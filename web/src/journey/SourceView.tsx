import { useEffect, useRef } from "react";

export default function SourceView(
  { source, highlight }: { source: string; highlight: { start: number; end: number } | null },
) {
  const ref = useRef<HTMLElement | null>(null);
  useEffect(() => { if (highlight && ref.current) ref.current.scrollIntoView({ block: "center" }); }, [highlight]);
  if (!highlight) return <div className="src">{source}</div>;
  const { start, end } = highlight;
  return (
    <div className="src">
      {source.slice(0, start)}
      <mark className="hl" ref={ref as React.RefObject<HTMLElement>}>{source.slice(start, end)}</mark>
      {source.slice(end)}
    </div>
  );
}
