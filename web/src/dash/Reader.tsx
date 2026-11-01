import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, DashError, type Work, type WorkDetail } from "./api";
import { errorMessage, useT, type MsgKey } from "./i18n";
import Paper, { type Mark } from "./Paper";
import { useJob } from "./useJob";
import WorksMenu from "./WorksMenu";

const ANALYZING = ["running", "notes-running"];
const STOPPED = ["stopped", "notes-stopped"];

/** 作品狀態(den 的 state + notes_ready,都是最新版的)→ 頂列那句話。 */
export function stateText(state: string, notesReady: boolean): MsgKey {
  switch (state) {
    case "running": return "state.running";
    case "notes-running": return "state.notesRunning";
    case "notes-stopped": return "state.notesStopped";
    case "ready": return notesReady ? "state.allReady" : "state.ready";
    case "stopped": return "state.stopped";
    case "stale": return "state.stale";
    default: return "state.none";
  }
}

/** 稿窗格:頂列(標題 ▾、版本、狀態)+ 紙。 */
export default function Reader({ slug, version, works, onOpen, onSubmitNew, onQuote, onFinished, marks = [], drawing, reload = 0 }: {
  slug: string; works: Work[];
  onOpen: (slug: string) => void; onSubmitNew: () => void;
  onQuote: (q: string) => void;
  /** 指定版本(?v=);沒給就是最新。 */
  version?: number;
  /** 讀者痕跡與正在畫的那道。 */
  marks?: Mark[]; drawing?: string;
  /** 外面遞增 = 這篇要重抓(例如重交了同一篇)。 */
  reload?: number;
  /** 分析跑完(重抓過這篇之後)通知,好讓左欄重抓。 */
  onFinished?: () => void;
}) {
  const t = useT();
  const [, setSearch] = useSearchParams();
  const [work, setWork] = useState<WorkDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [resumeErr, setResumeErr] = useState<string | null>(null);
  const [menu, setMenu] = useState<HTMLElement | null>(null);
  const [rev, setRev] = useState(0);

  const analyzing = !!work && work.job_id !== null && ANALYZING.includes(work.state);
  const job = useJob(analyzing ? work!.job_id : null);

  useEffect(() => { setResumeErr(null); }, [slug]);
  useEffect(() => {
    if (!job.done && !job.error) return;
    setRev(r => r + 1); onFinished?.();
  }, [job.done, job.error]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let live = true;
    if (rev === 0) { setWork(null); setErr(null); }
    api.work(slug, version).then(w => { if (live) setWork(w); },
      e => { if (live) setErr(e instanceof DashError ? e.code : "unknown"); });
    return () => { live = false; };
  }, [slug, version, rev, reload]);

  if (err) return <div className="reader-note" role="alert">{t(errorMessage(err))}</div>;
  if (!work) return <div className="reader-note">{t("loading")}</div>;

  const latest = Math.max(work.version, ...work.versions);
  const pickVersion = (n: number) => setSearch(n === latest ? {} : { v: String(n) });
  const resume = () => {
    setResumeErr(null);
    api.startJob(slug, { resumeOnly: true }).then(() => { setRev(r => r + 1); onFinished?.(); },
      e => setResumeErr(e instanceof DashError ? e.code : "unknown"));
  };
  return (
    <div className="reader">
      <header className="paper-top">
        <h1 className="paper-h">
          <button type="button" className="paper-title" aria-haspopup="dialog" aria-expanded={!!menu}
            onClick={e => { const el = e.currentTarget; setMenu(m => (m ? null : el)); }}>
            {work.title}<span aria-hidden="true"> ▾</span>
          </button>
        </h1>
        <div className="paper-vers" role="group" aria-label={t("paper.versions")}>
          {work.versions.map(n => (
            <button key={n} type="button" className="dash-dm" aria-pressed={n === work.version} onClick={() => pickVersion(n)}>v{n}</button>
          ))}
        </div>
        <span className="paper-state" role="status">
          {t(stateText(work.state, work.notes_ready))}
          {analyzing && job.step && ` · ${t(`job.step.${job.step}` as MsgKey)}`}
        </span>
        {STOPPED.includes(work.state) && <button type="button" className="paper-resume" onClick={resume}>{t("paper.resume")}</button>}
        {resumeErr && <span className="paper-state" role="alert">{t(errorMessage(resumeErr))}</span>}
      </header>
      {work.version !== latest && (
        <p className="paper-old">
          {t("paper.oldVersion", { n: work.version })}
          <button type="button" onClick={() => pickVersion(latest)}>{t("paper.latest")}</button>
        </p>
      )}
      <Paper text={work.text} title={work.title} marks={marks} drawing={drawing} onBring={onQuote} />
      {menu && <WorksMenu anchor={menu} below works={works} current={slug} onOpen={onOpen}
        onSubmitNew={onSubmitNew} onClose={() => setMenu(null)} />}
    </div>
  );
}
