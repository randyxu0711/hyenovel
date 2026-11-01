import { useCallback, useEffect, useRef, useState } from "react";
import { api, DashError, type SessionRow, type Turn, type TalkMessage } from "./api";
import { cpLength } from "./cp";
import { liveQuotes } from "./liveQuotes";
import { markId, type Mark } from "./Paper";
import { marksFrom } from "./Side";
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
/** 畫線佇列:一次畫一筆,每筆至少這麼久。 */
export const DRAW_MS = 600;
const still = () => !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const asError = (e: unknown) => (e instanceof DashError ? e : new DashError(0, "unknown"));

/** 一篇作品上的對話:局清單、目前這局的逐字稿、串流中的字、誰在陪讀、草稿、邊說邊畫的痕跡。
 *  version = 正在看的版本(undefined = 最新);逐字稿裡的引文位置(spans)都對這一版。
 *  source = 最新版原文(稿上正顯示最新版時才給):串流中的引文在這裡逐字找位置。 */
export function useTalk(slug: string | null, version?: number, source: string | null = null) {
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
  const now = useRef({ slug, version, draft, source, turns });
  now.current = { slug, version, draft, source, turns };

  // 邊說邊畫線:串流中找到的痕跡(message 到了就交給逐字稿的 spans),與一次一筆的畫線佇列。
  const [liveMarks, setLiveMarks] = useState<Mark[]>([]);
  const [drawing, setDrawing] = useState<string | null>(null);
  const queue = useRef<string[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const next = useRef(() => {});
  next.current = () => {
    const id = queue.current.shift() ?? null;
    setDrawing(id);
    timer.current = id === null ? null : setTimeout(() => next.current(), DRAW_MS);
  };
  const draw = useCallback((ids: string[]) => {
    if (!ids.length || still()) return;   // 減動:直接終態
    queue.current.push(...ids);
    if (timer.current === null) next.current();
  }, []);
  const stopDrawing = useCallback(() => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null; queue.current = [];
    setDrawing(null); setLiveMarks([]);
  }, []);
  useEffect(() => () => { if (timer.current !== null) clearTimeout(timer.current); }, []);

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
    stopDrawing();
    const v = now.current.version;
    setError(null);
    api.session(id, v).then(d => {
      if (epoch.current !== mine) return;
      setTurns(d.turns); setSession(d.session); setLegacy(d.legacy); setSpansV(v);
    }, e => { if (epoch.current === mine) setError(asError(e)); });
  }, [stopDrawing]);

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
    stopDrawing();
    setTurns([]); setSession(null); setLegacy(false); setSessions([]); setStreaming(null); setPending(null); setError(null);
    if (!slug) return;
    refreshSessions(slug, rows => {
      if (touched.current || !rows.length) return;
      touched.current = true;
      load(rows.reduce((a, b) => (b.last_at > a.last_at ? b : a)).session);
    });
  }, [slug, load, refreshSessions, stopDrawing]);

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
    stopDrawing();
    setTurns([]); setSession(null); setLegacy(false); setError(null); setSpansV(now.current.version);
  }, [stopDrawing]);

  /** 回傳這一輪有沒有成功存下(呼叫端據此清掉帶著的引文)。 */
  const send = useCallback(async (message: string, quotes: string[], character?: string): Promise<boolean> => {
    if (!slug || streaming !== null || legacy) return false;
    touched.current = true;
    const mine = ++epoch.current;
    const live = () => epoch.current === mine;
    setError(null); setStreaming(""); setPending({ text: message, quotes });
    let acc = "", got = false, ok = false;
    const who = chars.byId(character ?? whoId).id;
    // 看舊版時 source 是 null:串流中不畫(位置對不上這張稿)
    const src = now.current.version === undefined ? now.current.source : null;
    const lq = liveQuotes();
    const shown = new Set(marksFrom(now.current.turns, chars).map(m => m.id));   // 已在稿上的不重畫
    const fail = (e: DashError) => { if (live()) { setError(e); setDraft(d => d || message); } };
    try {
      for await (const ev of api.talk(slug, { session, message, character: character ?? whoId, quotes })) {
        if (!live()) return false;
        if (!got) { got = true; setDraft(""); }
        if (ev.event === "token") {
          acc += ev.data.text; setStreaming(acc);
          if (src === null) continue;
          const found: Mark[] = [];
          for (const q of lq.push(ev.data.text)) {
            const at = src.indexOf(q);   // UTF-16 位移(不是 den 的位移),換成 code point
            if (at < 0) continue;        // 逐字找不到:等 message 的 spans
            const start = cpLength(src.slice(0, at));
            const m = { start, end: start + cpLength(q), character: who, id: markId(start, start + cpLength(q), who) };
            if (shown.has(m.id)) continue;
            shown.add(m.id); found.push(m);
          }
          if (found.length) { setLiveMarks(ms => [...ms, ...found]); draw(found.map(m => m.id)); }
        }
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
          // 串流中的痕跡交給逐字稿;spans 裡先前沒找到的(如只差標點)此時補畫
          setLiveMarks([]);
          if (!old) {
            const by = chars.byId(d.character, d.mode).id;
            const late: string[] = [];
            for (const s of d.spans) {
              if (s.start === null || s.end === null) continue;
              const id = markId(s.start, s.end, by);
              if (!shown.has(id)) { shown.add(id); late.push(id); }
            }
            draw(late);
          }
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
      if (!ok) setLiveMarks([]);   // 這輪沒存下:串流中畫的痕跡不留
      if (ok) refreshSessions(slug);
    }
    return ok;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, session, whoId, streaming, legacy, setDraft, refreshSessions, chars, draw]);

  return {
    turns, streaming, pending, send, whoId, setWho, session, error, draft, setDraft,
    sessions, open, fresh, legacy, spansV, liveMarks, drawing,
  };
}

export type Talk = ReturnType<typeof useTalk>;
