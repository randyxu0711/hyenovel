import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, DashError, type Memory, type MemoryList, type MemoryScope, type Work } from "./api";
import { cpLength } from "./cp";
import { errorMessage, useT } from "./i18n";
import Icon from "./Icon";
import { MAX_CHAT } from "./useTalk";

type Chain = { live: Memory | null; rows: Memory[] };
type Group = { key: string; name: string; cap: number; chains: Chain[] };
type Act = (fn: () => Promise<unknown>) => Promise<boolean>;

function chainsOf(memories: Memory[]): Chain[] {
  const byRoot = new Map<number, Memory[]>();
  for (const m of memories) byRoot.set(m.root, [...(byRoot.get(m.root) ?? []), m]);
  return [...byRoot.values()].map(rows => ({ rows, live: rows.find(m => m.invalidated_at === null) ?? null }));
}

function groupsOf(chains: Chain[], caps: MemoryList["caps"], authorName: string): Group[] {
  const groups = new Map<string, Group>();
  for (const c of chains) {
    if (!c.live) continue;
    const m = c.live;
    const key = m.scope === "author" ? "" : m.slug!;
    const name = m.scope === "author" ? authorName : m.title ?? m.slug!;
    const cap = m.scope === "author" ? caps.author : caps.work;
    if (!groups.has(key)) groups.set(key, { key, name, cap, chains: [] });
    groups.get(key)!.chains.push(c);
  }
  return [...groups.values()].sort((a, b) => (a.key ? 1 : 0) - (b.key ? 1 : 0));
}

function Row({ chain, act }: { chain: Chain; act: Act }) {
  const t = useT();
  const m = chain.live!;
  const [editing, setEditing] = useState<string | null>(null);
  const [history, setHistory] = useState(false);
  const old = chain.rows.filter(r => r.id !== m.id).reverse();
  const save = async () => { if (await act(() => api.editMemory(m.id, editing!))) setEditing(null); };
  return (
    <li className="dash-mem-row">
      {editing === null ? <p>{m.text}</p> : (
        <textarea aria-label={t("memory.text")} rows={3} maxLength={MAX_CHAT} value={editing}
          onChange={e => setEditing(e.target.value)} />
      )}
      {m.quote && m.slug && m.session
        ? <Link className="dash-mem-source" to={`/w/${encodeURIComponent(m.slug)}?s=${encodeURIComponent(m.session)}`}>{m.quote}</Link>
        : <span className="dash-mem-source">{t("memory.typed")}</span>}
      <div className="dash-mem-bar">
        {editing === null
          ? <button type="button" className="ib" aria-label={t("memory.edit")} title={t("memory.edit")} onClick={() => setEditing(m.text)}><Icon name="edit" /></button>
          : <>
              <button type="button" className="ib" aria-label={t("memory.cancel")} title={t("memory.cancel")} onClick={() => setEditing(null)}><Icon name="close" /></button>
              <button type="button" className="dash-key" disabled={!editing.trim()} onClick={() => void save()}>{t("memory.store")}</button>
            </>}
        <button type="button" className="ib" aria-label={t("memory.archive")} title={t("memory.archive")}
          onClick={() => void act(() => api.archiveMemory(m.id))}><Icon name="box" /></button>
        {old.length > 0 && (
          <button type="button" className="ib dash-mem-hist" aria-label={t("memory.history")} title={t("memory.history")} aria-expanded={history}
            onClick={() => setHistory(h => !h)}><Icon name="history" /><span className="dash-dm">{old.length}</span></button>
        )}
      </div>
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

function AddForm({ act }: { act: Act }) {
  const t = useT();
  const [text, setText] = useState("");
  const [scope, setScope] = useState<MemoryScope>("author");
  const [slug, setSlug] = useState("");
  const [works, setWorks] = useState<Work[]>([]);
  useEffect(() => { api.works().then(setWorks, () => setWorks([])); }, []);
  const ready = text.trim() && (scope === "author" || slug);
  const add = async () => {
    const body = scope === "work" ? { scope, text, slug } : { scope, text };
    if (await act(() => api.remember(body))) setText("");
  };
  return (
    <form className="dash-mem-add" onSubmit={e => { e.preventDefault(); if (ready) void add(); }}>
      <textarea aria-label={t("memory.new")} placeholder={t("memory.new")} rows={2} maxLength={MAX_CHAT} value={text} onChange={e => setText(e.target.value)} />
      <div className="dash-mem-bar">
        <div className="set-seg" role="group" aria-label={t("memory.new")}>
          {(["author", "work"] as const).map(s => (
            <button key={s} type="button" aria-pressed={scope === s} onClick={() => setScope(s)}>
              {t(s === "author" ? "memory.scope.author" : "memory.scope.work")}
            </button>
          ))}
        </div>
        {scope === "work" && (
          <select aria-label={t("memory.pickWork")} value={slug} onChange={e => setSlug(e.target.value)}>
            <option value="" />
            {works.map(w => <option key={w.slug} value={w.slug}>{w.title}</option>)}
          </select>
        )}
        <button type="submit" className="dash-key dash-mem-go" disabled={!ready}>{t("memory.add")}</button>
      </div>
    </form>
  );
}

/** 記憶頁:生效中的依作者、各篇分組;封存的收在最後。 */
export default function MemoryPage() {
  const t = useT();
  const [data, setData] = useState<MemoryList | null>(null);
  const [code, setCode] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const fail = (e: unknown) => setCode(e instanceof DashError ? e.code : "unknown");
  const reload = useCallback(() => api.memories().then(setData), []);
  useEffect(() => { reload().catch(fail); }, [reload]);

  const acting = useRef(false);
  const act: Act = async fn => {
    if (acting.current) return false;
    acting.current = true;
    try {
      await fn();
    } catch (e) {
      fail(e);
      return false;
    } finally { acting.current = false; }
    setCode(null);
    await reload().catch(fail);
    return true;
  };

  const chains = data ? chainsOf(data.memories) : [];
  const groups = data ? groupsOf(chains, data.caps, t("memory.scope.author")) : [];
  const archived = chains.filter(c => !c.live);
  return (
    <div className="dash-mem">
      {code && <p role="alert">{t(errorMessage(code))}</p>}
      {data && groups.length === 0 && <p className="dash-mem-empty">{t("memory.empty")}</p>}
      {groups.map(g => {
        const used = g.chains.reduce((n, c) => n + cpLength(c.live!.text), 0);
        return (
        <div key={g.key} role="group" aria-label={g.name} className="dash-mem-group">
          <h2>{g.name}<span className="dash-mem-use"><i style={{ width: `${Math.min(100, (used / g.cap) * 100)}%` }} /></span><span className="dash-dm">{used}/{g.cap}</span></h2>
          <ul>{g.chains.map(c => <Row key={c.rows[0].root} chain={c} act={act} />)}</ul>
        </div>
        );
      })}
      <AddForm act={act} />
      {archived.length > 0 && (
        <button type="button" className="dash-set-opt" aria-expanded={showArchived} onClick={() => setShowArchived(s => !s)}>
          {t("memory.archived", { n: archived.length })}
        </button>
      )}
      {showArchived && archived.length > 0 && (
        <ul className="dash-mem-old">
          {archived.map(c => {
            const last = c.rows[c.rows.length - 1];
            return (
              <li key={last.root}>
                <p>{last.text}</p>
                <button type="button" className="ib" aria-label={t("memory.revert")} title={t("memory.revert")}
                  onClick={() => void act(() => api.revertMemory(last.id))}><Icon name="back" /></button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
