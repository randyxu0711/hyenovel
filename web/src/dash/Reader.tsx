import { useEffect, useRef, useState } from "react";
import { api, DashError, type WorkDetail } from "./api";
import { errorMessage, useT, type MsgKey } from "./i18n";
import NotesPanel from "./NotesPanel";
import { useJob } from "./useJob";
import { useSelectionQuote } from "./useSelectionQuote";

const ANALYZING = ["running", "notes-running"];
const STOPPED = ["stopped", "notes-stopped"];

/** 打字紙:滾筒在上、稿在下;選一段 → 浮動鈕帶進對話。 */
export default function Reader({ slug, companion, onQuote, onFinished, reload = 0 }: {
  slug: string; companion: string; onQuote: (q: string) => void;
  /** 外面遞增 = 這篇要重抓(例如重交了同一篇)。 */
  reload?: number;
  /** 分析跑完(重抓過這篇之後)通知,好讓左欄重抓。 */
  onFinished?: () => void;
}) {
  const t = useT();
  const [work, setWork] = useState<WorkDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [notesOpen, setNotesOpen] = useState(false);
  const [rev, setRev] = useState(0);
  const body = useRef<HTMLDivElement>(null);   // 只收正文的選取;標題不在內
  const { quote, tooLong, clear } = useSelectionQuote(body);

  const analyzing = !!work && work.job_id !== null && ANALYZING.includes(work.state);
  const job = useJob(analyzing ? work!.job_id : null);

  useEffect(() => { setNotesOpen(false); }, [slug]);
  useEffect(() => {
    if (!job.done && !job.error) return;
    setRev(r => r + 1); onFinished?.();
  }, [job.done, job.error]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let live = true;
    if (rev === 0) { setWork(null); setErr(null); }
    api.work(slug).then(w => { if (live) setWork(w); },
      e => { if (live) setErr(e instanceof DashError ? e.code : "unknown"); });
    return () => { live = false; };
  }, [slug, rev, reload]);

  if (err) return <div className="reader-note" role="alert">{t(errorMessage(err))}</div>;
  if (!work) return <div className="reader-note">{t("loading")}</div>;

  const notesBlock = work.notes_ready ? null
    : t(ANALYZING.includes(work.state) ? "notes.running" : "notes.none");
  return (
    <div className="reader" data-notes={notesOpen ? "open" : "closed"}>
      <div className="platen">
        <i />
        <span className="platen-tools">
          {t("rail.version", { n: work.version })}
          {analyzing && <>
            <span className="platen-mark" aria-hidden="true" />
            <span role="status">{t("job.reading")}{job.step && ` · ${t(`job.step.${job.step}` as MsgKey)}`}</span>
          </>}
          {STOPPED.includes(work.state) && <span role="status">{t(work.state === "stopped" ? "job.stopped" : "job.notesStopped")}</span>}
        </span>
        <i />
      </div>
      <div className="reader-bar">
        <button type="button" className="reader-notes" disabled={notesBlock !== null} aria-pressed={notesOpen}
          aria-describedby={notesBlock ? "notes-why" : undefined} onClick={() => setNotesOpen(o => !o)}>
          {t(notesOpen ? "notes.close" : "notes.open")}
        </button>
        {notesBlock && <span id="notes-why" className="reader-why">{notesBlock}</span>}
      </div>
      <div className="reader-body">
      <article className="sheet">
        <h1>{work.title}</h1>
        <div ref={body}>
          {paragraphs(work.text, work.title).map((p, i) => <p key={i}>{p}</p>)}
        </div>
      </article>
      {notesOpen && work.notes_ready && <NotesPanel slug={slug} />}
      </div>
      {quote && (
        <div className="reader-float">
          <button type="button" className="reader-bring" disabled={tooLong}
            onMouseDown={e => e.preventDefault()}
            onClick={() => { onQuote(quote); clear(); }}>
            {t("reader.bring", { name: companion })}
          </button>
          {tooLong && <span role="status">{t("reader.tooLong")}</span>}
        </div>
      )}
    </div>
  );
}

/** 原文分段;第一段若只是標題(標點、全半形、空白不計)就拿掉,標題已經在 h1 了。 */
function paragraphs(text: string, title: string): string[] {
  const ps = text.split(/\n+/).filter(p => p.trim());
  const bare = (s: string) => s.normalize("NFKC").replace(/[\p{P}\p{S}\s]/gu, "");
  return ps.length > 1 && bare(ps[0]) === bare(title) ? ps.slice(1) : ps;
}
