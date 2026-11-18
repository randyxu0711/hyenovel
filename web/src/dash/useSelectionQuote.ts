import { useCallback, useEffect, useState, type RefObject } from "react";
import { cpLength } from "./cp";

export const MAX_QUOTE = 400;
type Rect = { left: number; top: number; bottom: number };

/** 只收落在 container 內的選取(滑鼠、Shift+方向鍵、觸控都會觸發 selectionchange)。
 *  rect = 選取最後一段在視窗中的位置(給浮動鈕對齊用;量不到就是 null)。字數以 code point 算,跟 den 同。 */
export function useSelectionQuote(container: RefObject<HTMLElement | null>): {
  quote: string | null; tooLong: boolean; rect: Rect | null; clear: () => void;
} {
  const [sel, setSel] = useState<{ quote: string; rect: Rect | null } | null>(null);

  useEffect(() => {
    const onChange = () => {
      const s = document.getSelection();
      const box = container.current;
      const range = s && !s.isCollapsed && s.rangeCount > 0 ? s.getRangeAt(0) : null;
      const text = range && box && box.contains(range.commonAncestorContainer) ? s!.toString().trim() : "";
      if (!text) { setSel(null); return; }
      const rs = typeof range!.getClientRects === "function" ? [...range!.getClientRects()].filter(x => x.width || x.height) : [];
      const r = rs.length ? rs[rs.length - 1] : typeof range!.getBoundingClientRect === "function" ? range!.getBoundingClientRect() : null;
      setSel({ quote: text, rect: r && (r.width || r.height) ? { left: r.left, top: r.top, bottom: r.bottom } : null });
    };
    document.addEventListener("selectionchange", onChange);
    window.addEventListener("scroll", onChange, true);
    window.addEventListener("resize", onChange);
    return () => {
      document.removeEventListener("selectionchange", onChange);
      window.removeEventListener("scroll", onChange, true);
      window.removeEventListener("resize", onChange);
    };
  }, [container]);

  const clear = useCallback(() => {
    document.getSelection()?.removeAllRanges();
    setSel(null);
  }, []);

  return { quote: sel?.quote ?? null, tooLong: sel !== null && cpLength(sel.quote) > MAX_QUOTE, rect: sel?.rect ?? null, clear };
}
