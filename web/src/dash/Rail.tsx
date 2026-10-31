import { useEffect, useState } from "react";
import { api, type RecentSession, type SessionRow, type Work, type WorkDetail } from "./api";
import Avatar from "./Avatar";
import { useT } from "./i18n";
import { useCharacters } from "./useCharacters";

const RECENT = 3;
const ANALYZING = ["running", "notes-running"];

function useLoaded<T>(load: () => Promise<T>, deps: unknown[], empty: T): T {
  const [v, setV] = useState<T>(empty);
  useEffect(() => {
    let live = true;
    load().then(x => { if (live) setV(x); }, () => { if (live) setV(empty); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return v;
}

/** 左欄「作品」與「對話」兩區。載入失敗只是列表空著(閱讀區自己會顯示錯誤)。 */
export default function Rail({ current, onPick, onPickSession }: {
  current: string | null;
  onPick: (slug: string) => void;
  onPickSession: (slug: string, session: string) => void;
}) {
  const t = useT();
  const chars = useCharacters();
  const [all, setAll] = useState(false);
  const works = useLoaded<Work[]>(() => api.works(), [], []);
  const recent = useLoaded<RecentSession[]>(() => api.recentSessions(), [], []);
  const mine = useLoaded<SessionRow[]>(() => current ? api.sessions(current) : Promise.resolve([]), [current], []);
  const detail = useLoaded<WorkDetail | null>(() => current ? api.work(current) : Promise.resolve(null), [current], null);
  useEffect(() => setAll(false), [current]);

  const shown = all ? mine : mine.slice(0, RECENT);
  return (
    <div className="rail-lists">
      <section aria-label={t("rail.works")}>
        <h2 className="rail-h">{t("rail.works")}</h2>
        <ul>
          {works.map(w => {
            const open = w.slug === current;
            return (
              <li key={w.slug}>
                <button type="button" className="rail-work" aria-current={open ? "true" : undefined}
                  onClick={() => onPick(w.slug)}>
                  <span className="rail-title">{w.title}</span>
                  <span className="rail-meta">
                    {ANALYZING.includes(String(w.state)) ? (
                      <><span className="rail-dots" aria-hidden="true"><i /><i /><i /></span> {t("rail.reading")}</>
                    ) : open && detail ? (
                      `${t("rail.version", { n: detail.version })} · ${t("rail.chars", { n: detail.text.length })}`
                    ) : null}
                  </span>
                </button>
                {open && (
                  <ul className="rail-sessions">
                    {shown.map(s => (
                      <li key={s.session}>
                        <button type="button" className="rail-session" onClick={() => onPickSession(w.slug, s.session)}>
                          {s.preview}
                        </button>
                      </li>
                    ))}
                    {mine.length > RECENT && !all && (
                      <li><button type="button" className="rail-session" onClick={() => setAll(true)}>{t("rail.all")}</button></li>
                    )}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </section>
      <section aria-label={t("rail.sessions")}>
        <h2 className="rail-h">{t("rail.sessions")}</h2>
        {recent.length === 0 ? <p className="rail-meta">{t("rail.noSessions")}</p> : (
          <ul>
            {recent.map(s => (
              <li key={s.session}>
                <button type="button" className="rail-convo" onClick={() => onPickSession(s.slug, s.session)}>
                  <Avatar character={chars.byId(s.character, s.mode)} size={22} />
                  <span className="rail-convo-text">
                    <span>{s.preview}</span>
                    <span className="rail-meta">{s.title}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
