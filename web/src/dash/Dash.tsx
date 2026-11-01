import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, DashError, type Work } from "./api";
import { errorMessage, localized, useLang, useT } from "./i18n";
import Home from "./Home";
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
  const loc = useLocation();
  const { pathname } = loc;
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
  // 進門畫面送出的第一句:作品頁掛載時以新局送出一次,並清掉 router state(重新整理不重送)。
  // 延到下一個 tick 才送:StrictMode 的 effect 清理會取消第一次排程,且送出在 useTalk 重設之後。
  const first = (loc.state as { firstMessage?: string; character?: string } | null) ?? null;
  const talkRef = useRef(talk);
  talkRef.current = talk;
  const sentKey = useRef("");
  useEffect(() => {
    if (view !== "work" || !first?.firstMessage) return;
    const h = setTimeout(() => {
      if (sentKey.current === loc.key) return;
      sentKey.current = loc.key;
      nav(loc.pathname + loc.search, { replace: true, state: null });
      void talkRef.current.send(first.firstMessage!, [], first.character);
    }, 0);
    return () => clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, loc.key]);
  const goHome = () => nav("/", { state: { focus: true } });
  const submitted = (s: string, existing: boolean) => {
    nav(`/w/${encodeURIComponent(s)}`); bump(); setReload(n => n + 1);
    setNote(existing ? { slug: s, text: t("feed.already") } : null);
  };
  const open = (s: string) => { setNote(null); nav(`/w/${encodeURIComponent(s)}`); };

  return (
    <div className="dash" data-view={view} data-mode={mode}>
      <Rail collapsed={view !== "home"} works={works} current={slug} onOpen={open}
        onNew={goHome} onSubmitNew={goHome} />
      <main className="dash-desk">
        {view === "work" && <Reader slug={slug!} version={version} reload={reload} onFinished={bump} companion={localized(me.name, lang)}
          onQuote={q => setCarried(c => { const list = c.slug === slug ? c.list : []; return { slug: slug!, list: list.includes(q) ? list : [...list, q] }; })} />}
        {view === "home" && <Home works={works} onSubmitted={submitted} />}
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
