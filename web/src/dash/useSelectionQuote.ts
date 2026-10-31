import { useCallback, useEffect, useState, type RefObject } from "react";

export const MAX_QUOTE = 400;

/** 只收落在 container 內的選取(滑鼠、Shift+方向鍵、觸控都會觸發 selectionchange)。 */
export function useSelectionQuote(container: RefObject<HTMLElement | null>): {
  quote: string | null; tooLong: boolean; clear: () => void;
} {
  const [quote, setQuote] = useState<string | null>(null);

  useEffect(() => {
    const onChange = () => {
      const sel = document.getSelection();
      const box = container.current;
      const text = sel && !sel.isCollapsed && sel.rangeCount > 0 && box
        && box.contains(sel.getRangeAt(0).commonAncestorContainer) ? sel.toString().trim() : "";
      setQuote(text || null);
    };
    document.addEventListener("selectionchange", onChange);
    return () => document.removeEventListener("selectionchange", onChange);
  }, [container]);

  const clear = useCallback(() => {
    document.getSelection()?.removeAllRanges();
    setQuote(null);
  }, []);

  return { quote, tooLong: quote !== null && quote.length > MAX_QUOTE, clear };
}
