import { useEffect, useState } from "react";
import { api, DashError } from "./api";
import Avatar from "./Avatar";
import { errorMessage, localized, setLang, useLang, useT, type MsgKey } from "./i18n";
import Rail from "./Rail";
import Reader from "./Reader";
import { applySignature, cycleMode, initThemes, selectTheme, useThemeState } from "./theme";
import { CharactersProvider, makeCharacters, type Characters } from "./useCharacters";
import "./dash.css";

function Keys() {
  const t = useT();
  const lang = useLang();
  const { themes, theme, pref } = useThemeState();
  return (
    <div className="dash-keys">
      <label className="dash-key">
        <span>{t("keys.theme")}</span>
        <select value={theme?.id ?? ""} onChange={e => selectTheme(e.target.value)}>
          {themes.map(th => <option key={th.id} value={th.id}>{localized(th.name, lang)}</option>)}
        </select>
      </label>
      <button type="button" className="dash-key" onClick={cycleMode}>
        <span>{t("keys.mode")}</span> {t(`mode.${pref}` as MsgKey)}
      </button>
      <button type="button" className="dash-key" onClick={() => setLang(lang === "en" ? "zh-Hant" : "en")}>
        <span>{t("keys.lang")}</span> {lang === "en" ? "中文" : "EN"}
      </button>
    </div>
  );
}

type Pane = "works" | "desk" | "talk";
const PANES: [Pane, MsgKey][] = [["works", "rail.works"], ["desk", "nav.paper"], ["talk", "rail.sessions"]];

function Shell({ chars }: { chars: Characters }) {
  const t = useT();
  const { mode } = useThemeState();
  const me = chars.byId(null);
  useEffect(() => applySignature(me, mode), [me, mode]);
  const [slug, setSlug] = useState<string | null>(null);
  const [, setSession] = useState<string | null>(null);   // Task 8 接上
  const [quote, setQuote] = useState<string | null>(null);   // Task 8 接上
  const [pane, setPane] = useState<Pane>("works");
  const pick = (s: string, sess: string | null = null) => { setSlug(s); setSession(sess); setPane("desk"); };
  return (
    <div className="dash" data-pane={pane}>
      <div className="dash-tabs" role="tablist">
        {PANES.map(([id, key]) => (
          <button key={id} type="button" role="tab" aria-selected={pane === id} onClick={() => setPane(id)}>{t(key)}</button>
        ))}
      </div>
      <nav className="dash-rail" aria-label={t("rail.works")}>
        <div className="dash-brand"><Avatar character={me} size={30} /><b>{t("brand")}</b></div>
        <button type="button" className="dash-feed">{t("rail.feed")}</button>
        <Rail current={slug} onPick={s => pick(s)} onPickSession={pick} />
        <Keys />
      </nav>
      <main className="dash-desk">
        {slug ? <Reader slug={slug} onQuote={q => { setQuote(q); setPane("talk"); }} /> : t("desk.empty")}
      </main>
      <aside className="dash-talk">{quote ?? t("talk.empty")}</aside>
    </div>
  );
}

export default function Dash() {
  const t = useT();
  const [chars, setChars] = useState<Characters | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    Promise.all([api.themes(), api.characters()]).then(([th, ch]) => {
      initThemes(th.themes, th.default);
      setChars(makeCharacters(ch.characters, ch.default));
    }, e => setErr(e instanceof DashError ? e.code : "unknown"));
  }, []);
  if (err) return <div className="dash dash-note" role="alert">{t(errorMessage(err))}</div>;
  if (!chars) return <div className="dash dash-note">{t("loading")}</div>;
  return <CharactersProvider value={chars}><Shell chars={chars} /></CharactersProvider>;
}
