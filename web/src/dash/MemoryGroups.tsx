import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type DigestVersion, type Memory, type MemoryList, type MemoryScope, type WorkDigest, type WorkOverview, type WorkThread } from "./api";
import { cpLength } from "./cp";
import { useLang, useT } from "./i18n";
import Icon from "./Icon";
import { MAX_CHAT } from "./useTalk";
import { whenLabel } from "./when";

export type Reload = "memories" | "works" | "none";
export type Act = (fn: () => Promise<unknown>, reload?: Reload) => Promise<boolean>;
export type Chain = { live: Memory | null; rows: Memory[] };

type Group = {
  key: string; name: string; scope: MemoryScope; slug: string | null; archived: boolean;
  chains: Chain[]; digests: WorkDigest[]; threads: WorkThread[];
};

const chatLink = (slug: string | null, session: string) =>
  slug ? `/w/${encodeURIComponent(slug)}?s=${encodeURIComponent(session)}` : `/c/${encodeURIComponent(session)}`;

export function chainsOf(memories: Memory[]): Chain[] {
  const byRoot = new Map<number, Memory[]>();
  for (const m of memories) byRoot.set(m.root, [...(byRoot.get(m.root) ?? []), m]);
  return [...byRoot.values()].map(rows => ({ rows, live: rows.find(m => m.invalidated_at === null) ?? null }));
}

function groupsOf(chains: Chain[], works: WorkOverview[], authorName: string): Group[] {
  const base = { chains: [] as Chain[], digests: [] as WorkDigest[], threads: [] as WorkThread[], archived: false };
  const author: Group = { ...base, chains: [], key: "", name: authorName, scope: "author", slug: null };
  const bySlug = new Map<string, Group>(works.map(w => [w.slug, {
    ...base, chains: [], key: w.slug, name: w.title, scope: "work" as const, slug: w.slug, digests: w.digests, threads: w.threads,
  }]));
  const gone = new Map<string, Group>();
  for (const c of chains) {
    const m = c.live;
    if (!m) continue;
    if (m.scope === "author") { author.chains.push(c); continue; }
    const slug = m.slug!;
    const g = bySlug.get(slug) ?? gone.get(slug) ?? { ...base, chains: [], key: slug, name: m.title ?? slug, scope: "work" as const, slug, archived: true };
    if (g.archived) gone.set(slug, g);
    g.chains.push(c);
  }
  return [author, ...bySlug.values(), ...gone.values()];
}

