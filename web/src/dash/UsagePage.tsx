import { useEffect, useId, useState, type CSSProperties } from "react";
import {
  api, DashError, type QuotaWindow, type UsageBucket, type UsageCategory, type UsageCharacterRow,
  type UsageConfigRow, type UsageDelta, type UsageReport, type UsageSince, type UsageWork,
} from "./api";
import { localized, useLang, useT, type MsgKey } from "./i18n";
import { fmtDate, fmtDelta, fmtPct, fmtSeconds, fmtTime, fmtTokens } from "./usageFormat";

const PERIODS: UsageSince[] = ["7", "30", "all"];
const CATS: UsageCategory[] = ["analysis", "chat", "upkeep", "character", "other"];
const NEAR = 0.8;
const TOP = 10;

const sw = (c: UsageCategory): CSSProperties => ({ background: `var(--use-${c})` });
type T = ReturnType<typeof useT>;

function useFmt() {
  const lang = useLang();
  const t = useT();
  const tok = (n: number, partial = false) => `${partial ? "≥" : ""}${fmtTokens(n, lang)}`;
  const num = (n: number | null) => (n === null ? "—" : fmtTokens(n, lang));
  const sec = (ms: number | null) => (ms === null ? "—" : t("usage.sec", { s: fmtSeconds(ms) }));
  return { lang, t, tok, num, sec };
}

function Gauge({ label, w, t, lang }: { label: string; w: QuotaWindow; t: T; lang: ReturnType<typeof useLang> }) {
  const pct = Math.round((w.utilization ?? 0) * 100);
  const near = (w.utilization ?? 0) >= NEAR;
  return (
    <div className="use-gauge" data-warn={near || undefined} style={{ "--v": `${Math.min(pct, 100)}%` } as CSSProperties}>
      <span className="use-gauge-lab">{label}</span>
      <span className="use-gauge-pct">{pct}<i>%</i></span>
      <span className="use-track" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}
        aria-valuetext={t(near ? "usage.near" : "usage.used", { pct })} />
      <span className="use-gauge-sub">
        {near ? <b>{t("usage.near", { pct })}</b> : <span>{t("usage.used", { pct })}</span>}
        {w.resets_at !== null && <span>{t("usage.resets", { time: fmtTime(w.resets_at, lang) })}</span>}
      </span>
    </div>
  );
}

function Quota({ quota }: { quota: UsageReport["quota"] }) {
  const { t, lang } = useFmt();
  const id = useId();
  const windows = quota ? ([["usage.fiveHour", quota.five_hour], ["usage.sevenDay", quota.seven_day]] as [MsgKey, QuotaWindow | null][])
    .flatMap(([key, w]) => (w && w.utilization !== null ? [{ key, w }] : [])) : [];
  return (
    <section className="use-slip" aria-labelledby={id}>
      <header className="use-slip-h">
        <h2 id={id}>{t("usage.quota")}</h2>
        {quota && <small>{t("usage.asOf", { time: fmtTime(quota.at, lang) })}</small>}
      </header>
      {windows.length
        ? windows.map(({ key, w }) => <Gauge key={key} label={t(key)} w={w} t={t} lang={lang} />)
        : <p className="use-slip-empty">{t("usage.noQuota")}</p>}
    </section>
  );
}

