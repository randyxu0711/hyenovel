import { useEffect, useRef, useState, type DragEvent, type KeyboardEvent } from "react";
import { api, DashError, type Estimate } from "./api";
import { errorMessage, useT } from "./i18n";

const RESTART = ["none", "stopped", "notes-stopped"];

/** 「捲進一張新稿」:貼上或選檔/拖檔 → 字數與預估 → 交稿並開跑(或切到已存在的同稿)。 */
export default function Feed({ onClose, onSubmitted }: {
  onClose: () => void;
  /** 交稿完成(含已存在的同稿)。existing = 沒有開新 job。 */
  onSubmitted: (slug: string, existing: boolean) => void;
}) {
  const t = useT();
  const [text, setText] = useState("");
  const [title, setTitle] = useState<string | undefined>();
  const [est, setEst] = useState<{ chars: number; v: Estimate | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const chars = text.trim().length;

  useEffect(() => { area.current?.focus(); }, []);
  useEffect(() => {
    if (!chars) return;
    let live = true;
    const h = setTimeout(() => {
      api.estimate(chars).then(v => { if (live) setEst({ chars, v }); }, () => { if (live) setEst({ chars, v: null }); });
    }, 300);
    return () => { live = false; clearTimeout(h); };
  }, [chars]);

  const fail = (e: unknown) => setErr(e instanceof DashError ? e.code : "unknown");
  const load = async (file: File) => {
    setErr(null);
    try {
      const r = await api.extract(file);
      setText(r.text);
      setTitle(r.filename.replace(/\.(md|txt)$/i, ""));
    } catch (e) { fail(e); }
  };
  const drop = (e: DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f) void load(f);
  };
  const requestClose = () => { if (text.trim() && !confirming) setConfirming(true); else onClose(); };
  const go = async () => {
    if (!chars || busy) return;
    setBusy(true); setErr(null);
    try {
      const r = await api.submit(text, title);
      if (r.reused) {
        // 上次可能交稿成功但沒開成 job:沒分析過或停住的才補開(den 會續跑,不重跑)
        const w = await api.work(r.slug);
        if (RESTART.includes(w.state)) await api.startJob(r.slug);
        onSubmitted(r.slug, true);
        return;
      }
      await api.startJob(r.slug);
      onSubmitted(r.slug, false);
    } catch (e) { fail(e); setBusy(false); }
  };
  const key = (e: KeyboardEvent) => {
    if (e.key === "Escape") { e.stopPropagation(); requestClose(); return; }
    if (e.key !== "Tab") return;
    const els = [...box.current!.querySelectorAll<HTMLElement>("textarea, button, input")].filter(x => !(x as HTMLButtonElement).disabled);
    const first = els[0], last = els[els.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };

  const fresh = est && est.chars === chars ? est : null;
  return (
    <div className="feed-scrim" onMouseDown={e => { if (e.target === e.currentTarget && !text.trim()) onClose(); }}>
      <div className="feed" role="dialog" aria-modal="true" aria-labelledby="feed-h" ref={box}
        onKeyDown={key} onDragOver={e => e.preventDefault()} onDrop={drop}>
        <h2 id="feed-h">{t("feed.title")}</h2>
        <textarea ref={area} aria-label={t("feed.text")} placeholder={t("feed.paste")} value={text}
          onChange={e => { setText(e.target.value); setTitle(undefined); }} />
        <div className="feed-meta">
          <label className="feed-file">
            <input type="file" accept=".md,.txt" onChange={e => { const f = e.target.files?.[0]; if (f) void load(f); e.target.value = ""; }} />
            <span>{t("feed.pick")}</span>
          </label>
          {chars > 0 && <span>{t("feed.chars", { n: chars })}</span>}
          {fresh && <span>{fresh.v ? t("feed.estimate", { min: Math.max(1, Math.round(fresh.v.seconds / 60)) }) : t("feed.noEstimate")}</span>}
        </div>
        {err && <p role="alert" className="feed-msg">{t(errorMessage(err))}</p>}
        <div className="feed-actions">
          {confirming ? (
            <>
              <span role="alert" className="feed-msg">{t("feed.discard")}</span>
              <button type="button" onClick={() => setConfirming(false)}>{t("feed.keep")}</button>
              <button type="button" onClick={onClose}>{t("feed.discardYes")}</button>
            </>
          ) : <button type="button" onClick={requestClose}>{t("feed.cancel")}</button>}
          <button type="button" className="feed-go" disabled={!chars || busy} onClick={() => void go()}>
            {busy ? t("feed.sending") : t("feed.go")}
          </button>
        </div>
      </div>
    </div>
  );
}