export function Row({ chain, act, fresh = false }: { chain: Chain; act: Act; fresh?: boolean }) {
  const t = useT();
  const m = chain.live!;
  const [editing, setEditing] = useState<string | null>(null);
  const [history, setHistory] = useState(false);
  const old = chain.rows.filter(r => r.id !== m.id).reverse();
  const save = async () => { if (await act(() => api.editMemory(m.id, editing!))) setEditing(null); };
  return (
    <li className="dash-mem-row" data-mem={m.id} data-new={fresh || undefined}>
      <div className="dash-mem-line">
        {editing === null ? <p className="dash-mem-text">{m.text}</p> : (
          <textarea aria-label={t("memory.text")} rows={3} maxLength={MAX_CHAT} value={editing} autoFocus
            onChange={e => setEditing(e.target.value)}
            onKeyDown={e => { if (e.key === "Escape") { e.preventDefault(); setEditing(null); } }} />
        )}
        <div className="dash-mem-bar">
          {m.quote && m.session && (
            <Link className="ib" to={chatLink(m.slug, m.session)} aria-label={t("memory.fromChat")} title={t("memory.fromChat")}><Icon name="talk" /></Link>
          )}
          {old.length > 0 && (
            <button type="button" className="ib dash-mem-hist" aria-label={t("memory.history")} title={t("memory.history")} aria-expanded={history}
              onClick={() => setHistory(h => !h)}><Icon name="history" /><span className="dash-dm">{old.length}</span></button>
          )}
          {editing === null
            ? <button type="button" className="ib" aria-label={t("memory.edit")} title={t("memory.edit")} onClick={() => setEditing(m.text)}><Icon name="edit" /></button>
            : <>
                <button type="button" className="ib" aria-label={t("memory.cancel")} title={t("memory.cancel")} onClick={() => setEditing(null)}><Icon name="close" /></button>
                <button type="button" className="dash-key" disabled={!editing.trim()} onClick={() => void save()}>{t("memory.store")}</button>
              </>}
          <button type="button" className="ib" aria-label={t("memory.archive")} title={t("memory.archive")}
            onClick={() => void act(() => api.archiveMemory(m.id))}><Icon name="box" /></button>
        </div>
      </div>
      {m.quote && m.quote.trim() !== m.text.trim() && <blockquote className="dash-quote">{m.quote}</blockquote>}
      {history && (
        <ul className="dash-mem-old">
          {old.map(r => (
            <li key={r.id}>
              <p>{r.text}</p>
              <button type="button" className="dash-set-opt" onClick={() => void act(() => api.revertMemory(r.id))}>{t("memory.backTo")}</button>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function ThreadRow({ x, slug, act }: { x: WorkThread; slug: string; act: Act }) {
  const t = useT();
  const stale = x.stale && !x.ended;
  return (
    <li className="dash-mg-thread" data-ended={x.ended || undefined} data-stale={stale || undefined}>
      {stale
        ? <span className="dash-mg-ring" aria-hidden="true" />
        : <button type="button" className="dash-mg-ring" aria-pressed={x.ended} aria-label={t(x.ended ? "prior.reopen" : "prior.end")}
            title={t(x.ended ? "prior.reopen" : "prior.end")} onClick={() => void act(() => api.setThreadEnded(x.id, !x.ended), "works")}>{x.ended ? "✓" : ""}</button>}
      <span className="dash-mg-q">{x.text}</span>
      {stale
        ? <span className="dash-mg-state">{t("mg.stale")}</span>
        : <Link className="ib dash-mg-go" to={chatLink(slug, x.session)} aria-label={t("prior.goto")} title={t("prior.goto")}><Icon name="goto" /></Link>}
    </li>
  );
}

function DigestRow({ d, slug, act }: { d: WorkDigest; slug: string; act: Act }) {
  const t = useT();
  const lang = useLang();
  const [full, setFull] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);
  const [versions, setVersions] = useState<DigestVersion[] | null>(null);
  const toggleHistory = async () => {
    if (versions) { setVersions(null); return; }
    await act(async () => setVersions(await api.digestVersions(d.id)), "none");
  };
  const save = async () => { if (draft && await act(() => api.editDigest(d.id, draft), "works")) setDraft(null); };
  return (
    <li className="dash-mg-digest">
      <span className="dash-mg-when">{whenLabel(d.at, Date.now() / 1000, lang)}</span>
      <div className="dash-mg-body">
        {draft === null
          ? <p className="dash-mg-sum" data-full={full || undefined} role="button" tabIndex={0} aria-expanded={full}
              onClick={() => setFull(f => !f)}
              onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setFull(f => !f); } }}>{d.text}</p>
          : <textarea aria-label={t("mg.digests")} rows={3} value={draft} autoFocus onChange={e => setDraft(e.target.value)} />}
        {versions && (
          <ul className="dash-mem-old">
            {versions.filter(v => !v.current).map(v => (
              <li key={v.id}>
                <p>{v.text}</p>
                <button type="button" className="dash-set-opt"
                  onClick={() => void act(() => api.revertDigest(v.id).then(() => setVersions(null)), "works")}>{t("mg.restore")}</button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="dash-mem-bar dash-mg-acts">
        {d.versions > 1 && (
          <button type="button" className="ib dash-mem-hist" aria-label={t("memory.history")} title={t("memory.history")} aria-expanded={!!versions}
            onClick={() => void toggleHistory()}><Icon name="history" /><span className="dash-dm">{d.versions - 1}</span></button>
        )}
        <Link className="ib" to={chatLink(slug, d.session)} aria-label={t("prior.goto")} title={t("prior.goto")}><Icon name="talk" /></Link>
        {draft === null
          ? <button type="button" className="ib" aria-label={t("memory.edit")} title={t("memory.edit")} onClick={() => setDraft(d.text)}><Icon name="edit" /></button>
          : <>
              <button type="button" className="ib" aria-label={t("memory.cancel")} title={t("memory.cancel")} onClick={() => setDraft(null)}><Icon name="close" /></button>
              <button type="button" className="dash-key" disabled={!draft.trim()} onClick={() => void save()}>{t("prior.save")}</button>
            </>}
      </div>
    </li>
  );
}

function AddRow({ scope, slug, act, start = false }: { scope: MemoryScope; slug: string | null; act: Act; start?: boolean }) {
  const t = useT();
  const [text, setText] = useState<string | null>(start ? "" : null);
  if (text === null) {
    return <button type="button" className="dash-pend-lnk dash-mg-add" onClick={() => setText("")}><Icon name="plus" />{t("mg.addOpen")}</button>;
  }
  const add = async () => {
    const body = scope === "work" ? { scope, slug: slug!, text } : { scope, text };
    if (await act(() => api.remember(body))) setText(null);
  };
  return (
    <form className="dash-mem-add" onSubmit={e => { e.preventDefault(); if (text.trim()) void add(); }}>
      <textarea aria-label={t("memory.new")} placeholder={t("memory.new")} rows={2} maxLength={MAX_CHAT} value={text} autoFocus={!start}
        onChange={e => setText(e.target.value)}
        onKeyDown={e => { if (e.key === "Escape") { e.preventDefault(); setText(null); } }} />
      <div className="dash-mem-bar">
        <button type="button" className="ib" aria-label={t("memory.cancel")} title={t("memory.cancel")} onClick={() => setText(null)}><Icon name="close" /></button>
        <button type="submit" className="dash-key dash-mem-go" disabled={!text.trim()}>{t("memory.add")}</button>
      </div>
    </form>
  );
}

function Count({ icon, label, n }: { icon: React.ReactNode; label: string; n: number }) {
  if (n === 0) return <span className="dash-mg-c" />;
  return <span className="dash-mg-c" role="img" aria-label={`${label} ${n}`} title={label}>{icon}<span className="dash-dm">{n}</span></span>;
}

const OPEN_KEY = "hyenovel.memory.open";
const readOpen = (): Set<string> => {
  try { const v = JSON.parse(localStorage.getItem(OPEN_KEY) ?? "[]"); return new Set(Array.isArray(v) ? v.filter(x => typeof x === "string") : []); }
  catch { return new Set(); }
};
const writeOpen = (s: Set<string>) => { try { localStorage.setItem(OPEN_KEY, JSON.stringify([...s])); } catch { /* 存不了就不記 */ } };

export type Target = { group: string; memory: number; n: number };

const FRESH_MS = 2400;

export default function MemoryGroups({ data, works, act, goto = null, bump = null }: {
  data: MemoryList; works: WorkOverview[]; act: Act; goto?: Target | null; bump?: Target | null;
}) {
  const t = useT();
  const [open, setOpen] = useState<Set<string>>(readOpen);
  const [rest, setRest] = useState(false);
  const [fresh, setFresh] = useState<number | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const groups = groupsOf(chainsOf(data.memories), works, t("memory.scope.author"));
  const quiet = (g: Group) => g.scope === "work" && !g.archived && g.chains.length === 0 && g.threads.length === 0 && g.digests.length === 0;
  const shown = groups.filter(g => !quiet(g));
  const hidden = groups.filter(quiet);
  const flip = (k: string) => setOpen(s => { const n = new Set(s); if (!n.delete(k)) n.add(k); writeOpen(n); return n; });

  useEffect(() => {
    if (!goto) return;
    setOpen(s => { if (s.has(goto.group)) return s; const n = new Set(s); n.add(goto.group); writeOpen(n); return n; });
    if (hidden.some(g => g.key === goto.group)) setRest(true);
    setFresh(goto.memory);
    const id = window.setTimeout(() => setFresh(f => (f === goto.memory ? null : f)), FRESH_MS);
    return () => window.clearTimeout(id);
  }, [goto]);
  const landed = fresh !== null && data.memories.some(m => m.id === fresh);
  useEffect(() => {
    if (!landed) return;
    root.current?.querySelector(`[data-mem="${fresh}"]`)?.scrollIntoView?.({ block: "center", behavior: "smooth" });
  }, [landed, fresh]);

  const group = (g: Group) => {
    const mine = g.scope === "author";
    const isOpen = mine || open.has(g.key);
    const cap = mine ? data.caps.author : data.caps.work;
    const used = g.chains.reduce((n, c) => n + cpLength(c.live!.text), 0);
    const openThreads = g.threads.filter(x => !x.ended && !x.stale).length;
    const bumped = bump?.group === g.key ? bump.n : 0;
    const head = <>
      <span className="dash-mg-name" title={g.name}>{g.name}{g.archived && <span className="dash-mg-arch" role="img" aria-label={t("mg.archivedWork")} title={t("mg.archivedWork")}><Icon name="box" /></span>}</span>
      <span className="dash-mg-meta">
        {!mine && <>
          <Count key={bumped} icon={<Icon name="memory" />} label={t("mg.memories")} n={g.chains.length} />
          <Count icon={<span className="dash-mg-ring" aria-hidden="true" />} label={t("mg.threads")} n={openThreads} />
          <Count icon={<Icon name="prior" />} label={t("mg.digests")} n={g.digests.length} />
        </>}
        {(mine || (isOpen && g.chains.length > 0)) && <span className="dash-mg-use">
          <span className="dash-mem-use"><i style={{ width: `${Math.min(100, (used / cap) * 100)}%` }} /></span><span className="dash-dm">{used}/{cap}</span>
        </span>}
        {!mine && <span className="dash-mg-chev" aria-hidden="true"><Icon name="next" /></span>}
      </span>
    </>;
    return (
      <section key={g.key} role="group" aria-label={g.name} className="dash-mg-group" data-open={isOpen || undefined}
        data-mine={mine || undefined} data-bump={bumped || undefined}>
        {mine
          ? <div className="dash-mg-head" key={bumped}>{head}</div>
          : <button type="button" className="dash-mg-head" aria-expanded={isOpen} onClick={() => flip(g.key)}>{head}</button>}
        {isOpen && (
          <div className="dash-mg-body-wrap">
            {g.chains.length > 0 && (
              <div className="dash-mg-blk">
                {!mine && <h3>{t("mg.memories")}</h3>}
                <ul>{g.chains.map(c => <Row key={c.rows[0].root} chain={c} act={act} fresh={fresh === c.live!.id} />)}</ul>
              </div>
            )}
            {g.threads.length > 0 && (
              <div className="dash-mg-blk">
                <h3>{t("mg.threads")}</h3>
                <ul>{g.threads.map(x => <ThreadRow key={x.id} x={x} slug={g.slug!} act={act} />)}</ul>
              </div>
            )}
            {g.digests.length > 0 && (
              <div className="dash-mg-blk">
                <h3>{t("mg.digests")}</h3>
                <ul className="dash-mg-digests">{g.digests.map(d => <DigestRow key={d.id} d={d} slug={g.slug!} act={act} />)}</ul>
              </div>
            )}
            {!g.archived && <AddRow scope={g.scope} slug={g.slug} act={act} start={mine && g.chains.length === 0} />}
          </div>
        )}
      </section>
    );
  };
  return (
    <div className="dash-mg" ref={root}>
      {shown.map(group)}
      {hidden.length > 0 && (
        <>
          <button type="button" className="dash-pend-lnk dash-mg-rest" aria-expanded={rest} onClick={() => setRest(r => !r)}>
            {t("mg.quiet", { n: hidden.length })}
          </button>
          {rest && hidden.map(group)}
        </>
      )}
    </div>
  );
}
