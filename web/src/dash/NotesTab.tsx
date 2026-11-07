import type { WorkMap } from "./api";
import { errorMessage, useT, type MsgKey } from "./i18n";
import Icon from "./Icon";
import Iq from "./Iq";

const KINDS = ["moved", "confused", "wondering", "opinion"];

/** 沒有筆記時,依作品(最新版)的 state 說原因。 */
function why(state: string): MsgKey {
  if (state === "running" || state === "notes-running") return "notes.running";
  if (state === "stopped" || state === "notes-stopped") return "notes.stopped";
  if (state === "ready") return "notes.legacy";
  return "notes.none";
}

/** 筆記分頁:reviewer 的備課筆記。陪讀者看不到這些。 */
export default function NotesTab({ map, state, error = null }: { map: WorkMap | null; state: string; error?: string | null }) {
  const t = useT();
  if (!map && error) return <p className="side-lede" role="alert">{t(errorMessage(error))}</p>;
  if (!map) return <p className="side-lede">{t("loading")}</p>;
  if (!map.notes) return <p className="side-lede">{t(why(state))}</p>;
  return (
    <div className="side-col">
      <p className="side-lede notes-meta" title={t("notes.lead")}><span className="dash-dm">v{map.notes_version ?? map.version}</span><Icon name="eyeOff" /><span className="vh">{t("notes.lead")}</span></p>
      {map.notes.points.map((p, i) => (
        <section key={i} className="side-note">
          {KINDS.includes(p.kind) && <p className="side-kind">{t(`notes.kind.${p.kind}` as MsgKey)}</p>}
          <h3>{p.title}</h3>
          {p.spans.length > 0 && (
            <p className="side-quotes">{p.spans.map((s, j) => <Iq key={j} span={s} version={map.version} />)}</p>
          )}
          <p>{p.body}</p>
          {p.question && <p className="side-question">{p.question}</p>}
        </section>
      ))}
    </div>
  );
}
