/** 一篇的討論局:訊息流 + session,活在「篇」這一層。
 *
 * 為什麼在這裡而不是 NodeTalk 裡:資料層從來就是 by story —— den 的 discussion 掛在 story 上,
 * node 只是 utterance 的 `anchors` 標註。狀態放在節點元件裡,「取消選取」就等於卸載,
 * 對話與 sessionId 一起蒸發,再選一顆節點就成了新局。
 * 現在 den 每輪開一個工人、從 DB 逐字重送歷史;局 = discussion(session_id),換節點不重開局。
 *
 * node 在這裡的角色只剩「這輪從哪切入」:換節點不重開局,只在訊息前補一句錨定。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { getTranscript, streamDiscuss } from "../data/client";
import type { Turn } from "../types";

// think = 這一則的推理草稿。跟 text 分開存,因為它們是兩種東西:text 是編輯說出口的話
// (逐字進 transcript 正本),think 只活在這個畫面上,後端不留。
export type Msg = { role: "me" | "ed"; text: string; think?: string };

export type Discussion = ReturnType<typeof useDiscussion>;

export function useDiscussion(slug: string) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [past, setPast] = useState<Turn[]>([]);     // 落盤的逐字歷史(唯讀)
  const [busy, setBusy] = useState(false);
  const sessionId = useRef<string | null>(null);
  const anchored = useRef<string | null>(null);

  // 換篇才歸零。換節點不歸零 —— 那正是這個 hook 存在的理由。
  useEffect(() => {
    setMsgs([]); setBusy(false); setPast([]);
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
    // 失敗的一輪 den 不落盤(編輯下一輪不會記得):畫面上一律標出來,不讓截斷的字像正常回答。
    const UNSAVED = "(這輪沒完成,沒有存下;編輯下一輪不會記得這段)";
    const fail = (m: Msg, label: string, why: string): Msg =>
      ({ ...m, text: m.text ? `${m.text}\n\n${UNSAVED}(${why})` : `(${label}:${why})` });
    let terminal = false;
    const patchLast = (fn: (m: Msg) => Msg) =>
      setMsgs(m => { const c = [...m]; c[c.length - 1] = fn(c[c.length - 1]); return c; });
    try {
      for await (const ev of streamDiscuss(slug, sessionId.current, toSend, [node.id])) {
        if (ev.event === "token") patchLast(m => ({ ...m, text: m.text + (ev.data.text ?? "") }));
        else if (ev.event === "thinking") patchLast(m => ({ ...m, think: (m.think ?? "") + (ev.data.text ?? "") }));
        else if (ev.event === "message") { if (ev.data.session_id) sessionId.current = ev.data.session_id; if (ev.data.text) patchLast(m => ({ ...m, text: ev.data.text || m.text })); }
        else if (ev.event === "done") { terminal = true; if (ev.data.session_id) sessionId.current = ev.data.session_id; }
        else if (ev.event === "error") { terminal = true; patchLast(m => fail(m, "討論出錯", String(ev.data.message))); }
      }
      if (!terminal) patchLast(m => fail(m, "連線中斷", "連線提前結束"));
    } catch (e) {
      patchLast(m => fail(m, "連線中斷", String(e instanceof Error ? e.message : e)));
    } finally { setBusy(false); }
  }, [slug, busy]);

  // 收束不在這裡,也不在任何前端路徑上:收束暫無,另開切片。
  //
  // past 與 msgs 仍刻意不合併:msgs 是「這一局」(送訊息要帶 sessionId),
  // past 是整篇所有已落盤的局。合併會讓「這一局」的邊界消失。
  return { msgs, past, busy, sessionId, send };
}
