import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, DashError, type WorkDetail } from "./api";
import { clock, stepOf } from "./clock";
import DropSheet from "./DropSheet";
import Icon from "./Icon";
import { errorMessage, useLang, useT, type MsgKey } from "./i18n";
import Paper, { type Mark, type ObSpan } from "./Paper";
import { useJob } from "./useJob";
import { useSubmitDraft } from "./useSubmitDraft";
import { setPaperFlow, usePaperFlow } from "./paperFlow";
import { whenLabel } from "./when";

const ANALYZING = ["running", "notes-running"];
const STOPPED = ["stopped", "notes-stopped"];
const UNANALYZED = ["stale", "none"];

/** 頂列的狀態字:只在版本點表達不了時才出聲(停住、或沒有 job 卻在跑);好了、還沒分析都靠點與「分析」鈕。 */
export function stateText(state: string): MsgKey | null {
  switch (state) {
    case "running": return "state.running";
    case "notes-running": return "state.notesRunning";
    case "notes-stopped": return "state.notesStopped";
    case "stopped": return "state.stopped";
    default: return null;
  }
}

/** 版本條露哪幾版:不超過 max 版就全露;否則最新 max 版,目前看的那版若不在其中 → [它, 最新兩版]。升冪。 */
export function shownVersions(all: number[], cur: number, max = 3): { more: boolean; list: number[] } {
  if (all.length <= max) return { more: false, list: all };
  const tail = all.slice(-max);
  return { more: true, list: tail.includes(cur) ? tail : [cur, ...all.slice(-(max - 1))] };
}

/** 版本點:空心 = 沒分析;半顆 = 有分析沒筆記;實心 = 都有。latestState 只給最新版:分析中跳動。 */
export function dotOf(h: { analysed: boolean; noted: boolean }, latestState?: string): { dot: "empty" | "half" | "full"; busy: boolean } {
  if (latestState === "running") return { dot: "empty", busy: true };
  if (latestState === "notes-running") return { dot: "half", busy: true };
  return { dot: h.analysed ? (h.noted ? "full" : "half") : "empty", busy: false };
}

function VDot({ d }: { d: ReturnType<typeof dotOf> }) {
  return <span className="vdot" data-dot={d.dot} data-busy={d.busy ? "" : undefined} aria-hidden="true" />;
}

