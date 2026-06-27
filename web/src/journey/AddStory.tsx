import { useEffect, useRef, useState } from "react";
import { extractStory, createStory } from "../data/client";

type Phase = "pick" | "preview";

// 只負責「擲入前」:選檔 → 抽文字 → 過目改字 → 落 source.md。
// 確認後把 slug 交給 FormingStar,讓星骨在目錄裡長出來(分析串流不在這裡)。
export default function AddStory(
  { open, initialFile, onClose, onForming }:
  { open: boolean; initialFile?: File | null; onClose: () => void; onForming: (slug: string, title: string) => void },
) {
  const [phase, setPhase] = useState<Phase>("pick");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const handled = useRef<File | null>(null);

  const reset = () => { setPhase("pick"); setTitle(""); setText(""); setErr(null); setBusy(false); handled.current = null; };
  const close = () => { if (!busy) { reset(); onClose(); } };

  // 後端只抽不寫;抽壞的字會毒到逐字引用,所以一定先給人過目
  const onPick = async (f: File) => {
    setBusy(true); setErr(null);
    try {
      const r = await extractStory(f);
      setText(r.text);
      setTitle(t => t || f.name.replace(/\.[^.]+$/, ""));
      setPhase("preview");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  };

  // 從星空拖放進來的檔:自動抽文字直接進預覽
  useEffect(() => {
    if (open && initialFile && handled.current !== initialFile) {
      handled.current = initialFile;
      onPick(initialFile);
    }
    if (!open) handled.current = null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialFile]);

  const confirm = async () => {
    if (!title.trim() || !text.trim()) { setErr("標題和內文都要有"); return; }
    setBusy(true); setErr(null);
    try {
      const r = await createStory(title.trim(), text);
      const slug = r.slug, t = title.trim();
      reset(); onClose(); onForming(slug, t);   // 交棒給成形的星
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e)); setBusy(false);
    }
  };

  if (!open) return null;

  return (
    <div className="add-scrim" onPointerDown={e => { if (e.target === e.currentTarget) close(); }}>
      <div className="add-card">
        <div className="add-head">
          <span className="dock-t">新增故事</span>
          {!busy && <span className="dock-x" onClick={close}>✕</span>}
        </div>

        {phase === "pick" && (
          <div className="add-body">
            <p className="add-lead">請使用 txt / md / pdf / docx</p>
            <button className="add-drop" disabled={busy} onClick={() => fileRef.current?.click()}>
              {busy ? "讀取中…" : "＋ 選擇檔案"}
            </button>
            <input ref={fileRef} type="file" accept=".txt,.md,.pdf,.docx" hidden
              onChange={e => { const f = e.target.files?.[0]; if (f) onPick(f); e.target.value = ""; }} />
            {err && <p className="add-err">{err}</p>}
          </div>
        )}

        {phase === "preview" && (
          <div className="add-body">
            <label className="add-lab">標題</label>
            <input className="add-title" value={title} onChange={e => setTitle(e.target.value)} placeholder="這篇叫什麼" />
            <label className="add-lab">內文 <span className="add-count">{text.length} 字 · 抽壞請在此修正</span></label>
            <textarea className="add-text" value={text} onChange={e => setText(e.target.value)} spellCheck={false} />
            {err && <p className="add-err">{err}</p>}
            <div className="add-actions">
              <button className="add-ghost" onClick={() => { setPhase("pick"); setErr(null); }}>← 重選</button>
              <button className="add-go" disabled={busy} onClick={confirm}>完成</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
