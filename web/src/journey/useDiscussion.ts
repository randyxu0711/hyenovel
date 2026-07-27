/** 一篇的討論局:訊息流 + session,活在「篇」這一層。
 *
 * 為什麼在這裡而不是 NodeTalk 裡:資料層從來就是 by story —— 後端 `Session.slug`、
 * `transcript.jsonl`、`conclusions.jsonl`、`recall(slug, anchors=...)` 全以篇為單位,
 * node 只是 `anchors`/`refs` 標註。狀態放在節點元件裡,「取消選取」就等於卸載,
 * 對話與 sessionId 一起蒸發,而後端那個 ClaudeSDKClient 還活著 —— 再選一顆是新
 * session,要重付一次 `/story-discuss` 開場(讀 analysis+feedback+source,~$0.13–0.24)。
 *
 * node 在這裡的角色只剩「這輪從哪切入」:換節點不重開局,只在訊息前補一句錨定。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { streamDiscuss, distillDiscuss, getTranscript } from "../data/client";
import type { Turn } from "../types";

// think = 這一則的推理草稿。跟 text 分開存,因為它們是兩種東西:text 是編輯說出口的話
// (逐字進 transcript 正本),think 只活在這個畫面上,後端不留。
export type Msg = { role: "me" | "ed"; text: string; think?: string };

export type Discussion = ReturnType<typeof useDiscussion>;

export function useDiscussion(slug: string) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [past, setPast] = useState<Turn[]>([]);     // 落盤的逐字歷史(唯讀)
  const [busy, setBusy] = useState(false);
  const [kept, setKept] = useState("");
  const [cold, setCold] = useState(false);          // session 已冷卻(sweep_idle 回收)→ 收不了
  const sessionId = useRef<string | null>(null);
  const anchored = useRef<string | null>(null);

  // 換篇才歸零。換節點不歸零 —— 那正是這個 hook 存在的理由。
  useEffect(() => {
    setMsgs([]); setBusy(false); setKept(""); setCold(false); setPast([]);
    sessionId.current = null; anchored.current = null;
    if (!slug) return;
    // 歷史是增益不是主線:抓不到就沒歷史,討論照常(同燼的處置)。
    let live = true;
    getTranscript(slug).then(r => { if (live) setPast(r.turns); }).catch(() => {});
    return () => { live = false; };
  }, [slug]);

  const send = useCallback(async (text: string, node: { id: string; label: string }, typeName: string) => {
    if (!text || busy) return;
    let toSend = text;
    if (node.id !== anchored.current) {
      toSend = `(就「${node.label}」這個${typeName}節點)\n${text}`;
      anchored.current = node.id;
    }
    setMsgs(m => [...m, { role: "me", text }, { role: "ed", text: "" }]);
    setBusy(true);
    const patchLast = (fn: (m: Msg) => Msg) =>
      setMsgs(m => { const c = [...m]; c[c.length - 1] = fn(c[c.length - 1]); return c; });
    try {
      for await (const ev of streamDiscuss(slug, sessionId.current, toSend, [node.id])) {
        if (ev.event === "token") patchLast(m => ({ ...m, text: m.text + (ev.data.text ?? "") }));
        else if (ev.event === "thinking") patchLast(m => ({ ...m, think: (m.think ?? "") + (ev.data.text ?? "") }));
        else if (ev.event === "message") { if (ev.data.session_id) sessionId.current = ev.data.session_id; if (ev.data.text) patchLast(m => ({ ...m, text: m.text || ev.data.text })); }
        else if (ev.event === "done") { if (ev.data.session_id) sessionId.current = ev.data.session_id; }
        else if (ev.event === "error") patchLast(m => ({ ...m, text: m.text || `(討論出錯:${ev.data.message})` }));
      }
    } catch (e) {
      patchLast(m => ({ ...m, text: m.text || `(連線中斷:${String(e instanceof Error ? e.message : e)})` }));
    } finally { setBusy(false); }
  }, [slug, busy]);

  // 收束這一局:LLM 只吐草稿,四道閘門在後端。寫成了就通知上層 refetch(新燼當場點著)。
  const keep = useCallback(async (onKept?: () => void) => {
    if (!sessionId.current || busy) return;
    setBusy(true); setKept("收束中…");
    try {
      const r = await distillDiscuss(slug, sessionId.current);
      if (r.reason === "session_gone") { setCold(true); setKept("討論已冷卻 · 逐字已留存"); }
      else {
        setKept(r.errors.length ? `擋下:${r.errors[0]}` : `留下 ${r.written} 條結論`);
        if (r.written > 0) onKept?.();
      }
    } catch (e) {
      setKept(`收束失敗:${String(e instanceof Error ? e.message : e)}`);
    } finally { setBusy(false); }
  }, [slug, busy]);

  // past 與 msgs 刻意不合併:msgs 是「這一局」,而「留下結論」受活著的 session 閘控。
  // 併成一條流,只有歷史時鈕也會亮,按下去只拿得到 session_gone。
  return { msgs, past, busy, kept, cold, sessionId, send, keep };
}
