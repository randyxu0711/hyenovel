import { useEffect, useRef, useState } from "react";
import { distillDiscuss, streamDiscuss } from "../data/client";
import type { VizData } from "../types";

const CN: Record<string, string> = { technique: "技法", effect: "效果", theme: "主題", motif: "意象", beat: "節拍", character: "角色" };

type Msg = { role: "me" | "ed"; text: string };

export default function Dock(
  { slug, viz, selected, onJump }:
  { slug: string; viz: VizData; selected: string | null; onJump?: (start: number, end: number) => void },
) {
  const [open, setOpen] = useState(true);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [kept, setKept] = useState<string>("");     // 收束結果的一行回報
  const sessionId = useRef<string | null>(null);   // 後端在 done/message 回傳,續局用
  const anchored = useRef<string | null>(null);     // 上次已對後端聲明的節點,避免每輪重貼
  const bodyRef = useRef<HTMLDivElement>(null);

  // 換故事 → 整局重置(舊 session 由後端 sweep_idle 回收)
  useEffect(() => {
    setMsgs([]); setInput(""); setBusy(false); setKept("");
    sessionId.current = null; anchored.current = null;
  }, [slug]);

  // 新訊息/串流 → 捲到底
  useEffect(() => { const b = bodyRef.current; if (b) b.scrollTop = b.scrollHeight; }, [msgs]);

  const node = selected ? viz.nodes.find(n => n.id === selected) : null;
  const kp = selected && viz.feedback
    ? viz.feedback.key_points.find(p => p.refs.includes(selected)) : null;

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");

    // 節點錨定:話題切到新節點時,在訊息前貼一句 context(同節點連續發問就不重貼)
    let toSend = text;
    if (selected && selected !== anchored.current) {
      const n = viz.nodes.find(x => x.id === selected);
      if (n) toSend = `(就「${n.label}」這個${CN[n.type] || n.type}節點)\n${text}`;
      anchored.current = selected;
    }

    setMsgs(m => [...m, { role: "me", text }, { role: "ed", text: "" }]);
    setBusy(true);
    const patchLast = (fn: (t: string) => string) =>
      setMsgs(m => { const c = [...m]; c[c.length - 1] = { role: "ed", text: fn(c[c.length - 1].text) }; return c; });
    try {
      for await (const ev of streamDiscuss(slug, sessionId.current, toSend, selected ? [selected] : [])) {
        if (ev.event === "token") {
          patchLast(t => t + (ev.data.text ?? ""));
        } else if (ev.event === "message") {
          if (ev.data.session_id) sessionId.current = ev.data.session_id;
          if (ev.data.text) patchLast(t => t || ev.data.text);   // 沒串到 token 才用整段 fallback
        } else if (ev.event === "done") {
          if (ev.data.session_id) sessionId.current = ev.data.session_id;
        } else if (ev.event === "error") {
          patchLast(t => t || `(討論出錯:${ev.data.message})`);
        }
      }
    } catch (e) {
      patchLast(t => t || `(連線中斷:${String(e instanceof Error ? e.message : e)})`);
    } finally {
      setBusy(false);
    }
  }

  // 明示收束:蒸餾時機是判斷題,v1 由使用者說「這段聊完了」,不自動猜。
  async function keep() {
    if (!sessionId.current || busy) return;
    setBusy(true);
    setKept("收束中…");
    try {
      const r = await distillDiscuss(slug, sessionId.current);
      setKept(r.errors.length ? `擋下:${r.errors[0]}` : `留下 ${r.written} 條結論`);
    } catch (e) {
      setKept(`收束失敗:${String(e instanceof Error ? e.message : e)}`);
    } finally { setBusy(false); }
  }

  if (!open) return <button className="dock-tab" onClick={() => setOpen(true)}>編輯 · 討論</button>;

  return (
    <aside className="dock">
      <div className="dock-head"><span className="dock-t">編輯 · 討論</span>
        <span className="dock-x" onClick={() => setOpen(false)}>⟩</span></div>

      <div className="dock-body" ref={bodyRef}>
        {!node && viz.feedback && <>
          <div className="dock-type">編輯總覽</div>
          <div className="dock-label">整體閱讀</div>
          <p>{viz.feedback.read}</p>
          <div className="dock-lab">如果只能改一件事</div>
          <p>{viz.feedback.one_line}</p>
          {msgs.length === 0 && <>
            <div className="dock-lab">就地討論</div>
            <div className="bubble ed">點左邊圖上任一節點,我們就從那裡聊起;或直接在下面寫下你的想法。</div>
          </>}
        </>}
        {node && <>
          <div className="dock-type">{CN[node.type] || node.type}</div>
          <div className="dock-label">{node.label}</div>
          {kp ? <>
            <div className="dock-lab">編輯的判斷</div><p>{kp.body}</p>
            {kp.question && <button className="bubble ed q-seed" onClick={() => setInput(kp.question!)}>{kp.question}</button>}
          </> : <p>{node.note || "這個節點目前沒有編輯標記,從這裡開始討論也可以。"}</p>}
          {node.evidence.length > 0 && <>
            <div className="dock-lab">原文證據</div>
            {node.evidence.map((ev, i) => (
              <div className="ev" key={i}>
                <p className="ev-q">「{ev.quote}」</p>
                {onJump && <button className="dock-jump" onClick={() => onJump(ev.start, ev.end)}>在原文中看 ↗</button>}
              </div>
            ))}
          </>}
        </>}

        {msgs.length > 0 && <div className="dock-thread">
          {msgs.map((m, i) => (
            <div key={i} className={`bubble ${m.role === "me" ? "me" : "ed"}`}>
              {m.text || (busy && i === msgs.length - 1 ? <span className="dock-typing">…</span> : "")}
            </div>
          ))}
        </div>}

        {msgs.length > 0 && (
          <div className="dock-keep">
            <button type="button" onClick={keep} disabled={busy || !sessionId.current}>留下結論</button>
            {kept && <span className="dock-kept">{kept}</span>}
          </div>
        )}
      </div>

      <form className="dock-compose" onSubmit={e => { e.preventDefault(); send(); }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder={node ? `就「${node.label}」聊…` : "寫下你的想法…(Enter 送出,Shift+Enter 換行)"}
          rows={2}
          disabled={busy}
        />
        <button type="submit" className="dock-send" disabled={busy || !input.trim()}>
          {busy ? "…" : "送出"}
        </button>
      </form>
    </aside>
  );
}
