import { useEffect, useState } from "react";
import { api, DashError, type RecentSession, type SessionDetail } from "./api";
import Avatar from "./Avatar";
import { errorMessage, localized, setLang, useLang, useT, type Lang } from "./i18n";
import { loadPaperSize, PAPER_SIZE_KEY, type PaperSize } from "./Paper";
import { selectTheme, setMode, useThemeState, type ModePref } from "./theme";
import { useCharacters } from "./useCharacters";
import { companionId, setCompanion } from "./useTalk";

const MODES: { pref: ModePref; key: "set.mode.system" | "set.mode.light" | "set.mode.dark" }[] = [
  { pref: "system", key: "set.mode.system" }, { pref: "light", key: "set.mode.light" }, { pref: "dark", key: "set.mode.dark" },
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
                <p className="chat-who"><Avatar character={c} size={22} /><b style={{ color: c.colors[mode].text }}>{localized(c.name, lang)}</b></p>
                <p className="chat-text">{turn.text}</p>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

export default function Settings() {
  const t = useT();
  const lang = useLang();
  const chars = useCharacters();
  const { themes, theme, pref, mode } = useThemeState();
  const [size, setSize] = useState<PaperSize>(loadPaperSize);
  const [who, setWho] = useState(() => companionId(chars));
  const pickSize = (s: PaperSize) => {
    try { localStorage.setItem(PAPER_SIZE_KEY, s); } catch { /* 存不了就只這次有效 */ }
    setSize(s);
  };
  return (
    <section className="dash-settings" aria-label={t("rail.settings")}>
      <h1 className="dash-h">{t("rail.settings")}</h1>

      <section aria-labelledby="set-look">
        <h2 id="set-look">{t("set.look")}</h2>
        <div className="dash-set-row"><span>{t("set.mode")}</span>
          {MODES.map(m => (
            <button key={m.pref} type="button" className="dash-set-opt" aria-pressed={pref === m.pref}
              onClick={() => setMode(m.pref)}>{t(m.key)}</button>
          ))}
        </div>
        <div className="dash-set-row"><span>{t("set.palette")}</span>
          {themes.map(th => (
            <button key={th.id} type="button" className="dash-set-opt" aria-pressed={theme?.id === th.id}
              onClick={() => selectTheme(th.id)}>
              <span className="dash-set-chip" style={{ background: th[mode].paper }} aria-hidden="true" />
              {localized(th.name, lang)}
            </button>
          ))}
        </div>
        <div className="dash-set-row"><span>{t("set.lang")}</span>
          {LANGS.map(l => (
            <button key={l.lang} type="button" className="dash-set-opt" aria-pressed={lang === l.lang}
              onClick={() => setLang(l.lang)}>{l.label}</button>
          ))}
        </div>
        <div className="dash-set-row"><span>{t("set.paper")}</span>
          {SIZES.map(s => (
            <button key={s.size} type="button" className="dash-set-opt" aria-pressed={size === s.size}
              onClick={() => pickSize(s.size)}>{t(s.key)}</button>
          ))}
        </div>
      </section>

      <section aria-labelledby="set-who">
        <h2 id="set-who">{t("set.companions")}</h2>
        {chars.list.map(c => (
          <label key={c.id} className="dash-set-who">
            <input type="radio" name="default-companion" checked={who === c.id}
              onChange={() => { setCompanion(c.id); setWho(c.id); }} />
            <Avatar character={c} size={28} />
            <span>{localized(c.name, lang)} <small>{localized(c.line, lang)}</small> · {t("set.default")}</span>
          </label>
        ))}
      </section>

      <section aria-labelledby="set-data">
        <h2 id="set-data">{t("set.data")}</h2>
        <Archive />
      </section>
    </section>
  );
}
