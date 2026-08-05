"""跨篇 align:把全部故事的標籤分群成概念地圖(stories/label-map.json)。

與 label_map.py 的分界(**不可合併**):
  這邊 = SDK 接線(開一次性 client、組 prompt、收 JSON 文字),不量覆蓋率。
  那邊 = 確定性層(閘門、鑄 id、蓋章、落地),吃 100% 門檻。
理由是 pyproject.toml 的 coverage include 白名單:「只量確定性層 —— 純函式、
無外部 SDK 接線」。把 SDK 放進頂層模組,不是破壞 100% 門檻,就是被踢出白名單。
同一條切法在 settled.py / server/settle.py 已經跑過一遍。

**全量重歸,不做增量**:增量永遠不會重切,第一次分群的切法會跟著你一輩子 ——
而那是只有七篇時切的。舊 map 當參考不當約束,它有權說「這族該裂成兩族」。

設計正本:docs/superpowers/specs/2026-07-30-cross-story-align-design.md
"""
import asyncio
import json

from claude_agent_sdk import ClaudeSDKClient

import label_map

from . import config, log as log_mod, sdk_runner
from .log import log

_PROMPT_HEAD = """以下是一位作者所有短篇的**分析標籤**,每行一個。
請把它們歸成跨篇的**概念族**,輸出**單一 JSON 陣列**,不要任何其他文字。

每個元素三個欄位:
  canonical   這一族的名字,一句短語
  node_type   這一族的型別,必須是 motif / theme / technique / effect 其中之一,
              且該族全部成員都是這個型別(不可混編)
  members     這一族的成員陣列,每個成員四個欄位:
                slug            原樣照抄下方那一行的 slug
                node            原樣照抄下方那一行的 node id
                label           **原樣照抄下方那一行的標籤,一字不改**(改了會被閘門擋掉)
                why             為什麼這個節點屬於這一族,一句話
                evidence_index  該節點的第幾條引文最能支持這個歸類(從 0 起算,
                                不可超過該行標示的引文條數)

規則:
- **同一個節點可以屬於多個族。** 「泡沫」可以同時是「水」也是「消逝」——
  概念是可疊加的,硬要它二選一反而把它壓扁了。
- 不要為了湊數而歸族。只跨一篇的族沒有意義,寧可讓它落單。
- 不要發明下方沒有的節點。編一個不存在的會被閘門擋掉。
- 不要給 id,那不是你的工作。

── 標籤開始(共 {n} 個)──
{body}
── 標籤結束 ──
{prev}"""

_PREV_HEAD = """
── 前一版的族名(僅供參考,可以推翻)──
你有權說「這一族太大了,該裂成兩族」或「這兩族其實是同一件事」。
沿用得下去的名字盡量沿用,讀起來比較穩;但**不要為了沿用而扭曲分群**。
{names}"""


def build_prompt(table, prev):
    """組 prompt(純函式)。

    **標籤由我們組進去,不叫它自己去掃 stories/** —— 放它自己讀等於載入全部故事內文,
    那正是承重算術要避免的(七份 analysis.json 原封不動是 116k 字元)。
    同一個立場在 settle.py 的 _format 也寫過:自己讀會撈到不該撈的東西。

    **prev 只給族名,不給 id** —— id 是確定性層鑄的,給它看會誘導它自填。
    """
    body = "\n".join(
        f"{r['slug']}\t{r['node']}\t{r['type']}\t{r['label']}\t(引文 {len(r['quotes'])} 條)"
        for r in table)
    names = ""
    if prev:
        got = [c.get("canonical") for c in (prev.get("concepts") or [])
               if isinstance(c, dict) and isinstance(c.get("canonical"), str)]
        if got:
            names = _PREV_HEAD.format(names="\n".join(f"- {g}" for g in got))
    return _PROMPT_HEAD.format(n=len(table), body=body, prev=names)


