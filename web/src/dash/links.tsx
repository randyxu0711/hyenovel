import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import type { Span } from "./api";

type Pane = "paper" | "side";
type PaperFn = (span: Span) => void;
type TalkFn = (quote: string) => boolean;

export type Links = {
  hover: string | null;
  setHover(q: string | null): void;
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

export function LinksProvider({ children }: { children: ReactNode }) {
  const [hover, setHover] = useState<string | null>(null);
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
    () => ({ hover, setHover, jumpToPaper, jumpToTalk, registerPaper, registerTalk, pane, setPane }),
    [hover, jumpToPaper, jumpToTalk, registerPaper, registerTalk, pane],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLinks(): Links {
  const v = useContext(Ctx);
  if (!v) throw new Error("useLinks must be used within LinksProvider");
  return v;
}
