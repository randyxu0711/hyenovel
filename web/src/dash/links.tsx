import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { Span } from "./api";

type Pane = "paper" | "side";
type PaperFn = (span: Span) => void;
type TalkFn = (quote: string) => boolean;

export type Links = {
  hover: string | null;
  /** 滑過的引文在原文的起點(有位置時);同一句出現兩處時,稿只亮這一處。 */
  hoverAt: number | null;
  setHover(q: string | null, at?: number | null): void;
  jumpToPaper(span: Span): void;
  jumpToTalk(quote: string): void;
  registerPaper(fn: PaperFn): () => void;
  registerTalk(fn: TalkFn): () => void;
  pane: Pane;
  setPane(p: Pane): void;
};

const Ctx = createContext<Links | null>(null);

const isNarrow = () =>
  typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(max-width:1100px)").matches;

/** < 1100px:一次只顯示一個窗格。隨視窗變動;沒有 matchMedia 就當寬螢幕。 */
export function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(isNarrow);
  useEffect(() => {
    const mq = typeof window.matchMedia === "function" ? window.matchMedia("(max-width:1100px)") : null;
    if (!mq?.addEventListener) return;
    const on = () => setNarrow(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return narrow;
}

export function LinksProvider({ children }: { children: ReactNode }) {
  const [hovered, setHovered] = useState<{ q: string | null; at: number | null }>({ q: null, at: null });
  const setHover = useCallback((q: string | null, at: number | null = null) => setHovered({ q, at: q === null ? null : at }), []);
  const [pane, setPane] = useState<Pane>("side");
  const paper = useRef<PaperFn | null>(null);
  const talk = useRef<TalkFn | null>(null);

  const registerPaper = useCallback((fn: PaperFn) => {
    paper.current = fn;
    return () => { if (paper.current === fn) paper.current = null; };
  }, []);
  const registerTalk = useCallback((fn: TalkFn) => {
    talk.current = fn;
    return () => { if (talk.current === fn) talk.current = null; };
  }, []);
  const jumpToPaper = useCallback((span: Span) => {
    if (isNarrow()) setPane("paper");
    paper.current?.(span);
  }, []);
  const jumpToTalk = useCallback((quote: string) => {
    if (talk.current?.(quote) && isNarrow()) setPane("side");
  }, []);

  const value = useMemo<Links>(
    () => ({ hover: hovered.q, hoverAt: hovered.at, setHover, jumpToPaper, jumpToTalk, registerPaper, registerTalk, pane, setPane }),
    [hovered, setHover, jumpToPaper, jumpToTalk, registerPaper, registerTalk, pane],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLinks(): Links {
  const v = useContext(Ctx);
  if (!v) throw new Error("useLinks must be used within LinksProvider");
  return v;
}
