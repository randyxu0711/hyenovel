"""自動收束:把已結束的討論局壓成結論,不需要人按鈕。

與 discuss.py 的分界:那邊管**活著的**討論(session registry、串流、逐字落盤),
這邊管**結束之後**的事。兩者現在連依賴都沒有 —— 收束不再借用討論的 client。

**為什麼從逐字煉、不在活著的 session 裡煉**(推翻 distill() 原本的 docstring):
原判斷「只有活著的 session 語境最完整」管的是*語境重建*,那條仍然成立(spec §9.4:
記憶靠結論傳承,不靠逐字傳承)。但收束需要的只是「剛才雙方講了什麼」,而 transcript.jsonl
就是那個東西的正本。買到的是:蒸餾不再壓在「那個 claude 子行程閒置十幾分鐘後還活著嗎」
這個**我們從來沒驗證過**的假設上——而它的失敗是無聲的(只落一行 log,畫面/測試/CI 全綠)。
順帶 server 中途掛掉也不掉東西:逐字在硬碟上,重開後 _sessions 是空的,補煉即可。

LLM 全程唯讀(settle_options 的 allowed_tools=["Read"]):它把 JSON 當文字吐出來,
由 conclusions.py 解析、驗三道閘門、蓋章寫入。
"""
import asyncio

from claude_agent_sdk import ClaudeSDKClient

import conclusions
import settled

from . import config, ledger, sdk_runner, transcript
from .log import log

# 掃描間隔。判斷本身只讀幾個小檔,便宜;真正的成本在蒸餾那一輪。
SWEEP_INTERVAL = 30

# 一輪最多煉幾局。意外 backlog(久沒開的機器)用滴的不用灌的 —— 一輪把十幾局全煉了
# 是一筆無人看管的帳單。
MAX_PER_SWEEP = 3

_PROMPT_HEAD = """以下是一局已經結束的討論逐字。把它收束成結論,輸出**單一 JSON 陣列**,
不要任何其他文字。

每個元素只有四個欄位:
  kind    observation(對文本的觀察)/ judgment(編輯判斷)/ question(仍未解的提問)
  text    一句話講完這條結論,且**能獨立成立** —— 日後它會在沒有這段對話的情況下被撈出來
  refs    相關的 analysis node id 陣列(如 ["t3","m1"]);**必須是圖裡真有的 id**,
          編一個不存在的會被閘門擋掉。不確定就給 []
  quotes  支撐這條結論的**逐字原文**陣列;一字不改,改了會被閘門擋掉。沒有就給 []

只收真的有結論的東西 —— 沒有就回 []。不要複述對話裡說過的話,不要客套。
需要對照原文或 node id 時,讀 stories/{slug}/ 底下的 source.md 與 analysis.json。

── 逐字開始({slug},共 {n} 則)──
{body}
── 逐字結束 ──"""


def _format(slug, rows):
    """把一局的逐字組成 prompt。

    **由我們組進 prompt,不讓它自己讀 transcript.jsonl** —— 那個檔含整篇所有 session,
    放它去讀會串到別局,而它無從分辨哪幾行屬於這一局。
    """
    body = "\n\n".join(
        f"{'我' if r.get('role') == 'user' else '編輯'}:{r.get('text') or ''}"
        for r in rows)
    return _PROMPT_HEAD.format(slug=slug, n=len(rows), body=body)


async def settle_session(slug, session_id):
    """煉一局。回 {"written", "errors"}。**無論成敗都寫一列 settled.jsonl。**

    不寫那一列的話:成功但漏記 → 下輪重煉出重複結論;失敗但漏記 → 永遠重試。
    水位就是這裡唯一的出口,所以它在 finally 的位置(不是 happy path 上)。
    """
    rows = transcript.load(slug)
    turns = transcript.session_range(rows, session_id)
    mine = [r for r in rows if r.get("session") == session_id]
    if not mine or turns == [-1, -1]:
        # 退化區間:逐字寫入曾被吞掉。硬煉會蓋出一份指向別局第一行的 provenance —— 一個
        # 看起來合理的謊(見 transcript.session_range 的 docstring)。記帳放棄,不重試。
        settled.record(slug, session_id, True, 0, ["逐字裡沒有這一局"])
        return {"written": 0, "errors": ["逐字裡沒有這一局"]}

    ok, written, errors = False, 0, []
    client = None
    try:
        client = ClaudeSDKClient(options=sdk_runner.settle_options())
        await client.connect()
        r = await sdk_runner.run_turn(client, _format(slug, mine))
        ledger.append(slug, "distill", 0, r)
        drafts, err = conclusions.parse_drafts(r.text)
        if err:
            log.warning(f"event=settle-parse-fail slug={slug} session={session_id}")
            errors = [err]
        else:
            # 閘門跑過了就算收束完成 —— 即使一條都沒過(written=0)。那是合法結果,
            # 重試只會重現同一批被擋的草稿。
            ok = True
            written, errors = conclusions.append(slug, drafts, session_id, turns)
    except Exception as e:
        log.exception(f"event=settle-fail slug={slug} session={session_id}")
        errors = [str(e)]
    finally:
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass
        settled.record(slug, session_id, ok, written, errors)
    log.info(f"event=settle slug={slug} session={session_id} "
             f"ok={ok} written={written} errors={len(errors)}")
    return {"written": written, "errors": errors}


def _live(slug):
    """該篇還活著的 session id。延後 import:discuss 也在 server/ 內,模組層互 import
    會繞回來(discuss 不 import 本模組,但保持單向依賴比較不會有下一次意外)。"""
    from . import discuss
    return {s["session_id"] for s in discuss.list_sessions(slug)}


def due(limit=MAX_PER_SWEEP):
    """這一輪該煉的 (slug, session_id),最多 limit 局(純判斷,不花錢)。"""
    out = []
    if not config.STORIES.is_dir():
        return out
    for d in sorted(config.STORIES.iterdir()):
        if not d.is_dir():
            continue
        for sid in settled.pending(d.name, transcript.load(d.name), _live(d.name)):
            out.append((d.name, sid))
            if len(out) >= limit:
                return out
    return out


async def sweep_settle():
    """背景:把已結束的討論局煉成結論。

    **單一 task、迴圈內序列 await —— 不可改成 per-story create_task 扇出。**
    一次蒸餾約 90 秒,而水位要等 settle_session 收尾才寫得下去;扇出會讓同一局在水位
    落地前被下一輪(或同輪的另一個 task)再撿一次,煉兩次、付兩次、寫出重複結論。
    conclusions.append 的無鎖 read-then-write 配 id 也是靠這個序列前提站著的。
    """
    while True:
        await asyncio.sleep(SWEEP_INTERVAL)
        try:
            batch = due()
        except Exception:
            log.exception("event=settle-scan-fail")
            continue
        for slug, sid in batch:
            try:
                await settle_session(slug, sid)
            except Exception:
                # settle_session 自己已經兜過一層;這裡是最後一道,確保一篇炸掉
                # 不會讓整個 worker 靜靜死掉(死掉的守衛跟活著的守衛長得一樣)。
                log.exception(f"event=settle-sweep-fail slug={slug} session={sid}")
