import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, DashError, type Work, type WorkMap } from "./api";
import { errorMessage, useT } from "./i18n";
import { LinksProvider } from "./links";
import Home from "./Home";
import Rail from "./Rail";
import Reader from "./Reader";
import Side, { marksFrom } from "./Side";
import { useSeen } from "./useSeen";
import { useTalk } from "./useTalk";
import { applySignature, initThemes, useThemeState } from "./theme";
import { CharactersProvider, makeCharacters, type Characters } from "./useCharacters";
import "./dash.css";

type View = "home" | "work" | "settings";

function Shell({ chars }: { chars: Characters }) {
  const t = useT();
  const { mode } = useThemeState();
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

  const talk = useTalk(slug, version);
  const me = chars.byId(talk.whoId);
  const { markSeen } = useSeen();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (slug) markSeen(slug); }, [slug]);

  // 這一版的對位資料(結構圖、筆記);分析跑完或重交時重抓。
  const [mapRev, setMapRev] = useState(0);
  const [map, setMap] = useState<WorkMap | null>(null);
  useEffect(() => {
    setMap(null);
    if (!slug) return;
    let live = true;
    api.map(slug, version).then(m => { if (live) setMap(m); }, () => { /* 抓不到:分頁停在載入中,稿與對話照用 */ });
    return () => { live = false; };
  }, [slug, version, mapRev, reload]);
  // 痕跡只在逐字稿的位置對的就是這一版時才畫(換版本重抓完之前不畫)。
  const marks = talk.spansV === version ? marksFrom(talk.turns, chars) : [];
  const work = works.find(w => w.slug === slug);
  const split = useSplit();
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
    <LinksProvider>
    <div className="dash" data-view={view} data-mode={mode}
      style={split.width ? { "--dash-split": `${split.width}px` } as CSSProperties : undefined}>
      <Rail collapsed={view !== "home"} works={works} current={slug} onOpen={open}
        onNew={goHome} onSubmitNew={goHome} />
      <main className="dash-desk">
        {view === "work" && <Reader slug={slug!} version={version} reload={reload} marks={marks}
          onFinished={() => { bump(); setMapRev(n => n + 1); }}
          works={works} onOpen={open} onSubmitNew={goHome}
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
        <div className="dash-grip" role="separator" aria-orientation="vertical" aria-label={t("split.label")} tabIndex={0}
          aria-valuemin={MIN} aria-valuenow={split.width ?? undefined}
          onPointerDown={split.onPointerDown} onKeyDown={split.onKeyDown} />
      )}
      {view === "work" && (
        <aside className="dash-side">
          <Side version={version ?? work?.version ?? 0} map={map} state={String(work?.state ?? "")} marks={marks}
            talk={talk} quotes={quotes}
            onDropQuote={i => setCarried({ slug: slug!, list: quotes.filter((_, j) => j !== i) })}
            onSent={() => { setCarried({ slug: slug!, list: [] }); setNote(null); bump(); }} />
        </aside>
      )}
    </div>
    </LinksProvider>
  );
}

const SPLIT_KEY = "hyenovel.split";
const MIN = 380;      // 稿窗格與右欄各自最少
const RAIL = 56;      // 收起的左欄,不算在兩窗格裡
const GRIP = 9;
const STEP = 24;
const clampSide = (w: number) => Math.round(Math.max(MIN, Math.min(w, window.innerWidth - RAIL - GRIP - MIN)));

/** 中間分隔線:拖或用方向鍵調右欄寬,存 localStorage。沒存過 = 兩邊平分(CSS 決定)。 */
function useSplit() {
  const [width, setWidth] = useState<number | null>(() => {
    try { const n = Number(localStorage.getItem(SPLIT_KEY)); return n > 0 ? n : null; } catch { return null; }
  });
  const set = (w: number) => {
    const v = clampSide(w);
    setWidth(v);
    try { localStorage.setItem(SPLIT_KEY, String(v)); } catch { /* 存不了就只這次有效 */ }
  };
  const current = (el: HTMLElement) => width ?? ((el.nextElementSibling as HTMLElement | null)?.getBoundingClientRect().width || MIN);
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    set(current(e.currentTarget) + (e.key === "ArrowLeft" ? STEP : -STEP));
  };
  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    const grip = e.currentTarget;
    grip.setPointerCapture?.(e.pointerId);
    const move = (ev: globalThis.PointerEvent) => set(window.innerWidth - ev.clientX - GRIP / 2);
    const up = () => { grip.removeEventListener("pointermove", move); grip.removeEventListener("pointerup", up); };
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", up);
  };
  return { width, onKeyDown, onPointerDown };
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
