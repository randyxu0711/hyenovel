import { useEffect, useState } from "react";
import { api, DashError } from "./api";
import Avatar from "./Avatar";
import { errorMessage, localized, setLang, useLang, useT, type MsgKey } from "./i18n";
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

function Shell({ chars }: { chars: Characters }) {
  const t = useT();
  const { mode } = useThemeState();
  const me = chars.byId(null);
  useEffect(() => applySignature(me, mode), [me, mode]);
  return (
    <div className="dash">
      <nav className="dash-rail" aria-label={t("rail.works")}>
        <div className="dash-brand"><Avatar character={me} size={30} /><b>{t("brand")}</b></div>
        <button type="button" className="dash-feed">{t("rail.feed")}</button>
        <Keys />
      </nav>
      <main className="dash-desk">{t("desk.empty")}</main>
      <aside className="dash-talk">{t("talk.empty")}</aside>
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
