import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api, DashError, type RecentSession, type SessionDetail } from "./api";
import Blob from "./Blob";
import Icon, { type IconName } from "./Icon";
import { errorMessage, localized, setLang, useLang, useT, type Lang, type MsgKey } from "./i18n";
import MemoryPage from "./MemoryPage";
import { setPaperFlow, usePaperFlow } from "./paperFlow";
import { loadPaperSize, PAPER_SIZE_KEY, type PaperSize } from "./Paper";
import { speakerChanges } from "./Talk";
import { selectTheme, setMode, useThemeState, type ModePref } from "./theme";
import { useCharacters } from "./useCharacters";
import { companionId, setCompanion } from "./useTalk";

const MODES: { pref: ModePref; key: MsgKey; icon: IconName }[] = [
  { pref: "system", key: "set.mode.system", icon: "auto" }, { pref: "light", key: "set.mode.light", icon: "sun" },
  { pref: "dark", key: "set.mode.dark", icon: "moon" },
];
const SIZES: { size: PaperSize; key: "set.size.s" | "set.size.m" | "set.size.l" }[] = [
  { size: "s", key: "set.size.s" }, { size: "m", key: "set.size.m" }, { size: "l", key: "set.size.l" },
];
const LANGS: { lang: Lang; label: string }[] = [{ lang: "zh-Hant", label: "繁體中文" }, { lang: "en", label: "English" }];

