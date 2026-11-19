import { useCallback, useEffect, useState } from "react";
import { api, DashError, type Prior as PriorData, type PriorSnapshot } from "./api";
import Icon from "./Icon";
import { errorMessage, useLang, useT } from "./i18n";
import { whenLabel } from "./when";

type Digest = { id: number; at: number; text: string };
type Thread = { id: number; text: string; at: number; session: string; ended: boolean; talked: boolean };

function Card({ session, digests, threads, open, onOpen, live, busy, onSkip, onEdited, onGoto, setThreads }: {
  session: string | null; digests: Digest[]; threads: Thread[]; open: boolean; onOpen: (o: boolean) => void;
  live: boolean; busy?: boolean; onSkip?: () => void; onEdited?: () => Promise<void>;
  onGoto: (session: string) => void; setThreads: (fn: (ts: Thread[]) => Thread[]) => void;
}) {
  const t = useT();
  const lang = useLang();
  const [pick, setPick] = useState(0);
  const [draft, setDraft] = useState<string | null>(null);
  const [code, setCode] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const shown = digests[Math.min(pick, digests.length - 1)];
  const open_ = threads.filter(x => !x.ended).length;
  const now = Date.now() / 1000;
  const when = (at: number) => whenLabel(at, now, lang);

  const save = async () => {
    if (draft === null || saving) return;
    setSaving(true); setCode(null);
    try {
      await api.editDigest(shown.id, draft);
      await onEdited?.();
      setDraft(null);
    } catch (e) {
      const c = e instanceof DashError ? e.code : "unknown";
      setCode(c);
      if (c === "stale-digest") await onEdited?.();
    } finally { setSaving(false); }
  };
  const toggle = async (x: Thread) => {
    setCode(null);
    try { await api.setThreadEnded(x.id, !x.ended); } catch (e) { setCode(e instanceof DashError ? e.code : "unknown"); return; }
    setThreads(ts => ts.map(y => (y.id === x.id ? { ...y, ended: !x.ended } : y)));
  };
  const untalk = async (x: Thread) => {
    if (!session) return;
    setCode(null);
    try { await api.setTalked(session, x.id, false); } catch (e) { setCode(e instanceof DashError ? e.code : "unknown"); return; }
    setThreads(ts => ts.map(y => (y.id === x.id ? { ...y, talked: false } : y)));
  };

  const line = [t("prior.title"), t("prior.count", { n: digests.length }), ...(open_ ? [`${t("prior.threads")} ${open_}`] : [])].join(" · ");
  return (
    <div className="chat-prior" data-mode={live ? "live" : "snapshot"}>
      <button type="button" className="chat-cut chat-prior-cut" aria-expanded={open} onClick={() => onOpen(!open)}>
        <Icon name="prior" /><span>{line}</span><span className="chat-prior-chev"><Icon name="next" /></span>
      </button>
      {open && shown && (
        <div className="chat-sum chat-prior-card">
          <h3>{t("prior.summary")}
            {live && (
              <span className="chat-prior-acts">
                {draft === null ? (
                  <>
                    <button type="button" className="chat-prior-lnk" disabled={busy} onClick={() => { setCode(null); setDraft(shown.text); }}>{t("prior.edit")}</button>
                    <button type="button" className="chat-prior-lnk" disabled={busy} onClick={onSkip}>{t("prior.skip")}</button>
                  </>
                ) : (
                  <>
                    <button type="button" className="chat-prior-lnk" disabled={saving || !draft.trim()} onClick={() => void save()}>{t("prior.save")}</button>
                    <button type="button" className="chat-prior-lnk" onClick={() => { setDraft(null); setCode(null); }}>{t("prior.cancel")}</button>
                  </>
                )}
              </span>
            )}
          </h3>
          {digests.length > 1 && (
            <div className="set-seg chat-prior-days" role="group" aria-label={t("prior.summary")}>
              {digests.map((d, i) => (
                <button key={d.id} type="button" aria-pressed={d === shown} disabled={draft !== null}
                  onClick={() => setPick(i)}>{when(d.at)}</button>
              ))}
            </div>
          )}
          {draft === null
            ? <p className="chat-prior-text">{shown.text}</p>
            : <textarea className="chat-prior-edit" aria-label={t("prior.summary")} value={draft} autoFocus
                onChange={e => setDraft(e.target.value)} />}
          {code && <p className="chat-prior-err" role="alert">{t(errorMessage(code))}</p>}
          {threads.length > 0 && (
            <>
              <h3>{t("prior.threads")}</h3>
              <ul>
                {threads.map(x => (
                  <li key={x.id} data-ended={x.ended || undefined}>
                    <button type="button" className="chat-prior-ring" aria-pressed={x.ended}
                      aria-label={t(x.ended ? "prior.reopen" : "prior.end")} title={t(x.ended ? "prior.reopen" : "prior.end")}
                      onClick={() => void toggle(x)}>{x.ended ? "✓" : ""}</button>
                    <span className="chat-prior-q">{x.text}<span className="chat-prior-from">{when(x.at)}</span></span>
                    {x.talked
                      ? <span className="chat-prior-state">{t("prior.talked")}
                          <button type="button" className="chat-prior-lnk" onClick={() => void untalk(x)}>{t("prior.undo")}</button></span>
                      : <button type="button" className="chat-prior-lnk" disabled={busy} onClick={() => onGoto(x.session)}>{t("prior.goto")}</button>}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Live({ slug, skipped, onSkip, onGoto, busy }: {
  slug: string; skipped: boolean; onSkip: (on: boolean) => void; onGoto: (session: string) => void; busy: boolean;
}) {
  const t = useT();
  const [data, setData] = useState<PriorData | null>(null);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [open, setOpen] = useState(true);
  const load = useCallback(() => api.prior(slug).then(d => {
    setData(d);
    setThreads(d.threads.filter(x => !x.stale).map(x => ({ ...x, ended: !!x.ended, talked: false })));
  }, () => {}), [slug]);
  useEffect(() => { setData(null); void load(); }, [load]);
  if (!data || !data.enabled || data.digests.length === 0) return null;
  if (skipped) {
    return (
      <p className="chat-cut chat-prior-off">
        <span>{t("prior.skipped")}</span>
        <button type="button" className="chat-prior-lnk" disabled={busy} onClick={() => onSkip(false)}>{t("prior.unskip")}</button>
      </p>
    );
  }
  return (
    <Card session={null} onGoto={onGoto} digests={data.digests} threads={threads} setThreads={setThreads} open={open} onOpen={setOpen}
      live busy={busy} onSkip={() => onSkip(true)} onEdited={load} />
  );
}

function Snapshot({ session, snapshot, onGoto, busy }: { session: string; snapshot: PriorSnapshot; onGoto: (session: string) => void; busy: boolean }) {
  const [threads, setThreads] = useState<Thread[]>(snapshot.threads);
  const [open, setOpen] = useState(false);
  useEffect(() => { setThreads(snapshot.threads); }, [snapshot]);
  if (snapshot.digests.length === 0) return null;
  return <Card session={session} digests={snapshot.digests} threads={threads} setThreads={setThreads} open={open} onOpen={setOpen}
    live={false} busy={busy} onGoto={onGoto} />;
}

export default function Prior(props: { onGoto: (session: string) => void; busy: boolean } & (
  | { mode: "live"; slug: string; skipped: boolean; onSkip: (on: boolean) => void }
  | { mode: "snapshot"; session: string; snapshot: PriorSnapshot | null })) {
  if (props.mode === "live") return <Live slug={props.slug} skipped={props.skipped} onSkip={props.onSkip} onGoto={props.onGoto} busy={props.busy} />;
  if (!props.snapshot) return null;
  return <Snapshot session={props.session} snapshot={props.snapshot} onGoto={props.onGoto} busy={props.busy} />;
}
