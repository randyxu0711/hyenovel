import { useEffect, useRef, useState } from "react";
import { streamDiscuss } from "../data/client";
import type { VizNode, FeedbackPoint } from "../types";

type Msg = { role: "me" | "ed"; text: string };

// 沉浸式討論:不是側欄盒子,是星空上從節點長出來的發光對話。
// 先呈現編輯對這顆「已寫好的判斷」(kp),再從那句往下聊。
// 沿用 Dock 的串流 + 節點錨定;換節點不重開 session,改在訊息前補一句 context。
export default function NodeTalk(
  { slug, node, typeName, color, flag, kp, source, onJump, onClose }:
  { slug: string; node: VizNode; typeName: string; color: string; flag: string; kp: FeedbackPoint | null;
    source?: string; onJump?: (start: number, end: number) => void; onClose: () => void },
) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const sessionId = useRef<string | null>(null);
  const anchored = useRef<string | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => { setMsgs([]); setInput(""); setBusy(false); sessionId.current = null; anchored.current = null; }, [slug]);
  useEffect(() => { const b = bodyRef.current; if (b) b.scrollTop = b.scrollHeight; }, [msgs]);

  const cite = node.evidence.find(e => e.quote) ?? null;
  const quote = cite?.quote ?? "";
  // 附帶原文:抓引用句在原文的前後文,讓討論就貼著那段文本
  const passage = (() => {
    if (!source || !cite || cite.start == null || cite.end == null) return null;
    const a = Math.max(0, cite.start - 70), b = Math.min(source.length, cite.end + 70);
    return { pre: (a > 0 ? "…" : "") + source.slice(a, cite.start), mid: source.slice(cite.start, cite.end), post: source.slice(cite.end, b) + (b < source.length ? "…" : "") };
  })();

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    let toSend = text;
    if (node.id !== anchored.current) {
      toSend = `(就「${node.label}」這個${typeName}節點)\n${text}`;
      anchored.current = node.id;
    }
    setMsgs(m => [...m, { role: "me", text }, { role: "ed", text: "" }]);
    setBusy(true);
    const patchLast = (fn: (t: string) => string) =>
      setMsgs(m => { const c = [...m]; c[c.length - 1] = { role: "ed", text: fn(c[c.length - 1].text) }; return c; });
    try {
      for await (const ev of streamDiscuss(slug, sessionId.current, toSend)) {
        if (ev.event === "token") patchLast(t => t + (ev.data.text ?? ""));
        else if (ev.event === "message") { if (ev.data.session_id) sessionId.current = ev.data.session_id; if (ev.data.text) patchLast(t => t || ev.data.text); }
        else if (ev.event === "done") { if (ev.data.session_id) sessionId.current = ev.data.session_id; }
        else if (ev.event === "error") patchLast(t => t || `(討論出錯:${ev.data.message})`);
      }
    } catch (e) {
      patchLast(t => t || `(連線中斷:${String(e instanceof Error ? e.message : e)})`);
    } finally { setBusy(false); }
  }

  return (
    <div className="talk">
      <div className="talk-head">
        <span className="talk-type" style={{ color, borderColor: color }}>{typeName}</span>
        <span className="talk-label">{node.label}</span>
        {flag && <span className="talk-flag">⚑ {flag}</span>}
        <button className="talk-x" onClick={onClose}>✕</button>
      </div>

      <div className="talk-body" ref={bodyRef}>
        {/* 編輯對這顆已寫好的判斷:選中就先看到,再從這裡往下聊 */}
        <div className="talk-standing">
          {kp ? <>
            <div className="talk-kp-h">編輯的判斷</div>
            <p className="talk-kp-b">{kp.body}</p>
          </> : node.note ? <p className="talk-kp-b">{node.note}</p>
            : <p className="talk-kp-b dim">這顆目前沒有獨立的編輯標記，從這裡開始聊也行。</p>}
          {passage
            ? <p className="talk-passage">{passage.pre}<mark>{passage.mid}</mark>{passage.post}</p>
            : quote && <p className="talk-quote">「{quote}」</p>}
          {cite && onJump && <button type="button" className="talk-jump" onClick={() => onJump(cite.start, cite.end)}>在原文中讀整段 ↗</button>}
          {kp?.question && (
            <button type="button" className="talk-qseed" onClick={() => setInput(kp.question!)}>{kp.question}</button>
          )}
        </div>
        {msgs.map((m, i) => (
          <div key={i} className={`talk-line ${m.role}`}>
            {m.text || (busy && i === msgs.length - 1 ? <span className="talk-typing">…</span> : "")}
          </div>
        ))}
      </div>

      <form className="talk-compose" onSubmit={e => { e.preventDefault(); send(); }}>
        <textarea value={input} onChange={e => setInput(e.target.value)} rows={1} disabled={busy}
          placeholder={`就「${node.label}」說…`}
          onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
        <button type="submit" disabled={busy || !input.trim()}>{busy ? "…" : "↑"}</button>
      </form>
    </div>
  );
}
