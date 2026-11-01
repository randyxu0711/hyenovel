import { useCallback, useEffect, useRef, useState } from "react";
import { api, DashError, type SessionRow, type Turn, type TalkMessage } from "./api";
import { useCharacters } from "./useCharacters";
import { useSeen } from "./useSeen";

const WHO_KEY = "hyenovel.companion";
const read = (): string | null => { try { return localStorage.getItem(WHO_KEY); } catch { return null; } };
const write = (v: string) => { try { localStorage.setItem(WHO_KEY, v); } catch { /* 存不了也照用 */ } };

const draftKey = (slug: string) => `hyenovel.draft.${slug}`;
const readDraft = (slug: string | null): string => {
  if (!slug) return "";
  try { return localStorage.getItem(draftKey(slug)) ?? ""; } catch { return ""; }
};
const writeDraft = (slug: string, text: string) => {
  try { if (text) localStorage.setItem(draftKey(slug), text); else localStorage.removeItem(draftKey(slug)); } catch { /* 存不了就算了 */ }
};

/** 記住的陪讀者(要在清單裡),沒有就預設。進門畫面用它決定誰接話。 */
export function companionId(chars: { list: { id: string }[]; defaultId: string }): string {
  const saved = read();
  return saved && chars.list.some(c => c.id === saved) ? saved : chars.defaultId;
}

/** 與 den/config.py 的 MAX_CHAT_CHARS 一致(den/tests/test_app_errors.py 比對)。 */
export const MAX_CHAT = 8000;

export type Pending = { text: string; quotes: string[] };
const asError = (e: unknown) => (e instanceof DashError ? e : new DashError(0, "unknown"));

/** 一篇作品上的對話:局清單、目前這局的逐字稿、串流中的字、誰在陪讀、草稿。
 *  version = 正在看的版本(undefined = 最新);逐字稿裡的引文位置(spans)都對這一版。 */
