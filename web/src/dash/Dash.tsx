import { useEffect, useState } from "react";
import { api, DashError } from "./api";
import Avatar from "./Avatar";
import { errorMessage, localized, setLang, useLang, useT, type MsgKey } from "./i18n";
import Feed from "./Feed";
import Rail from "./Rail";
import Reader from "./Reader";
import Seat from "./Seat";
import Talk from "./Talk";
import { useTalk } from "./useTalk";
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
  const lang = useLang();
  const [slug, setSlug] = useState<string | null>(null);
  const [session, setSession] = useState<string | null>(null);
  const [quotes, setQuotes] = useState<string[]>([]);
  const [open, setOpen] = useState(true);
  const [feeding, setFeeding] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [reload, setReload] = useState(0);   // 重交已開著的那篇:Reader 要重抓
  const [notice, setNotice] = useState<string | null>(null);
  const bump = () => setRefresh(n => n + 1);
  const talk = useTalk(slug, session);
  const me = chars.byId(talk.whoId);
  useEffect(() => applySignature(me, mode), [me, mode]);
  const [pane, setPane] = useState<Pane>("works");
  const pick = (s: string, sess: string | null = null) => { setSlug(s); setSession(sess); setQuotes([]); setNotice(null); setPane("desk"); };
  return (
    <div className="dash" data-pane={pane} data-talk={open ? "open" : "closed"}>
      <div className="dash-tabs" role="tablist">
        {PANES.map(([id, key]) => (
          <button key={id} type="button" role="tab" aria-selected={pane === id} onClick={() => setPane(id)}>{t(key)}</button>
        ))}
      </div>
      <nav className="dash-rail" aria-label={t("rail.works")}>
        <div className="dash-brand"><Avatar character={me} size={30} /><b>{t("brand")}</b></div>
        <button type="button" className="dash-feed" onClick={() => setFeeding(true)}>{t("rail.feed")}</button>
        <Rail refresh={refresh} current={slug} onLoaded={ws => setSlug(cur => cur ?? ws[0]?.slug ?? null)} onPick={s => pick(s)} onPickSession={pick} />
        <Keys />
      </nav>
      <main className="dash-desk">
        {slug ? <Reader slug={slug} reload={reload} onFinished={bump} companion={localized(me.name, lang)} onQuote={q => { setQuotes(qs => qs.includes(q) ? qs : [...qs, q]); setOpen(true); setPane("talk"); }} /> : t("desk.empty")}
      </main>
      {notice && (
        <p className="dash-notice" role="status">
          {notice}
          <button type="button" aria-label={t("notice.dismiss")} onClick={() => setNotice(null)}>×</button>
        </p>
      )}
      <aside className="dash-talk">
        <Talk talk={talk} hasWork={slug !== null} quotes={quotes}
          onDropQuote={i => setQuotes(qs => qs.filter((_, j) => j !== i))}
          onSent={() => { setQuotes([]); setNotice(null); bump(); }} onCollapse={() => setOpen(false)} />
      </aside>
      {feeding && <Feed onClose={() => setFeeding(false)}
        onSubmitted={(s, existing) => { setFeeding(false); pick(s); bump(); setReload(n => n + 1); setNotice(existing ? t("feed.already") : null); }} />}
      {!open && <Seat character={me} onOpen={() => setOpen(true)} />}
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
