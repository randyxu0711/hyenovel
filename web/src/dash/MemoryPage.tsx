import { useCallback, useEffect, useRef, useState } from "react";
import { api, DashError, type MemoryList, type WorkOverview } from "./api";
import { errorMessage, useT } from "./i18n";
import Icon from "./Icon";
import MemoryGroups, { chainsOf, type Act, type Reload } from "./MemoryGroups";
import MemoryPending from "./MemoryPending";

function PriorSwitch({ fail }: { fail: (e: unknown) => void }) {
  const t = useT();
  const [on, setOn] = useState<boolean | null>(null);
  useEffect(() => { api.priorEnabled().then(setOn, () => setOn(null)); }, []);
  if (on === null) return null;
  const pick = async (v: boolean) => {
    if (v === on) return;
    try { await api.setPriorEnabled(v); setOn(v); } catch (e) { fail(e); }
  };
  return (
    <div className="dash-mem-switch">
      <span>{t("memory.priorSwitch")}</span>
      <div className="set-seg" role="group" aria-label={t("memory.priorSwitch")}>
        {([true, false] as const).map(v => (
          <button key={String(v)} type="button" aria-pressed={on === v} onClick={() => void pick(v)}>
            {t(v ? "memory.on" : "memory.off")}
          </button>
        ))}
      </div>
    </div>
  );
}

const noop = () => {};

export default function MemoryPage({ onPending = noop }: { onPending?: (n: number) => void }) {
  const t = useT();
  const [data, setData] = useState<MemoryList | null>(null);
  const [works, setWorks] = useState<WorkOverview[]>([]);
  const [code, setCode] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const fail = (e: unknown) => setCode(e instanceof DashError ? e.code : "unknown");
  const reloadMemories = useCallback(() => api.memories().then(setData), []);
  const reloadWorks = useCallback(() => api.memoryWorks().then(setWorks), []);
  useEffect(() => { reloadMemories().catch(fail); reloadWorks().catch(() => setWorks([])); }, [reloadMemories, reloadWorks]);

  const acting = useRef(false);
  const act: Act = async (fn, reload: Reload = "memories") => {
    if (acting.current) return false;
    acting.current = true;
    try {
      await fn();
    } catch (e) {
      fail(e);
      return false;
    } finally { acting.current = false; }
    setCode(null);
    if (reload === "memories") await reloadMemories().catch(fail);
    if (reload === "works") await reloadWorks().catch(fail);
    return true;
  };

  const archived = data ? chainsOf(data.memories).filter(c => !c.live) : [];
  return (
    <div className="dash-mem">
      <MemoryPending onChange={() => void reloadMemories().catch(fail)} onCount={onPending} />
      {code && <p role="alert">{t(errorMessage(code))}</p>}
      {data && <MemoryGroups data={data} works={works} act={act} />}
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
      <PriorSwitch fail={fail} />
    </div>
  );
}
