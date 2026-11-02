import { useEffect, useRef, useState, type DragEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { api, DashError, type Work, type WorkDetail, type WorkMap } from "./api";
import { errorMessage, useT, type MsgKey } from "./i18n";
import Paper, { type Mark } from "./Paper";
import PrintHead from "./PrintHead";
import { useJob } from "./useJob";
import { useSubmitDraft } from "./useSubmitDraft";
import WorksMenu from "./WorksMenu";

const ANALYZING = ["running", "notes-running"];
const STOPPED = ["stopped", "notes-stopped"];
const UNANALYZED = ["stale", "none"];

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
export default function Reader({ slug, version, works, onOpen, onSubmitNew, onQuote, onFinished, onAnalysed, onPaper, onNewVersion, map = null, marks = [], drawing, reload = 0 }: {
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
  /** analyst 那一步完成(結構資料有了):外面重抓 map。 */
  onAnalysed?: () => void;
  /** 稿上顯示的是哪篇、是不是最新版、原文(邊說邊畫線要在最新版原文裡找引文)。 */
  onPaper?: (p: { slug: string; latest: boolean; text: string }) => void;
  /** 這一版的對位資料(印字頭印的點陣張力)。 */
  map?: WorkMap | null;
  /** 交新版成功(same = 跟最新版一字不差、沒有新增版本;version = 交成/對到的那一版)。 */
  onNewVersion?: (r: { same: boolean; version: number; analyzing: boolean }) => void;
}) {
  const t = useT();
  const [, setSearch] = useSearchParams();
  const [work, setWork] = useState<WorkDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [resumeErr, setResumeErr] = useState<string | null>(null);
  const [menu, setMenu] = useState<HTMLElement | null>(null);
  const [rev, setRev] = useState(0);
  const submit = useSubmitDraft(slug);
  const slugNow = useRef(slug);
  slugNow.current = slug;
  const [keeping, setKeeping] = useState(false);   // 送出中的是「只存版」那顆
  const fileInput = useRef<HTMLInputElement>(null);

  const analyzing = !!work && work.job_id !== null && ANALYZING.includes(work.state);
  const job = useJob(analyzing ? work!.job_id : null);

  const { cancel: dropDraft } = submit;
  useEffect(() => { setResumeErr(null); dropDraft(); }, [slug, dropDraft]);   // 換篇:交稿條不跟過去(會交到別篇)
  useEffect(() => { if (job.analysed) onAnalysed?.(); }, [job.analysed]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (work) onPaper?.({ slug: work.slug, latest: work.version === Math.max(work.version, ...work.versions), text: work.text });
  }, [work]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!job.done && !job.error) return;
    setRev(r => r + 1); onFinished?.();
  }, [job.done, job.error]);   // eslint-disable-line react-hooks/exhaustive-deps

  // 換作品或換版本:先清掉舊的字,別讓新的痕跡落在上一篇/上一版上(續跑重抓過之後也一樣)。
  useEffect(() => { setWork(null); setErr(null); }, [slug, version]);
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
  const pickVersion = (n: number) => setSearch(prev => {   // 只動 ?v=,其他參數(?s= 目前這局)留著
    const p = new URLSearchParams(prev);
    if (n === latest) p.delete("v"); else p.set("v", String(n));
    return p;
  });
  const start = (go: () => Promise<unknown>) => {   // 續跑 / 分析這版:開了就重抓這篇並通知左欄
    setResumeErr(null);
    go().then(() => { setRev(r => r + 1); onFinished?.(); },
      e => setResumeErr(e instanceof DashError ? e.code : "unknown"));
  };
  const submitNew = async (analyze: boolean) => {
    setKeeping(!analyze);
    const r = await submit.confirm({ analyze });
    if (!r || r.slug !== slugNow.current) return;   // 等確認的時候換了作品:別對別篇通知
    if (r.jobError) setResumeErr(r.jobError);   // 新版存下了但沒開成分析:回最新版,頂列有「分析這版」可重按
    onNewVersion?.({ same: r.same, version: r.version, analyzing: analyze && !r.same && !r.jobError });
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f && !submit.busy) void submit.fromFile(f);
  };
  const { draft } = submit;
  const est = draft?.estimate;
  return (
    <div className="reader" onDragOver={e => e.preventDefault()} onDrop={onDrop}>
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
        <button type="button" className="paper-newver" onClick={() => fileInput.current?.click()}>{t("newver.open")}</button>
        <input ref={fileInput} type="file" accept=".md,.txt" hidden
          onChange={e => { const f = e.target.files?.[0]; e.target.value = ""; if (f && !submit.busy) void submit.fromFile(f); }} />
        {STOPPED.includes(work.state) && <button type="button" className="paper-resume" onClick={() => start(() => api.startJob(slug, { resumeOnly: true }))}>{t("paper.resume")}</button>}
        {work.version === latest && UNANALYZED.includes(work.state) && (
          <button type="button" className="paper-resume" onClick={() => start(() => api.startJob(slug))}>{t("newver.analyze")}</button>
        )}
        {resumeErr && <span className="paper-state" role="alert">{t(errorMessage(resumeErr))}</span>}
      </header>
      {(draft || submit.error) && (
        <div className="dash-float home-box paper-newbar" role="group" aria-label={t("newver.open")}>
          {draft && <b>{t("newver.title", { n: latest + 1 })}</b>}
          {draft && (
            <p className="home-meta">
              <span>{t("feed.chars", { n: draft.chars })}</span>
              {est && <span>{est.v ? t("feed.estimate", { min: Math.max(1, Math.round(est.v.seconds / 60)) }) : t("feed.noEstimate")}</span>}
            </p>
          )}
          {submit.error && <p role="alert" className="home-msg">{t(errorMessage(submit.error))}</p>}
          <div className="home-actions">
            <button type="button" className="dash-key" disabled={submit.busy} onClick={submit.cancel}>{t("feed.cancel")}</button>
            {draft && <>
              <button type="button" className="dash-key home-go" disabled={submit.busy || !draft.chars} onClick={() => void submitNew(false)}>
                {submit.busy && keeping ? t("feed.sending") : t("newver.keep")}
              </button>
              <button type="button" className="dash-key home-go" disabled={submit.busy || !draft.chars} onClick={() => void submitNew(true)}>
                {submit.busy && !keeping ? t("feed.sending") : t("feed.go")}
              </button>
            </>}
          </div>
        </div>
      )}
      {work.version !== latest && (
        <p className="paper-old">
          {t("paper.oldVersion", { n: work.version })}
          <button type="button" onClick={() => pickVersion(latest)}>{t("paper.latest")}</button>
        </p>
      )}
      {work.version === latest && (
        <PrintHead key={work.job_id ?? "none"} running={analyzing} map={map}
          printed={job.analysed && !!map && map.analysis_version === map.version && map.beats.length > 0} />
      )}
      <Paper text={work.text} title={work.title} marks={marks} drawing={drawing} onBring={onQuote} />
      {menu && <WorksMenu anchor={menu} below works={works} current={slug} onOpen={onOpen}
        onSubmitNew={onSubmitNew} onClose={() => setMenu(null)} />}
    </div>
  );
}