function Activity({ report }: { report: UsageReport }) {
  const { t, tok, num } = useFmt();
  const id = useId();
  return (
    <section className="use-group" aria-labelledby={id}>
      <h2 className="use-group-h" id={id}>{t("usage.byActivity")}</h2>
      <div className="use-strip" aria-hidden="true">
        {report.categories.map(c => <span key={c.id} style={{ ...sw(c.id), flexGrow: c.tokens }} />)}
      </div>
      <table className="use-rows" aria-labelledby={id}>
        <thead><tr>
          <th scope="col"><span className="use-sr">{t("usage.byActivity")}</span></th>
          <th scope="col">{t("usage.col.tokens")}</th><th scope="col">{t("usage.col.share")}</th>
          <th scope="col" className="use-avg">{t("usage.col.avg")}</th>
        </tr></thead>
        <tbody>
          {report.categories.map(c => (
            <tr key={c.id}>
              <th scope="row"><i className="use-sw" style={sw(c.id)} />{t(`usage.cat.${c.id}`)}</th>
              <td>{tok(c.tokens, c.partial)}</td><td>{fmtPct(c.share)}</td><td className="use-avg">{num(c.avg)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {report.unused_share !== null && <p className="use-unused">{t("usage.unused", { pct: Math.round(report.unused_share * 100) })}</p>}
    </section>
  );
}

function Breakdown({ bucket }: { bucket: UsageBucket }) {
  const { t, tok } = useFmt();
  return (
    <div>
      <h3>{t("usage.byActivity")}</h3>
      <dl className="use-dl">
        {CATS.filter(c => bucket.by_category[c] !== undefined).map(c => (
          <div key={c}><dt><i className="use-sw" style={sw(c)} />{t(`usage.cat.${c}`)}</dt><dd>{tok(bucket.by_category[c]!)}</dd></div>
        ))}
      </dl>
    </div>
  );
}

function Versions({ versions }: { versions: UsageWork["versions"] }) {
  const { t, tok } = useFmt();
  const max = Math.max(1, ...versions.map(v => v.tokens));
  return (
    <div>
      <h3>{t("usage.versions")}</h3>
      <ol className="use-vers">
        {versions.map(v => (
          <li key={v.n} className="use-ver" data-none={!v.analyzed || undefined}
            style={{ "--h": `${Math.max(2, (v.tokens / max) * 60)}px` } as CSSProperties}>
            <b>{!v.analyzed ? t("usage.notAnalyzed") : v.tokens ? tok(v.tokens, v.partial) : "—"}</b>
            <i aria-hidden="true" />
            <span>{t("usage.version", { n: v.n })}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function WorkRow({ title, bucket, max, archived, plain, versions }: {
  title: string; bucket: UsageBucket; max: number; archived?: boolean; plain?: boolean; versions?: UsageWork["versions"];
}) {
  const { t, tok } = useFmt();
  return (
    <li>
      <details className="use-work">
        <summary>
          <svg className="use-caret" viewBox="0 0 14 14" aria-hidden="true"><path d="M5 3.5 8.5 7 5 10.5" /></svg>
          <span className="use-work-t" data-plain={plain || undefined}>
            <span>{title}</span>{archived && <em>{t("usage.archived")}</em>}
          </span>
          <span className="use-wbar" aria-hidden="true" style={{ "--w": `${(bucket.tokens / max) * 100}%` } as CSSProperties}>
            {CATS.filter(c => bucket.by_category[c]).map(c => <i key={c} style={{ ...sw(c), flexGrow: bucket.by_category[c] }} />)}
          </span>
          <span className="use-work-v">{tok(bucket.tokens, bucket.partial)}</span>
        </summary>
        <div className="use-detail">
          <Breakdown bucket={bucket} />
          {versions && versions.length > 0 && <Versions versions={versions} />}
        </div>
      </details>
    </li>
  );
}

function Works({ works, unbound }: { works: UsageWork[]; unbound: UsageBucket | null }) {
  const { t } = useFmt();
  const id = useId();
  const [all, setAll] = useState(false);
  if (!works.length && !unbound) return null;
  const max = Math.max(1, ...works.map(w => w.tokens), unbound?.tokens ?? 0);
  const shown = all ? works : works.slice(0, TOP);
  return (
    <section className="use-group" aria-labelledby={id}>
      <h2 className="use-group-h" id={id}>{t("usage.byWork")}</h2>
      <ul className="use-works">
        {shown.map(w => <WorkRow key={w.story_id} title={w.title} bucket={w} max={max} archived={w.archived} versions={w.versions} />)}
        {unbound && <WorkRow title={t("usage.unbound")} bucket={unbound} max={max} plain />}
      </ul>
      {!all && works.length > TOP && (
        <button type="button" className="use-rest" onClick={() => setAll(true)}>{t("usage.rest", { n: works.length - TOP })}</button>
      )}
    </section>
  );
}

function Cell({ value, delta }: { value: string; delta: number | null | undefined }) {
  const { t } = useFmt();
  return <td>{value}{delta != null && <span className="use-d" title={t("usage.vsPrev")}>{fmtDelta(delta)}</span>}</td>;
}

function Stats({ r }: { r: UsageConfigRow | UsageCharacterRow }) {
  const { num, sec } = useFmt();
  const d: Partial<UsageDelta> = r.delta ?? {};
  return <>
    <td>{r.n}</td>
    <Cell value={num(r.avg)} delta={d.avg} />
    <Cell value={num(r.thinking)} delta={d.thinking} />
    <Cell value={sec(r.ms_median)} delta={d.ms} />
  </>;
}

function groupBy<R>(rows: R[], key: (r: R) => string): R[][] {
  const out = new Map<string, R[]>();
  for (const r of rows) out.set(key(r), [...(out.get(key(r)) ?? []), r]);
  return [...out.values()];
}

function Head({ first, model }: { first: string; model?: boolean }) {
  const { t } = useFmt();
  return (
    <thead><tr>
      <th scope="col"><span className="use-sr">{first}</span></th>
      {model && <th scope="col">{t("usage.col.model")}</th>}
      <th scope="col">{t("usage.col.calls")}</th><th scope="col">{t("usage.col.avg")}</th>
      <th scope="col">{t("usage.col.thinking")}</th><th scope="col">{t("usage.col.latency")}</th>
    </tr></thead>
  );
}

function Current({ on }: { on: boolean }) {
  const { t } = useFmt();
  return on ? <span className="use-cur">{t("usage.current")}</span> : null;
}

function Compare({ compare }: { compare: UsageReport["compare"] }) {
  const { t, lang } = useFmt();
  const step = (k: string) => t(`usage.step.${k}` as MsgKey) ?? k;
  return (
    <details className="use-cmp">
      <summary>
        <svg className="use-caret" viewBox="0 0 14 14" aria-hidden="true"><path d="M5 3.5 8.5 7 5 10.5" /></svg>
        {t("usage.compare")}<span className="use-aside">{t("usage.compareScope")}</span>
      </summary>
      <p className="use-cmp-note">{t("usage.compareNote")}</p>
      <div className="use-cmp-wrap">
        {compare.config.length > 0 && (
          <table className="use-tbl">
            <caption>{t("usage.byPrompt")}</caption>
            <Head first={t("usage.byPrompt")} model />
            {groupBy(compare.config, r => r.kind).map(rows => (
              <tbody key={rows[0].kind}>
                {rows.map(r => (
                  <tr key={`${r.prompt_fp}/${r.runner}/${r.model}/${r.effort}`} data-solo={rows.length === 1 || undefined}>
                    <th scope="row">{step(r.kind)}<Current on={r.current} />
                      <span className="use-sub">{t("usage.fpSince", { fp: r.prompt_fp.slice(0, 7), date: fmtDate(r.first_at, lang) })}</span>
                    </th>
                    <td className="use-model">{r.recorded
                      ? <>{r.model ?? "—"}<span className="use-sub">{r.effort ?? "—"}</span></>
                      : t("usage.notRecorded")}</td>
                    <Stats r={r} />
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        )}
        {compare.character.length > 0 && (
          <table className="use-tbl">
            <caption>{t("usage.byCompanion")}</caption>
            <Head first={t("usage.byCompanion")} />
            {groupBy(compare.character, r => r.character_id ?? "").map(rows => (
              <tbody key={rows[0].character_id ?? ""}>
                {rows.map(r => (
                  <tr key={`${r.character_id}@${r.character_v}`} data-solo={rows.length === 1 || undefined}>
                    <th scope="row">{r.recorded && r.name ? localized(r.name, lang) : t("usage.notRecorded")}<Current on={r.current} />
                      {r.character_v !== null && <span className="use-sub">{t("usage.version", { n: r.character_v })}</span>}
                    </th>
                    <Stats r={r} />
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        )}
      </div>
    </details>
  );
}

export default function UsagePage() {
  const { t, tok } = useFmt();
  const [since, setSince] = useState<UsageSince>("7");
  const [report, setReport] = useState<UsageReport | null>(null);
  const [err, setErr] = useState<"noLedger" | "failed" | null>(null);
  useEffect(() => {
    const ctl = new AbortController();
    api.usage(since, ctl.signal).then(
      r => { setReport(r); setErr(null); },
      e => {
        if (e instanceof DashError && e.code === "aborted") return;
        setErr(e instanceof DashError && e.status === 404 ? "noLedger" : "failed");
      });
    return () => ctl.abort();
  }, [since]);
  if (err === "noLedger") return <p className="use-empty" role="status">{t("usage.noLedger")}</p>;
  if (!report) return err ? <p className="use-empty" role="alert">{t("usage.failed")}</p> : null;
  const empty = report.total.tokens === 0 && report.categories.length === 0;
  const incomplete = report.completeness.partial + report.completeness.unknown;
  return (
    <div className="use-page">
      {err && <p className="use-empty" role="alert">{t("usage.failed")}</p>}
      <Quota quota={report.quota} />
      <div className="use-period">
        <div className="set-seg" role="group" aria-label={t("usage.period")}>
          {PERIODS.map(p => (
            <button key={p} type="button" aria-pressed={since === p} onClick={() => setSince(p)}>{t(`usage.since.${p}`)}</button>
          ))}
        </div>
        {!empty && <span className="use-total">{t("usage.total", { total: tok(report.total.tokens, report.total.partial) })}</span>}
      </div>
      {empty ? <p className="use-empty">{t("usage.empty")}</p> : <>
        <Activity report={report} />
        <Works works={report.works} unbound={report.unbound} />
        <Compare compare={report.compare} />
      </>}
      {report.running > 0 && <p className="use-foot">{t("usage.running", { n: report.running })}</p>}
      {incomplete > 0 && <p className="use-foot">{t("usage.foot", { n: incomplete })}</p>}
    </div>
  );
}
