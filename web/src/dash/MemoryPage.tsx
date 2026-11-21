import { useCallback, useEffect, useRef, useState } from "react";
import { api, DashError, type MemoryList, type WorkOverview } from "./api";
import { errorMessage, useT } from "./i18n";
import MemoryGroups, { chainsOf, type Act, type Reload, type Target } from "./MemoryGroups";
import MemoryPending, { type Saved } from "./MemoryPending";

function Switch({ label, on, onLabel, pick }: { label: string; on: boolean; onLabel: string; pick: (v: boolean) => void }) {
  const t = useT();
  return (
    <div className="dash-mem-switch">
      <span>{label}</span>
      <div className="set-seg" role="group" aria-label={label}>
        {([true, false] as const).map(v => (
          <button key={String(v)} type="button" aria-pressed={on === v} onClick={() => { if (v !== on) pick(v); }}>
            {v ? onLabel : t("memory.off")}
          </button>
        ))}
      </div>
    </div>
  );
}

function useSetting(get: () => Promise<boolean>, set: (v: boolean) => Promise<void>, fail: (e: unknown) => void, after?: () => void) {
  const [on, setOn] = useState<boolean | null>(null);
  useEffect(() => { get().then(setOn, () => setOn(null)); }, [get]);
  const pick = async (v: boolean) => {
    try { await set(v); setOn(v); after?.(); } catch (e) { fail(e); }
  };
  return [on, pick] as const;
}

const noop = () => {};

export default function MemoryPage({ onPending = noop, toPending = false }: { onPending?: (n: number) => void; toPending?: boolean }) {
  const t = useT();
  const [data, setData] = useState<MemoryList | null>(null);
  const [works, setWorks] = useState<WorkOverview[] | null>(null);
  const [code, setCode] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const fail = (e: unknown) => setCode(e instanceof DashError ? e.code : "unknown");
  const reloadMemories = useCallback(() => api.memories().then(setData), []);
  const reloadWorks = useCallback(() => api.memoryWorks().then(setWorks), []);
  useEffect(() => { reloadMemories().catch(fail); reloadWorks().catch(fail); }, [reloadMemories, reloadWorks]);

  const acting = useRef(false);
  const act: Act = async (fn, reload: Reload = "memories") => {
    if (acting.current) return false;
    acting.current = true;
    let ok = true;
    try {
      await fn();
      setCode(null);
    } catch (e) {
      fail(e);
      ok = false;
    }
    try {
      if (reload === "memories") await reloadMemories().catch(fail);
      if (reload === "works") await reloadWorks().catch(fail);
    } finally { acting.current = false; }
    return ok;
  };

  const [pendKey, setPendKey] = useState(0);
  const [goto, setGoto] = useState<Target | null>(null);
  const [bump, setBump] = useState<Target | null>(null);
  const mark = (set: (t: Target | null) => void) => (s: Saved) => set({ ...s, n: Date.now() });
  const [prior, setPrior] = useSetting(api.priorEnabled, api.setPriorEnabled, fail);
  const [suggest, setSuggest] = useSetting(api.suggestEnabled, api.setSuggestEnabled, fail, () => setPendKey(k => k + 1));
  const archived = data ? chainsOf(data.memories).filter(c => !c.live) : [];
  return (
    <div className="dash-mem">
      <MemoryPending key={pendKey} onChange={() => void reloadMemories().catch(fail)} onCount={onPending}
        onSaved={mark(setBump)} onGoto={mark(setGoto)} focus={toPending} />
      {code && <p role="alert">{t(errorMessage(code))}</p>}
      {data && works && <MemoryGroups data={data} works={works} act={act} goto={goto} bump={bump} />}
      <footer className="dash-mem-foot">
        {prior !== null && <Switch label={t("memory.priorSwitch")} on={prior} onLabel={t("memory.on")} pick={v => void setPrior(v)} />}
        {suggest !== null && <Switch label={t("memory.suggestSwitch")} on={suggest} onLabel={t("memory.suggestOn")} pick={v => void setSuggest(v)} />}
        {archived.length > 0 && (
          <button type="button" className="dash-pend-lnk dash-mem-arch" aria-expanded={showArchived} onClick={() => setShowArchived(s => !s)}>
            {t("memory.archived", { n: archived.length })}
          </button>
        )}
        {showArchived && archived.length > 0 && (
          <ul className="dash-mem-old dash-mem-archl">
            {archived.map(c => {
              const last = c.rows[c.rows.length - 1];
              return (
                <li key={last.root}>
                  <p>{last.text}</p>
                  <button type="button" className="dash-set-opt" onClick={() => void act(() => api.revertMemory(last.id))}>{t("memory.revert")}</button>
                </li>
              );
            })}
          </ul>
        )}
      </footer>
    </div>
  );
}
