import { useCallback, useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, DashError, type Character, type Work, type WorkMap } from "./api";
import { errorMessage, useT } from "./i18n";
import { flushSync } from "react-dom";
import { LinksProvider, useLinks, useNarrow } from "./links";
import Palette from "./Palette";
import Home from "./Home";
import Rail from "./Rail";
import Reader from "./Reader";
import Settings, { SettingsNav, type SettingsSection } from "./Settings";
import Side, { marksFrom } from "./Side";
import Figure from "./Figure";
import { composerState, useReaction } from "./Talk";
import { useSeen } from "./useSeen";
import { initCompanion, useTalk } from "./useTalk";
import { SHELF_W, useShelf } from "./useShelf";
import { applySignature, initThemes, toggleDayNight, useThemeState } from "./theme";
import { CharactersProvider, makeCharacters, type Characters } from "./useCharacters";
import "./dash.css";

type View = "home" | "work" | "settings";

function Shell({ chars }: { chars: Characters }) {
  const t = useT();
  const { mode } = useThemeState();
  const nav = useNavigate();
  const { slug: routeSlug, session: routeSession } = useParams();
  const { pathname } = useLocation();
  const [search, setSearch] = useSearchParams();
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
  // null = 還沒到(進門畫面不能說「沒有作品」);抓失敗記錯誤碼,左欄空著,閱讀區自己會顯示錯誤。
  const [loaded, setLoaded] = useState<Work[] | null>(null);
  const [worksErr, setWorksErr] = useState<string | null>(null);
  const works = loaded ?? [];
  const bump = () => setRefresh(n => n + 1);
  useEffect(() => {
    let live = true;
    api.works().then(ws => { if (live) { setLoaded(ws); setWorksErr(null); } },
      e => { if (live) setWorksErr(e instanceof DashError ? e.code : "unknown"); });
    return () => { live = false; };
  }, [refresh]);

  // 稿上正顯示的原文:是這篇的最新版時才交給 useTalk(邊說邊畫線在這裡找引文)
  const [paper, setPaper] = useState<{ slug: string; latest: boolean; text: string } | null>(null);
  const source = version === undefined && paper && paper.slug === slug && paper.latest ? paper.text : null;
  // 目前這局記在網址的 ?s=(重新整理回到同一局);只換網址不進歷史。
  const setSearchRef = useRef(setSearch);
  setSearchRef.current = setSearch;
  const viewRef = useRef(view);
  viewRef.current = view;
  const onSession = useCallback((id: string | null) => {
    if (viewRef.current === "home") { nav(id ? `/c/${encodeURIComponent(id)}` : "/", { replace: true }); return; }
    setSearchRef.current(prev => {
      const p = new URLSearchParams(prev);
      if (id) p.set("s", id); else p.delete("s");
      return p;
    }, { replace: true });
  }, [nav]);
  const [talkReload, setTalkReload] = useState(0);   // 交了新版:目前這局的逐字稿重抓(畫線位置對到新稿)
  const talk = useTalk(slug, version, source, slug ? search.get("s") : routeSession ?? null, onSession, talkReload);
  const shownRoute = useRef(routeSession);
  useEffect(() => {
    if (view !== "home" || shownRoute.current === routeSession) return;
    shownRoute.current = routeSession;
    if (talk.streaming !== null || (routeSession ?? null) === talk.session) return;
    if (routeSession) talk.open(routeSession); else talk.fresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, routeSession]);
  useEffect(() => {
    if (view === "home" && talk.bound && talk.session)
      nav(`/w/${encodeURIComponent(talk.bound)}?s=${encodeURIComponent(talk.session)}`, { replace: true });
  }, [view, talk.bound, talk.session, nav]);
  const me = chars.byId(talk.whoId);
  const { markSeen } = useSeen();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (slug) markSeen(slug); }, [slug]);

  // 這一版的對位資料(結構圖、筆記);分析跑完或重交時重抓。
  const [mapRev, setMapRev] = useState(0);
  const [map, setMap] = useState<WorkMap | null>(null);
  const [mapErr, setMapErr] = useState<string | null>(null);   // 這篇這版抓不到對位資料的錯誤碼
  useEffect(() => {
    setMap(null); setMapErr(null);
    if (!slug) return;
    let live = true;
    api.map(slug, version).then(m => { if (live) setMap(m); },
      e => { if (live) setMapErr(e instanceof DashError ? e.code : "unknown"); });   // 稿與對話照用,分頁說錯誤
    return () => { live = false; };
  }, [slug, version, mapRev, reload]);
  // 結構圖選中的觀察(意象 id):稿上它的引文畫直線;換篇、換版清掉。
  const [ob, setOb] = useState<string | null>(null);
  useEffect(() => { setOb(null); }, [slug, version]);
  const obs = (map?.motifs?.find(m => m.id === ob)?.spans ?? [])
    .flatMap(s => s.start !== null && s.end !== null ? [{ start: s.start, end: s.end }] : []);
  // 痕跡只在逐字稿的位置對的就是這一版時才畫(換版本重抓完之前不畫)。
  const marks = talk.spansV === version ? [...marksFrom(talk.turns, chars), ...talk.liveMarks] : [];
  const work = works.find(w => w.slug === slug);
  const analyzing = ["running", "notes-running"].includes(String(work?.state));
  const reacting = useReaction(analyzing);
  // 設定頁的回去鍵:回到進設定前開著的那篇;沒開過 → 進門。分區只記在這裡,不進網址。
  const [last, setLast] = useState<string | null>(null);
  useEffect(() => { if (slug) setLast(slug); }, [slug]);
  const [section, setSection] = useState<SettingsSection>("look");
  const setNav = <SettingsNav section={section} onPick={setSection}
    back={{ label: t("set.back.page"), to: last ? `/w/${encodeURIComponent(last)}` : "/" }} />;
  const shelf = useShelf();
  const split = useSplit(SHELF_W[shelf.mode]);
  const narrow = useNarrow();
  const { pane, setPane } = useLinks();
  const [palette, setPalette] = useState(false);
  const [focus, setFocus] = useState(false);
  const focused = focus && view === "work" && !narrow;
  useEffect(() => { if (view !== "work") setFocus(false); }, [view]);
  const hidePaper = narrow && view === "work" && pane !== "paper";
  const hideSide = narrow && pane !== "side";
  // 窄螢幕打開一篇 → 先看稿。兩個窗格都留著掛載,只藏一邊,跳轉才找得到對方。
  useEffect(() => { if (slug && narrow) setPane("paper"); }, [slug, narrow, setPane]);
  // 鍵盤:Ctrl/⌘+K 開指令框(輸入框裡也算);「/」聚焦輸入框(焦點已在輸入元素時不攔)
  const toggleShelf = useRef(shelf.toggle);
  toggleShelf.current = shelf.toggle;
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.isComposing || e.keyCode === 229) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette(true); return; }
      if ((e.ctrlKey || e.metaKey) && e.key === "\\") { e.preventDefault(); toggleShelf.current(); return; }
      if (e.key === "Escape" && focused && !palette) { setFocus(false); return; }
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
      if (view === "settings") return;
      e.preventDefault();
      if (view === "work" && hideSide) flushSync(() => setPane("side"));
      document.querySelector<HTMLElement>(view === "work" ? ".dash-side textarea" : ".home textarea")?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [view, hideSide, setPane, focused, palette]);
  useEffect(() => applySignature(me, mode), [me, mode]);
  const goHome = () => nav("/", { state: { focus: true } });
  const submitted = (s: string, existing: boolean) => {
    nav(`/w/${encodeURIComponent(s)}`); bump(); setReload(n => n + 1);
    setNote(existing ? { slug: s, text: t("feed.already") } : null);
  };
  const open = (s: string) => { setNote(null); nav(`/w/${encodeURIComponent(s)}`); };
  // 交新版:回最新版(拿掉 ?v=,?s= 目前這局留著),重抓左欄與稿。
  const newVersion = (r: { same: boolean; version: number }) => {
    setSearch(prev => { const p = new URLSearchParams(prev); p.delete("v"); return p; }, { replace: true });
    bump(); setReload(n => n + 1);
    if (r.same) setNote({ slug: slug!, text: t("newver.same", { n: r.version }) });
    else { setNote(null); setTalkReload(n => n + 1); }
  };

  return (
    <div className="dash" data-view={view} data-mode={mode} data-shelf={shelf.mode} data-narrow={narrow ? "true" : "false"} data-focus={focused ? "true" : "false"}
      style={split.width ? { "--dash-split": `${split.width}px` } as CSSProperties : undefined}>
      {narrow && (
        <div className="dash-bar">
          {view === "work" && (
            <div className="dash-pane-switch" role="group" aria-label={t("pane.label")}>
              <button type="button" aria-pressed={pane === "paper"} onClick={() => setPane("paper")}>{t("pane.paper")}</button>
              <button type="button" aria-pressed={pane === "side"} onClick={() => setPane("side")}>{t("pane.talk")}</button>
            </div>
          )}
          <button type="button" className="dash-bar-palette" aria-haspopup="dialog" onClick={() => setPalette(true)}>{t("palette.open")}</button>
        </div>
      )}
      <Rail mode={shelf.mode} onToggle={shelf.toggle} works={works} current={slug} talk={talk} view={view}
        onOpen={open} onNew={goHome} onFind={() => setPalette(true)} onChat={id => nav(id ? `/c/${encodeURIComponent(id)}` : "/")}
        settingsNav={view === "settings" ? setNav : null} hidden={focused} />
      <main className="dash-desk" hidden={hidePaper}>
        {view === "work" && <Reader slug={slug!} version={version} reload={reload} marks={marks} obs={obs} drawing={talk.drawing ?? undefined}
          onAnalysed={() => setMapRev(n => n + 1)} onPaper={setPaper} onNewVersion={newVersion}
          focus={focused} onFocus={narrow ? undefined : setFocus}
          onFinished={() => { bump(); setMapRev(n => n + 1); }}
          onQuote={q => {
            setCarried(c => { const list = c.slug === slug ? c.list : []; return { slug: slug!, list: list.includes(q) ? list : [...list, q] }; });
            if (narrow) setPane("side");
          }} />}
        {view === "home" && <Home works={loaded} error={worksErr} onSubmitted={submitted} talk={talk} />}
        {view === "settings" && <Settings section={section} nav={narrow ? setNav : null} />}
      </main>
      {notice && (
        <p className="dash-notice" role="status">
          {notice}
          <button type="button" aria-label={t("notice.dismiss")} onClick={() => setNote(null)}>×</button>
        </p>
      )}
      {view === "work" && !narrow && (
        <div className="dash-grip" hidden={focused} role="separator" aria-orientation="vertical" aria-label={t("split.label")} tabIndex={0}
          aria-valuemin={MIN} aria-valuenow={split.width ?? undefined}
          onPointerDown={split.onPointerDown} onKeyDown={split.onKeyDown} />
      )}
      {view === "work" && (
        <aside className="dash-side" hidden={hideSide || focused}>
          <Side version={version ?? work?.version ?? 0} map={map} mapError={mapErr} state={String(work?.state ?? "")} marks={marks}
            talk={talk} quotes={quotes} ob={ob} onOb={setOb} analyzing={analyzing}
            onDropQuote={i => setCarried({ slug: slug!, list: quotes.filter((_, j) => j !== i) })}
            onSent={() => { setCarried({ slug: slug!, list: [] }); setNote(null); bump(); }} />
        </aside>
      )}
      {focused && (
        <button type="button" className="dash-peek" aria-label={t("focus.back")} title={t("focus.back")} onClick={() => setFocus(false)}>
          <Figure character={me} size={58} state={composerState({ streaming: talk.streaming, analyzing, reacting, typing: false })} />
        </button>
      )}
      {palette && <Palette works={works} chars={chars} onOpen={open} onSettings={() => nav("/settings")}
        onToggle={toggleDayNight} onClose={() => setPalette(false)} />}
    </div>
  );
}

