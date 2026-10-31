import { useEffect, useState } from "react";
import { api, type RecentSession, type SessionRow, type Work } from "./api";
import Avatar from "./Avatar";
import { useT } from "./i18n";
import { useCharacters } from "./useCharacters";

const RECENT = 3;
const ANALYZING = ["running", "notes-running"];

/** 結果綁在載入它的 key 上:key 一換,舊 key 的資料立刻不再回傳(不會殘留到新作品底下)。 */
function useLoaded<T>(load: () => Promise<T>, key: string | null, empty: T, tick = 0): T {
  const [got, setGot] = useState<{ key: string | null; v: T } | null>(null);
  useEffect(() => {
    let live = true;
    load().then(v => { if (live) setGot({ key, v }); }, () => { if (live) setGot({ key, v: empty }); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, tick]);
  return got && got.key === key ? got.v : empty;
}

const NONE: never[] = [];

/** 左欄「作品」與「對話」兩區。載入失敗只是列表空著(閱讀區自己會顯示錯誤)。 */
export default function Rail({ current, onPick, onPickSession, onLoaded, refresh = 0 }: {
  current: string | null;
  onPick: (slug: string) => void;
  onPickSession: (slug: string, session: string) => void;
  /** 作品清單載入後通知(依最近活動排序,第一篇最近)。 */
  onLoaded?: (works: Work[]) => void;
  /** 數字一變就重抓三份清單(分析跑完、剛交稿)。 */
  refresh?: number;
}) {
  const t = useT();
  const chars = useCharacters();
  const [all, setAll] = useState(false);
  const works = useLoaded<Work[] | null>(() => api.works(), "", null, refresh);
  const recent = useLoaded<RecentSession[]>(() => api.recentSessions(), "", NONE, refresh);
  const mine = useLoaded<SessionRow[]>(() => current ? api.sessions(current) : Promise.resolve(NONE), current, NONE, refresh);
  useEffect(() => setAll(false), [current]);
  useEffect(() => { if (works) onLoaded?.(works); }, [works]);   // eslint-disable-line react-hooks/exhaustive-deps

  const shown = all ? mine : mine.slice(0, RECENT);
  return (
    <div className="rail-lists">
      <section aria-label={t("rail.works")}>
        <h2 className="rail-h">{t("rail.works")}</h2>
        <ul>
          {works?.length === 0 && <li><p className="rail-meta">{t("rail.firstDraft")}</p></li>}
          {(works ?? NONE).map(w => {
            const open = w.slug === current;
            return (
              <li key={w.slug}>
                <button type="button" className="rail-work" aria-current={open ? "true" : undefined}
                  onClick={() => onPick(w.slug)}>
                  <span className="rail-title">{w.title}</span>
                  <span className="rail-meta">
                    {ANALYZING.includes(String(w.state)) ? (
                      <><span className="rail-dots" aria-hidden="true"><i /><i /><i /></span> {t("rail.reading")}</>
                    ) : typeof w.version === "number" && typeof w.chars === "number" ? (
                      `${t("rail.version", { n: w.version })} · ${t("rail.chars", { n: w.chars })}`
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
