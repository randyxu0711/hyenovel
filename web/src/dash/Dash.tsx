import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, DashError, type Work } from "./api";
import { errorMessage, localized, useLang, useT } from "./i18n";
import Feed from "./Feed";
import Rail from "./Rail";
import Reader from "./Reader";
import Talk from "./Talk";
import { useTalk } from "./useTalk";
import { applySignature, initThemes, useThemeState } from "./theme";
import { CharactersProvider, makeCharacters, type Characters } from "./useCharacters";
import "./dash.css";

type View = "home" | "work" | "settings";

function Shell({ chars }: { chars: Characters }) {
  const t = useT();
  const { mode } = useThemeState();
  const lang = useLang();
  const nav = useNavigate();
  const { slug: routeSlug } = useParams();
  const { pathname } = useLocation();
  const [search] = useSearchParams();
  const view: View = pathname === "/settings" ? "settings" : routeSlug ? "work" : "home";
  const slug = view === "work" ? routeSlug! : null;
  const v = Number(search.get("v"));
  const version = Number.isInteger(v) && v > 0 ? v : undefined;

  // 帶進對話的引文與提示綁在它們所屬的作品上:換作品(含瀏覽器上一頁)自然看不到舊的。
  const [carried, setCarried] = useState<{ slug: string; list: string[] }>({ slug: "", list: [] });
  const [note, setNote] = useState<{ slug: string; text: string } | null>(null);
  const quotes = carried.slug === slug ? carried.list : [];
  const notice = note && note.slug === slug ? note.text : null;
  const [feeding, setFeeding] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [reload, setReload] = useState(0);   // 重交已開著的那篇:Reader 要重抓
  const [works, setWorks] = useState<Work[]>([]);
  const bump = () => setRefresh(n => n + 1);
  useEffect(() => {
    let live = true;
    api.works().then(ws => { if (live) setWorks(ws); }, () => { /* 清單載入失敗:左欄空著,閱讀區自己會顯示錯誤 */ });
    return () => { live = false; };
  }, [refresh]);

  const talk = useTalk(slug, null);
  const me = chars.byId(talk.whoId);
  useEffect(() => applySignature(me, mode), [me, mode]);
  const open = (s: string) => { setNote(null); nav(`/w/${encodeURIComponent(s)}`); };

  return (
    <div className="dash" data-view={view} data-mode={mode}>
      <Rail collapsed={view !== "home"} works={works} current={slug} onOpen={open}
        onNew={() => nav("/")} onSubmitNew={() => setFeeding(true)} />
      <main className="dash-desk">
        {view === "work" && <Reader slug={slug!} version={version} reload={reload} onFinished={bump} companion={localized(me.name, lang)}
          onQuote={q => setCarried(c => { const list = c.slug === slug ? c.list : []; return { slug: slug!, list: list.includes(q) ? list : [...list, q] }; })} />}
        {view === "home" && (works.length === 0 ? t("rail.firstDraft") : t("desk.empty"))}
        {view === "settings" && <h1 className="dash-h">{t("rail.settings")}</h1>}
      </main>
      {notice && (
        <p className="dash-notice" role="status">
          {notice}
          <button type="button" aria-label={t("notice.dismiss")} onClick={() => setNote(null)}>×</button>
        </p>
      )}
      {view === "work" && (
        <aside className="dash-talk">
          <Talk talk={talk} hasWork quotes={quotes}
            onDropQuote={i => setCarried({ slug: slug!, list: quotes.filter((_, j) => j !== i) })}
            onSent={() => { setCarried({ slug: slug!, list: [] }); setNote(null); bump(); }} />
        </aside>
      )}
      {feeding && <Feed onClose={() => setFeeding(false)}
        onSubmitted={(s, existing) => {
          setFeeding(false); nav(`/w/${encodeURIComponent(s)}`); bump(); setReload(n => n + 1);
          setNote(existing ? { slug: s, text: t("feed.already") } : null);
        }} />}
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