async def _ask(prompt):
    """開一次性專用 client 問一輪,回它吐的文字。照 settle.py 的形狀。

    **不記 ledger**:`ledger.append(slug, ...)` 寫的是 `stories/<slug>/usage.jsonl`,
    而 align 是跨篇的,沒有 slug 可掛;硬塞一個假 slug 會讓那個目錄不存在而被靜靜
    跳過(ledger 的既有契約),等於記了個寂寞。成本改記進 log —— 一次分群幾分錢,
    量級遠低於 critique/discuss,不值得為它發明一套跨篇帳本。
    (代價:這是 usage 帳本第一個不覆蓋的支出口,spec §13.6 記著。)

    **要包 wait_for**:`run_turn` 自己不帶逾時,critique 路徑上每一格 LLM 都是
    `asyncio.wait_for(..., PHASE_TIMEOUT)` 包起來的(orchestrator.py:125)。
    這條雖然在背景、不阻塞誕生,但卡住的 client 會一直占著,而且**卡住不會拋例外** ——
    呼叫端那個 `except Exception` 接不到它。
    """
    client = ClaudeSDKClient(options=sdk_runner.settle_options())
    await client.connect()
    try:
        r = await asyncio.wait_for(sdk_runner.run_turn(client, prompt),
                                   timeout=config.ALIGN_TIMEOUT)
        log.info(f"event=align-turn cost_usd={round(r.cost, 4)} is_error={r.is_error}")
        return r.text
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def rebuild_async(force=False):
    """重建地圖。回 {"ok", "skipped", "concepts", "errors"}。

    不 stale 且沒 force → 直接回,不花錢。
    """
    prev = label_map.load()
    if not force and prev is not None and not label_map.is_stale(prev):
        return {"ok": True, "skipped": True,
                "concepts": len(prev.get("concepts") or []), "errors": []}
    table = label_map.collect()
    if not table:
        return {"ok": False, "skipped": False, "concepts": 0,
                "errors": ["沒有任何可分群的標籤"]}
    text = await _ask(build_prompt(table, prev))
    mapping, errors = label_map.build(text)
    ok = mapping is not None
    log.info(f"event=align ok={ok} labels={len(table)} "
             f"concepts={len(mapping['concepts']) if ok else 0} errors={len(errors)}")
    return {"ok": ok, "skipped": False,
            "concepts": len(mapping["concepts"]) if ok else 0, "errors": errors}


def rebuild(force=False):
    """同步包裝,給 CLI 與測試用。"""
    return asyncio.run(rebuild_async(force))


# 醒來看一次的間隔。地圖不需要「critique 一結束就新鮮」,只需要在你下一次跨篇討論
# 之前新鮮;而醒來的判定本身是幾個 sha1,零成本。
SWEEP_INTERVAL = 60


async def _sweep_once():
    """醒來一次:該重建就重建。回「這一輪有沒有真的去重建」(給測試看的)。

    **判斷全在這裡,sweep_align 只剩迴圈** —— 政策要可測,骨架不必測。
    """
    from . import critique      # 延後 import:critique 會 import orchestrator,模組層
                                # 互相 import 容易繞回來(同 settle.py:112 的做法)
    try:
        if critique.list_running():
            return False
        m = label_map.load()
        if m is not None and not label_map.is_stale(m):
            return False
        r = await rebuild_async()
        if not r["ok"]:
            log.warning(f"event=align-fail errors={len(r['errors'])}")
        return True
    except Exception:
        # 最後一道:一輪炸掉不可以讓整個 worker 靜靜死掉。
        log.exception("event=align-sweep-fail")
        return False


async def sweep_align():
    """背景:跨篇概念地圖 stale 就重建。

    **單一 task、迴圈內序列 await —— 不可改成 per-story create_task 扇出。**
    扇出會讓兩輪併發各讀到同一份 prev、各花一次錢,最後 last-writer-wins 覆蓋掉
    另一份(#15 已經為同一個形狀買過單:sweep_settle 扇出會煉兩次)。

    **為什麼是輪詢而不是掛 critique 收尾**:掛在 orchestrator 尾巴會把一次 30–90 秒的
    分群塞進誕生儀式第三拍與第四拍之間(_STEP 的 render 是 3、done 才是 4),
    而輪詢的成本只是幾個 analysis.json 的 sha1。完整理由見 spec §7。
    """
    while True:
        await asyncio.sleep(SWEEP_INTERVAL)
        await _sweep_once()


if __name__ == "__main__":
    import sys

    # CLI 不經過 app.py 的 startup,logging 沒人配置過 —— 不呼叫這行的話
    # event=align-turn(**唯一的成本紀錄**,align 沒有 slug 可掛 ledger)整個蒸發。
    log_mod.setup()
    r = rebuild(force="--force" in sys.argv)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    sys.exit(0 if r["ok"] else 1)