/** 稿窗格:頂列(標題、版本條、交新版、分析、排法)+ 紙。 */
export default function Reader({ slug, version, onQuote, onFinished, onAnalysed, onPaper, onNewVersion, marks = [], obs = [], drawing, reload = 0, focus = false, onFocus }: {
  slug: string;
  onQuote: (q: string) => void;
  /** 指定版本(?v=);沒給就是最新。 */
  version?: number;
  /** 讀者痕跡與正在畫的那道。 */
  marks?: Mark[]; drawing?: string;
  /** 結構圖選中的觀察在這版原文的位置(畫直線)。 */
  obs?: ObSpan[];
  /** 外面遞增 = 這篇要重抓(例如重交了同一篇)。 */
  reload?: number;
  /** 分析跑完(重抓過這篇之後)通知,好讓左欄重抓。 */
  onFinished?: () => void;
  focus?: boolean; onFocus?: (on: boolean) => void;
  /** analyst 那一步完成(結構資料有了):外面重抓 map。 */
  onAnalysed?: () => void;
  /** 稿上顯示的是哪篇、是不是最新版、原文(邊說邊畫線要在最新版原文裡找引文)。 */
  onPaper?: (p: { slug: string; latest: boolean; text: string }) => void;
  /** 交新版成功(same = 跟最新版一字不差、沒有新增版本;version = 交成/對到的那一版)。 */
  onNewVersion?: (r: { same: boolean; version: number; analyzing: boolean }) => void;
}) {
  const t = useT();
  const [, setSearch] = useSearchParams();
  const [work, setWork] = useState<WorkDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [resumeErr, setResumeErr] = useState<string | null>(null);
  const [all, setAll] = useState(false);   // 「所有版本」浮層
  const lang = useLang();
  const flow = usePaperFlow();
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
  useEffect(() => { setWork(null); setErr(null); setAll(false); }, [slug, version]);
  // 所有版本浮層:開了聚焦第一列;點外面關
  const listRef = useRef<HTMLUListElement>(null);
  useEffect(() => {
    if (!all) return;
    listRef.current?.querySelector("button")?.focus();
    const onDown = (e: MouseEvent) => {
      const el = e.target as Element;
      if (!listRef.current?.contains(el) && !el.closest?.(".paper-vers")) setAll(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [all]);
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
  const history = work.history ?? work.versions.map(n => ({ n, at: 0, analysed: false, noted: false }));
  const dot = (n: number) => dotOf(history.find(h => h.n === n) ?? { analysed: false, noted: false }, n === latest ? work.state : undefined);
  const shown = shownVersions(work.versions, work.version);
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

  const { draft } = submit;
  const est = draft?.estimate;
  return (
    <div className="reader">
      <DropSheet next={latest + 1} onFile={f => { if (!submit.busy) void submit.fromFile(f); }} />
      <header className="paper-top">
        <h1 className="paper-h">{work.title}</h1>
        <div className="paper-vers" role="group" aria-label={t("paper.versions")}>
          {shown.more && (
            <button type="button" className="ib" aria-label={t("paper.allVersions")} title={t("paper.allVersions")}
              aria-expanded={all} onClick={() => setAll(a => !a)}><Icon name="dots" /></button>
          )}
          {shown.list.map(n => (
            <button key={n} type="button" className="paper-v" aria-pressed={n === work.version} onClick={() => pickVersion(n)}>
              <VDot d={dot(n)} />v{n}
            </button>
          ))}
          {all && (
            <ul className="dash-float paper-vlist" role="dialog" aria-label={t("paper.allVersions")} ref={listRef}
              onKeyDown={e => { if (e.key === "Escape") { e.stopPropagation(); setAll(false); } }}>
              {history.map(h => (
                <li key={h.n}><button type="button" onClick={() => { setAll(false); pickVersion(h.n); }}>
                  <VDot d={dot(h.n)} /><span>v{h.n}</span><span className="vdot-when">{whenLabel(h.at, Date.now() / 1000, lang)}</span>
                </button></li>
              ))}
            </ul>
          )}
        </div>
        <button type="button" className="ib" aria-label={t("newver.open")} title={t("newver.open")}
          onClick={() => fileInput.current?.click()}><Icon name="stack" /></button>
        <input ref={fileInput} type="file" accept=".md,.txt" hidden
          onChange={e => { const f = e.target.files?.[0]; e.target.value = ""; if (f && !submit.busy) void submit.fromFile(f); }} />
        {work.version !== latest && (
          <span className="paper-oldpill">{t("paper.old")}
            <button type="button" className="ib" aria-label={t("paper.latest")} title={t("paper.latest")}
              onClick={() => pickVersion(latest)}><Icon name="back" /></button>
          </span>
        )}
        {analyzing
          ? <Running jobId={work.job_id!} state={work.state} sseStep={job.step} onStopped={() => { setRev(r => r + 1); onFinished?.(); }} />
          : stateText(work.state) && <span className="paper-state" role="status">{t(stateText(work.state)!)}</span>}
        {STOPPED.includes(work.state) && <button type="button" className="paper-resume" onClick={() => start(() => api.startJob(slug, { resumeOnly: true }))}>{t("paper.resume")}</button>}
        {work.version === latest && UNANALYZED.includes(work.state) && (
          <button type="button" className="paper-resume" onClick={() => start(() => api.startJob(slug))}>{t("newver.analyze")}</button>
        )}
        {resumeErr && <span className="paper-state" role="alert">{t(errorMessage(resumeErr))}</span>}
        <div className="set-seg paper-flow" role="group" aria-label={t("set.flow")}>
          {(["v", "h"] as const).map(f => (
            <button key={f} type="button" aria-pressed={flow === f} aria-label={t(`flow.${f}`)} title={t(`flow.${f}`)}
              onClick={() => setPaperFlow(f)}><Icon name={f === "v" ? "vert" : "hori"} /></button>
          ))}
        </div>
        {onFocus && (
          <button type="button" className="ib" aria-pressed={focus} aria-label={t("focus.on")} title={t("focus.on")}
            onClick={() => onFocus(!focus)}><Icon name="focus" /></button>
        )}
        {analyzing && <i className="paper-track" aria-hidden="true" />}
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
      <Paper text={work.text} title={work.title} marks={marks} drawing={drawing} onBring={onQuote}
        old={work.version !== latest} obs={obs} />
    </div>
  );
}

function Running({ jobId, state, sseStep, onStopped }: {
  jobId: number; state: string; sseStep: string | null; onStopped: () => void;
}) {
  const t = useT();
  const [since, setSince] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => setSince(null), [jobId]);
  useEffect(() => {
    let live = true;
    api.job(jobId).then(j => { if (live && j.state === "running") setSince(j.created_at); }, () => {});
    return () => { live = false; };
  }, [jobId, sseStep]);
  useEffect(() => {
    if (since === null) return;
    setNow(Date.now() / 1000);
    const id = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(id);
  }, [since]);
  const stop = () => { api.cancelJob(jobId).catch(() => {}).finally(onStopped); };
  return (
    <span className="running">
      <span role="status">{t(stepOf(sseStep, state) === "notes" ? "run.notes" : "run.observe")}</span>
      {since !== null && <span className="t">{clock(now - since)}</span>}
      <button type="button" className="ib" aria-label={t("run.stop")} title={t("run.stop")} onClick={stop}><Icon name="stop" /></button>
    </span>
  );
}