export function useTalk(slug: string | null, version?: number) {
  const chars = useCharacters();
  const { markSeen } = useSeen();
  // 記住的 id 要對照清單:找不到就當作沒選過、用預設。
  const saved = read();
  const [picked, setPicked] = useState<string | null>(saved && chars.list.some(c => c.id === saved) ? saved : null);
  const setWho = useCallback((id: string) => { write(id); setPicked(id); }, []);

  const [turns, setTurns] = useState<Turn[]>([]);
  const [spansV, setSpansV] = useState<number | undefined>(version);   // turns 的 spans 是對哪一版
  const [session, setSession] = useState<string | null>(null);
  const [legacy, setLegacy] = useState(false);
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [streaming, setStreaming] = useState<string | null>(null);   // null = 沒在串流
  const [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState<DashError | null>(null);
  const [draftOf, setDraftOf] = useState<{ slug: string | null; text: string }>(() => ({ slug, text: readDraft(slug) }));
  const draft = draftOf.slug === slug ? draftOf.text : readDraft(slug);
  const epoch = useRef(0);       // 換作品/換局/送出後,舊的回應不准再寫進來
  const touched = useRef(false); // 使用者已經自己選局或送出:不再自動打開最近那局
  const now = useRef({ slug, version, draft });
  now.current = { slug, version, draft };

  // 沒選過人時,既有的局由最後說話的那位接著陪讀(舊局只有 mode 也照樣對到角色)。
  const last = [...turns].reverse().find(t => t.role === "assistant");
  const inherited = last ? chars.byId(last.character, last.mode).id : null;
  const whoId = picked ?? inherited ?? chars.defaultId;

  const setDraft = useCallback((v: string | ((d: string) => string)) => {
    const s = now.current.slug;
    const text = typeof v === "function" ? v(now.current.draft) : v;
    now.current.draft = text;
    if (s) writeDraft(s, text);
    setDraftOf({ slug: s, text });
  }, []);

  /** 抓一局的逐字稿(對目前看的版本)。 */
  const load = useCallback((id: string) => {
    const mine = ++epoch.current;
    const v = now.current.version;
    setError(null);
    api.session(id, v).then(d => {
      if (epoch.current !== mine) return;
      setTurns(d.turns); setSession(d.session); setLegacy(d.legacy); setSpansV(v);
    }, e => { if (epoch.current === mine) setError(asError(e)); });
  }, []);

  const refreshSessions = useCallback((s: string, then?: (rows: SessionRow[]) => void) => {
    api.sessions(s).then(rows => {
      if (now.current.slug !== s) return;
      setSessions(rows);
      then?.(rows);
    }, () => { /* 清單抓不到:選單空著,目前這局照用 */ });
  }, []);

  // 換作品:清空,抓局清單;使用者還沒動作就打開最近那局。
  useEffect(() => {
    ++epoch.current;
    touched.current = false;
    setTurns([]); setSession(null); setLegacy(false); setSessions([]); setStreaming(null); setPending(null); setError(null);
    if (!slug) return;
    refreshSessions(slug, rows => {
      if (touched.current || !rows.length) return;
      touched.current = true;
      load(rows.reduce((a, b) => (b.last_at > a.last_at ? b : a)).session);
    });
  }, [slug, load, refreshSessions]);

  // 換版本:目前這局照新版本重抓位置(串流中先不動,串流結束再抓)。
  // 在 spansV 追上之前,呼叫端不該把 spans 畫到稿上。
  const sessionRef = useRef(session);
  sessionRef.current = session;
  const busy = streaming !== null;
  useEffect(() => {
    if (busy || spansV === version) return;
    if (sessionRef.current) load(sessionRef.current);
    else setSpansV(version);
  }, [version, busy, spansV, load]);

  const open = useCallback((id: string) => { touched.current = true; load(id); }, [load]);
  const fresh = useCallback(() => {
    touched.current = true;
    ++epoch.current;
    setTurns([]); setSession(null); setLegacy(false); setError(null); setSpansV(now.current.version);
  }, []);

  /** 回傳這一輪有沒有成功存下(呼叫端據此清掉帶著的引文)。 */
  const send = useCallback(async (message: string, quotes: string[], character?: string): Promise<boolean> => {
    if (!slug || streaming !== null || legacy) return false;
    touched.current = true;
    const mine = ++epoch.current;
    const live = () => epoch.current === mine;
    setError(null); setStreaming(""); setPending({ text: message, quotes });
    let acc = "", got = false, ok = false;
    const fail = (e: DashError) => { if (live()) { setError(e); setDraft(d => d || message); } };
    try {
      for await (const ev of api.talk(slug, { session, message, character: character ?? whoId, quotes })) {
        if (!live()) return false;
        if (!got) { got = true; setDraft(""); }
        if (ev.event === "token") { acc += ev.data.text; setStreaming(acc); }
        else if (ev.event === "message") {
          const d: TalkMessage = ev.data, ts = Date.now() / 1000;
          // message 的 spans 對最新版;看舊版時先不帶位置,下面以 ?v= 重抓
          const old = now.current.version !== undefined;
          setSession(d.session_id);
          setTurns(t => [...t,
            { role: "user", text: message, ts, mode: null, character: null, quotes, spans: [] },
            { role: "assistant", text: d.text, ts, mode: d.mode, character: d.character, quotes: [], spans: old ? [] : d.spans }]);
          markSeen(slug);
          ok = true;
          if (old) {
            const v = now.current.version;
            api.session(d.session_id, v).then(s => {
              if (epoch.current === mine) { setTurns(s.turns); setSpansV(v); }
            }, () => { /* 重抓不到:這輪只是沒有位置 */ });
          }
        } else if (ev.event === "error") {
          fail(new DashError(0, ev.data?.code ?? "unknown", {}, ev.data?.message ?? ""));
        }
      }
    } catch (e) {
      fail(asError(e));
    }
    if (live()) {
      setStreaming(null); setPending(null);
      if (ok) refreshSessions(slug);
    }
    return ok;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, session, whoId, streaming, legacy, setDraft, refreshSessions]);

  return {
    turns, streaming, pending, send, whoId, setWho, session, error, draft, setDraft,
    sessions, open, fresh, legacy, spansV,
  };
}

export type Talk = ReturnType<typeof useTalk>;
