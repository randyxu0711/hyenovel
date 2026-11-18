import { useEffect, useRef, useState } from "react";
import Icon from "./Icon";
import { MAX_QUOTE } from "./useSelectionQuote";
import type { Compare, TracePoint, TraceQuote } from "./api";
import { useT, type MsgKey } from "./i18n";
import Iq from "./Iq";
import { useLinks } from "./links";

const KINDS = ["moved", "confused", "wondering", "opinion"];
const STATE: Record<string, MsgKey> = { kept: "trace.kept", changed: "trace.changed", gone: "trace.gone", mixed: "trace.mixed" };

function Bring({ quote, onBring }: { quote: string; onBring?: (q: string) => void }) {
  const t = useT();
  if (!onBring) return null;
  return (
    <button type="button" className="ib trace-bring" aria-label={t("reader.bring")} title={t("reader.bring")}
      onClick={e => { e.stopPropagation(); onBring([...quote].slice(0, MAX_QUOTE).join("")); }}><Icon name="talk" /></button>
  );
}

function Quote({ q, version, old, many, onBring }: { q: TraceQuote; version: number; old: number; many: boolean; onBring?: (q: string) => void }) {
  const t = useT();
  const { jumpToRun } = useLinks();
  const state = q.fate !== "lost" && many ? <span className="trace-qstate">{t(STATE[q.fate])}</span> : null;
  if (q.fate === "lost") return (
    <p className="trace-q"><span role="button" tabIndex={0} className="dash-iq is-lost" aria-disabled="true"
      title={t("trace.lost", { n: old })}>「{q.quote}」</span></p>
  );
  if (q.fate === "gone") return (
    <p className="trace-q">
      <del role="button" tabIndex={0} className="dash-iq trace-gone" aria-label={q.quote} onClick={() => jumpToRun(q.del!)}
        onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); jumpToRun(q.del!); } }}>「{q.quote}」</del>
      {state}<Bring quote={q.quote} onBring={onBring} />
    </p>
  );
  if (q.fate === "changed") return (
    <p className="trace-q trace-changed">
      <del className="trace-old">「{q.quote}」</del>
      <Iq span={{ quote: q.new_text!, start: q.new!.start, end: q.new!.end }} version={version} />
      {state}<Bring quote={q.quote} onBring={onBring} />
    </p>
  );
  return <p className="trace-q"><Iq span={{ quote: q.quote, start: q.new!.start, end: q.new!.end }} version={version} />{state}</p>;
}

function Card({ p, cmp, onBring }: { p: TracePoint; cmp: Compare; onBring?: (q: string) => void }) {
  const t = useT();
  const { trace } = useLinks();
  const [open, setOpen] = useState(false);
  const self = useRef<HTMLElement>(null);
  useEffect(() => {
    if (trace.picked !== p.i) return;
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    self.current?.scrollIntoView?.({ block: "nearest", behavior: still ? "auto" : "smooth" });
  }, [trace.picked, p.i]);
  const raised = p.kind === "moved" && p.fate === "changed";
  return (
    <section ref={self} className={["side-note", "trace-card", raised && "is-raised"].filter(Boolean).join(" ")}
      data-sel={trace.picked === p.i ? "" : undefined} data-point={p.i}
      onMouseEnter={() => trace.setHover(p.i)} onMouseLeave={() => trace.setHover(null)}
      onClick={() => trace.setPicked(p.i)}>
      <p className="trace-top">
        {KINDS.includes(p.kind) && <span className="side-kind">{t(`notes.kind.${p.kind}` as MsgKey)}</span>}
        {p.label && <span className="trace-state">{t(STATE[p.label])}</span>}
      </p>
      <h3><button type="button" className="trace-title" aria-expanded={open} onClick={() => setOpen(o => !o)}>{p.title}</button></h3>
      {p.quotes.length === 0 && <p className="trace-q side-lede">{t("trace.noQuote")}</p>}
      {p.quotes.map((q, j) => <Quote key={j} q={q} version={cmp.new} old={cmp.old} many={p.quotes.length > 1} onBring={onBring} />)}
      {open && p.body && <p>{p.body}</p>}
      {open && p.question && <p className="side-question">{p.question}</p>}
    </section>
  );
}

function Group({ head, n, children, start }: { head: string; n: number; children: React.ReactNode; start: boolean }) {
  const [open, setOpen] = useState(start);
  if (!n) return null;
  return (
    <div className="trace-group">
      <button type="button" className="trace-group-h" aria-expanded={open} onClick={() => setOpen(o => !o)}>
        {head}<span className="dash-dm">{n}</span>
      </button>
      {open && children}
    </div>
  );
}

/** 右欄「去向」:上一版筆記的每一點,現在去了哪裡。只陳述,不評價。 */
export default function TraceTab({ cmp, onBring }: { cmp: Compare; onBring?: (q: string) => void }) {
  const t = useT();
  const moved = (p: TracePoint) => (p.kind === "moved" ? 0 : 1);
  const changed = cmp.points.filter(p => p.fate === "changed").sort((a, b) => moved(a) - moved(b) || a.i - b.i);
  const kept = cmp.points.filter(p => p.fate === "kept");
  const lost = cmp.points.filter(p => p.fate === "untracked");
  const cards = (ps: TracePoint[]) => ps.map(p => <Card key={p.i} p={p} cmp={cmp} onBring={onBring} />);
  return (
    <div className="side-col trace">
      <Group key={`c${cmp.old}`} head={t("trace.g.changed")} n={changed.length} start>{cards(changed)}</Group>
      <Group key={`k${cmp.old}${cmp.same}`} head={t("trace.g.kept")} n={kept.length} start={cmp.same}>{cards(kept)}</Group>
      <Group key={`l${cmp.old}`} head={t("trace.g.lost")} n={lost.length} start={false}>{cards(lost)}</Group>
    </div>
  );
}