/** 舊討論封存:唯讀。先數量,打開後列出,點一局看逐字;沒有輸入框。 */
function Archive() {
  const t = useT();
  const lang = useLang();
  const chars = useCharacters();
  const { mode } = useThemeState();
  const [rows, setRows] = useState<RecentSession[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  useEffect(() => {
    let live = true;
    api.recentSessions(100, { legacy: true }).then(
      r => { if (live) setRows(r.filter(s => s.legacy)); },
      e => { if (live) setErr(e instanceof DashError ? e.code : "unknown"); });
    return () => { live = false; };
  }, []);
  const show = (id: string) => api.session(id).then(setDetail, e => setErr(e instanceof DashError ? e.code : "unknown"));
  const who = speakerChanges(detail?.turns ?? [], chars.byId);
  return (
    <>
      {rows && <p>{t("set.legacy", { n: rows.length })}</p>}
      {err && <p role="alert">{t(errorMessage(err))}</p>}
      {rows && rows.length > 0 && (
        <button type="button" className="dash-set-opt" aria-expanded={open}
          onClick={() => { setOpen(o => !o); setDetail(null); }}>
          {t(open ? "set.closeArchive" : "set.openArchive")}
        </button>
      )}
      {open && !detail && (
        <div className="dash-set-archive">
          <p>{t("set.archiveNote")}</p>
          <ul>
            {rows!.map(s => (
              <li key={s.session}>
                <button type="button" className="dash-set-opt" onClick={() => void show(s.session)}>
                  <b>{s.title}</b> <span>{s.preview}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {open && detail && (
        <div className="dash-set-log">
          <button type="button" className="dash-set-opt" onClick={() => setDetail(null)}>{t("set.back")}</button>
          <h3>{detail.title}</h3>
          {detail.turns.map((turn, i) => {
            if (turn.role !== "assistant") return <div key={i} className="chat-me"><p>{turn.text}</p></div>;
            const c = chars.byId(turn.character, turn.mode);
            return (
              <div key={i} className="chat-turn">
                {who.has(i) && <p className="chat-who"><Blob character={c} size={22} /><b style={{ color: c.colors[mode].text }}>{localized(c.name, lang)}</b></p>}
                <p className="chat-text">{turn.text}</p>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

export type SettingsSection = "look" | "companions" | "memory" | "archive";
const SECTIONS: { id: SettingsSection; key: MsgKey; icon: IconName }[] = [
  { id: "look", key: "set.look", icon: "look" }, { id: "companions", key: "set.companions", icon: "person" },
  { id: "memory", key: "set.memory", icon: "memory" }, { id: "archive", key: "set.archive", icon: "box" },
];

/** 設定分區:回去鍵 + 各分區。書架在設定頁時畫它;窄螢幕由 Settings 畫在內容上方(橫排)。 */
export function SettingsNav({ section, onPick, back }: {
  section: SettingsSection; onPick: (s: SettingsSection) => void; back: { label: string; to: string };
}) {
  const t = useT();
  const nav = useNavigate();
  return (
    <div className="set-nav" role="group" aria-label={t("set.sections")}>
      <button type="button" className="set-back" aria-label={back.label} title={back.label} onClick={() => nav(back.to)}>
        <Icon name="back" /><span>{back.label}</span>
      </button>
      {SECTIONS.map(x => (
        <button key={x.id} type="button" aria-label={t(x.key)} title={t(x.key)} aria-current={section === x.id ? "true" : undefined}
          onClick={() => onPick(x.id)}>
          <Icon name={x.icon} /><span>{t(x.key)}</span>
        </button>
      ))}
    </div>
  );
}

/** 一列:左標籤、右控制。 */
function Row({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="set-row">
      <span className="set-lab">{label}{hint && <span className="set-hint">{hint}</span>}</span>
      <div className="set-ctl">{children}</div>
    </div>
  );
}

const FLOWS = [
  { flow: "v", key: "flow.v", icon: "vert" },
  { flow: "h", key: "flow.h", icon: "hori" },
] as const;

function Look() {
  const t = useT();
  const lang = useLang();
  const { themes, theme, pref, mode } = useThemeState();
  const [size, setSize] = useState<PaperSize>(loadPaperSize);
  const flow = usePaperFlow();
  const pickSize = (s: PaperSize) => {
    try { localStorage.setItem(PAPER_SIZE_KEY, s); } catch { /* 存不了就只這次有效 */ }
    setSize(s);
  };
  return (
    <div className="set-look">
      <div className="set-rows">
        <Row label={t("set.mode")}>
          <div className="set-seg" role="group" aria-label={t("set.mode")}>
            {MODES.map(m => (
              <button key={m.pref} type="button" aria-pressed={pref === m.pref} aria-label={t(m.key)} title={t(m.key)}
                onClick={() => setMode(m.pref)}><Icon name={m.icon} /></button>
            ))}
          </div>
        </Row>
        <Row label={t("set.palette")}>
          {themes.map(th => (
            <button key={th.id} type="button" className="dash-set-opt" aria-pressed={theme?.id === th.id}
              onClick={() => selectTheme(th.id)}>
              <span className="dash-set-chip" style={{ background: th[mode].paper }} aria-hidden="true" />
              {localized(th.name, lang)}
            </button>
          ))}
        </Row>
        <Row label={t("set.lang")}>
          <div className="set-seg" role="group" aria-label={t("set.lang")}>
            {LANGS.map(l => (
              <button key={l.lang} type="button" aria-pressed={lang === l.lang} onClick={() => setLang(l.lang)}>{l.label}</button>
            ))}
          </div>
        </Row>
        <Row label={t("set.flow")} hint={t("set.flowHint")}>
          <div className="set-seg" role="group" aria-label={t("set.flow")}>
            {FLOWS.map(f => (
              <button key={f.flow} type="button" aria-pressed={flow === f.flow} aria-label={t(f.key)} title={t(f.key)}
                onClick={() => setPaperFlow(f.flow)}><Icon name={f.icon} /></button>
            ))}
          </div>
        </Row>
        <Row label={t("set.paper")}>
          <div className="set-seg" role="group" aria-label={t("set.paper")}>
            {SIZES.map(s => (
              <button key={s.size} type="button" aria-pressed={size === s.size} onClick={() => pickSize(s.size)}>{t(s.key)}</button>
            ))}
          </div>
        </Row>
      </div>
      <figure className="set-prev" aria-label={t("set.preview")}>
        <p className="set-mini" data-size={size}>{t("set.sample")}</p>
      </figure>
    </div>
  );
}

function Companions() {
  const t = useT();
  const lang = useLang();
  const chars = useCharacters();
  const [who, setWho] = useState(() => companionId(chars));
  return (
    <div className="set-rows">
      {chars.list.map(c => (
        <label key={c.id} className="dash-set-who">
          <input type="radio" name="default-companion" checked={who === c.id}
            onChange={() => { setCompanion(c.id); setWho(c.id); }} />
          <Blob character={c} size={28} />
          <span>{localized(c.name, lang)} <small>{localized(c.line, lang)}</small>{who === c.id && ` · ${t("set.default")}`}</span>
        </label>
      ))}
    </div>
  );
}

/** 設定內容:只畫目前分區。分區導覽在書架(窄螢幕時 nav 由外面給,畫在內容上方)。 */
export default function Settings({ section, nav }: { section: SettingsSection; nav: ReactNode | null }) {
  const t = useT();
  const title = t(SECTIONS.find(x => x.id === section)!.key);
  return (
    <section className="dash-settings" aria-label={t("rail.settings")} data-section={section}>
      {nav}
      <h1 className="dash-h">{title}</h1>
      {section === "look" && <Look />}
      {section === "companions" && <Companions />}
      {section === "memory" && <MemoryPage />}
      {section === "archive" && <Archive />}
    </section>
  );
}