const SPLIT_KEY = "hyenovel.split";
const MIN = 380;      // 稿窗格與右欄各自最少
const GRIP = 9;
const STEP = 24;
/** 右欄寬夾在 [MIN, 視窗 − 書架 − 分隔線 − 稿最少]。 */
export const clampSide = (w: number, shelfW: number) =>
  Math.round(Math.max(MIN, Math.min(w, window.innerWidth - shelfW - GRIP - MIN)));

/** 中間分隔線:拖或用方向鍵調右欄寬,存 localStorage。沒存過 = 兩邊平分(CSS 決定)。 */
function useSplit(shelfW: number) {
  const [width, setWidth] = useState<number | null>(() => {
    try { const n = Number(localStorage.getItem(SPLIT_KEY)); return n > 0 ? n : null; } catch { return null; }
  });
  const set = (w: number) => {
    const v = clampSide(w, shelfW);
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
    const apply = (ch: { characters: Character[]; default: string }) => {
      initCompanion(ch.default);
      setChars(makeCharacters(ch.characters, ch.default, () => api.characters().then(apply)));
    };
    Promise.all([api.themes(), api.characters()]).then(([th, ch]) => {
      initThemes(th.themes, th.default);
      apply(ch);
    }, e => setErr(e instanceof DashError ? e.code : "unknown"));
  }, []);
  if (err) return <div className="dash dash-note" role="alert">{t(errorMessage(err))}</div>;
  if (!chars) return <div className="dash dash-note">{t("loading")}</div>;
  return <CharactersProvider value={chars}><LinksProvider><Shell chars={chars} /></LinksProvider></CharactersProvider>;
}
