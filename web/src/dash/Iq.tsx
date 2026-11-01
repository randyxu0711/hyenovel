import type { Span } from "./api";
import { useT } from "./i18n";
import { useLinks } from "./links";

/** 右欄裡的一段原文引文:滑過 → 稿上那句亮;點 → 稿捲過去。
 *  這一版對不到(start 為 null)→ 灰虛線、說明找不到,不跳。 */
export default function Iq({ span, version, children }: { span: Span; version: number; children?: string }) {
  const t = useT();
  const { setHover, jumpToPaper } = useLinks();
  const label = children ?? `「${span.quote}」`;
  if (span.start === null) {
    return <button type="button" className="dash-iq is-lost" aria-disabled="true" title={t("iq.lost", { n: version })}>{label}</button>;
  }
  const on = () => setHover(span.quote, span.start), off = () => setHover(null);
  return (
    <button type="button" className="dash-iq" onMouseEnter={on} onMouseLeave={off} onFocus={on} onBlur={off}
      onClick={() => jumpToPaper(span)}>
      {label}
    </button>
  );
}

/** 把一段話裡成對的「……」換成引文鍵;只有在 spans 裡的才算原文,其他照一般文字。 */
export function quoted(text: string, spans: Span[], version: number): (string | JSX.Element)[] {
  const out: (string | JSX.Element)[] = [];
  let at = 0;
  for (const m of text.matchAll(/「([^「」]*)」/g)) {
    const inner = m[1];
    const span = spans.find(s => s.quote === inner || s.quote === inner.trim());
    if (!span) continue;
    if (m.index! > at) out.push(text.slice(at, m.index));
    out.push(<Iq key={m.index} span={span} version={version}>{m[0]}</Iq>);
    at = m.index! + m[0].length;
  }
  if (at < text.length) out.push(text.slice(at));
  return out;
}
