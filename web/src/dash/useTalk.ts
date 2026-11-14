import { useCallback, useEffect, useRef, useState } from "react";
import { api, DashError, type Adopted, type AttachIn, type Attachment, type SessionRow, type Turn, type TurnMemory, type TurnReaction, type TalkMessage } from "./api";
import { cpLength } from "./cp";
import { liveQuotes } from "./liveQuotes";
import { DRAW_MS, markId, type Mark } from "./Paper";
import { marksFrom } from "./Side";
import { useCharacters } from "./useCharacters";
import { useSeen } from "./useSeen";

let defaultWho: string | null = null;
const whoListeners = new Set<(id: string) => void>();
const announce = (v: string) => {
  defaultWho = v;
  whoListeners.forEach(fn => fn(v));   // 指令框、設定頁換人:開著的對話立刻跟著換
};

const draftKey = (slug: string) => `hyenovel.draft.${slug}`;
const readDraft = (slug: string | null): string => {
  if (!slug) return "";
  try { return localStorage.getItem(draftKey(slug)) ?? ""; } catch { return ""; }
};
const writeDraft = (slug: string, text: string) => {
  try { if (text) localStorage.setItem(draftKey(slug), text); else localStorage.removeItem(draftKey(slug)); } catch { /* 存不了就算了 */ }
};

/** den 給的全域預設陪讀者:載入角色時設一次。 */
export const initCompanion = (id: string | null) => { defaultWho = id; };

/** 設定頁、指令框換全域預設:den 存好才生效,存不下就把錯誤丟給呼叫者。 */
export async function setCompanion(id: string): Promise<void> {
  await api.setDefaultCharacter(id);
  announce(id);
}

/** 全域預設陪讀者(要在清單裡),沒有就用清單的預設。進門畫面與新局用它。 */
export function companionId(chars: { active: { id: string }[]; defaultId: string }): string {
  return defaultWho && chars.active.some(c => c.id === defaultWho) ? defaultWho : chars.defaultId;
}

/** 與 den/config.py 的 MAX_CHAT_CHARS 一致(den/tests/test_app_errors.py 比對)。 */
export const MAX_CHAT = 8000;

/** 串流剛結束的作者發言:den 先存作者、再存回覆,所以是回覆的前一號;陪讀者先開口的那輪沒有作者發言。 */
export const userSeq = (message: string, replySeq: number): number | undefined => (message ? replySeq - 1 : undefined);

export type Pending = { text: string; quotes: string[] };

/** 能丟進對話的稿:只收 .md / .txt(與 submit_work 同規則)。 */
export const attachable = (f: File) => /\.(md|txt)$/i.test(f.name);
const stem = (name: string) => name.replace(/\.(md|txt)$/i, "");
const still = () => !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const asError = (e: unknown) => (e instanceof DashError ? e : new DashError(0, "unknown"));

/** 一篇作品上的對話:局清單、目前這局的逐字稿、串流中的字、誰在陪讀、草稿、邊說邊畫的痕跡。
 *  version = 正在看的版本(undefined = 最新);逐字稿裡的引文位置(spans)都對這一版。
 *  source = 最新版原文(稿上正顯示最新版時才給):串流中的引文在這裡逐字找位置。
 *  wanted = 換作品時要打開的局(網址的 ?s=;不在這篇的清單裡就照常開最近那局)。
 *  onSession = 使用者選局、開新局、新局第一輪存下時通知(呼叫端寫回網址)。
 *  reloadKey = 外面遞增 → 目前這局照目前版本重抓(交了新版,位置要對到新稿)。 */
export function useTalk(slug: string | null, version?: number, source: string | null = null,
  wanted: string | null = null, onSession?: (id: string | null) => void, reloadKey = 0) {
  const chars = useCharacters();
  const { markSeen } = useSeen();
  // 對話裡換人只影響這一局;換作品、開局、開新局就清掉。
  const [picked, setPicked] = useState<string | null>(null);
  const setWho = setPicked;
  useEffect(() => { whoListeners.add(setPicked); return () => { whoListeners.delete(setPicked); }; }, []);

  const [turns, setTurns] = useState<Turn[]>([]);
  const [spansV, setSpansV] = useState<number | undefined>(version);   // turns 的 spans 是對哪一版
  const [session, setSession] = useState<string | null>(null);
  const [legacy, setLegacy] = useState(false);
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [bound, setBound] = useState<string | null>(slug);   // 這局綁的作品(沒作品的局 = null)
  const [staged, setStaged] = useState<AttachIn | null>(null);   // 作者打了一半字時丟的稿:隨下一輪送出
  const [working, setWorking] = useState(false);   // clear / compact / 開成作品進行中
  const [streaming, setStreaming] = useState<string | null>(null);   // null = 沒在串流
  const [redoing, setRedoing] = useState<number | null>(null);       // 正在重說的那一格(串流的字放在那格)
  const [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState<DashError | null>(null);
  const [draftOf, setDraftOf] = useState<{ slug: string | null; text: string }>(() => ({ slug, text: readDraft(slug) }));
  const draft = draftOf.slug === slug ? draftOf.text : readDraft(slug);
  const abort = useRef<AbortController | null>(null);
  const epoch = useRef(0);       // 換作品/換局/送出後,舊的回應不准再寫進來
  const touched = useRef(false); // 使用者已經自己選局或送出:不再自動打開最近那局
  const now = useRef({ slug, version, draft, source, turns, wanted, onSession });
  now.current = { slug, version, draft, source, turns, wanted, onSession };
  const shownSession = useRef(session);
  shownSession.current = session;

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

  // 這局沒換過人時,由最後說話的那位接著陪讀。
  const last = [...turns].reverse().find(t => t.role === "assistant");
  const usable = (id: string | null | undefined) => (id && chars.active.some(c => c.id === id) ? id : null);
  const whoId = usable(picked) ?? usable(last?.character) ?? companionId(chars);

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
      setAttachments(d.attachments); setBound(d.slug);
    }, e => { if (epoch.current === mine) setError(asError(e)); });
  }, [stopDrawing]);

  const refreshSessions = useCallback((s: string, then?: (rows: SessionRow[]) => void) => {
    api.sessions(s).then(rows => {
      if (now.current.slug !== s) return;
      setSessions(rows);
      then?.(rows);
    }, () => { /* 清單抓不到:選單空著,目前這局照用 */ });
  }, []);

  // 換作品:清空,抓局清單;使用者還沒動作就打開網址指定的局,沒有就最近那局。
  useEffect(() => {
    ++epoch.current;
    touched.current = false;
    stopDrawing();
    setPicked(null);
    setTurns([]); setSession(null); setLegacy(false); setSessions([]); setStreaming(null); setPending(null); setError(null);
    setAttachments([]); setBound(slug); setStaged(null);
    if (!slug) {
      if (now.current.wanted) { touched.current = true; load(now.current.wanted); }
      return;
    }
    refreshSessions(slug, rows => {
      if (touched.current || !rows.length) return;
      touched.current = true;
      const asked = rows.find(r => r.session === now.current.wanted);
      load((asked ?? rows.reduce((a, b) => (b.last_at > a.last_at ? b : a))).session);
    });
  }, [slug, load, refreshSessions, stopDrawing]);

  // 換版本或 reloadKey 變了:目前這局照新版本重抓位置(串流中先不動,串流結束再抓)。兩者同時變只抓一次。
  // 在 spansV 追上之前,呼叫端不該把 spans 畫到稿上。
  const sessionRef = useRef(session);
  sessionRef.current = session;
  const busy = streaming !== null;
  const loadedKey = useRef(reloadKey);
  useEffect(() => {
    if (busy || (spansV === version && loadedKey.current === reloadKey)) return;
    loadedKey.current = reloadKey;
    if (sessionRef.current) load(sessionRef.current);
    else setSpansV(version);
  }, [version, busy, spansV, load, reloadKey]);

  const open = useCallback((id: string) => { touched.current = true; setPicked(null); load(id); now.current.onSession?.(id); }, [load]);
  const fresh = useCallback(() => {
    touched.current = true;
    now.current.onSession?.(null);
    ++epoch.current;
    stopDrawing();
    setPicked(null);
    setTurns([]); setSession(null); setLegacy(false); setError(null); setSpansV(now.current.version);
    setAttachments([]); setBound(now.current.slug); setStaged(null);
  }, [stopDrawing]);

  /** 邊說邊畫:串流中逐字找引文畫線;message 到了把痕跡交給逐字稿,先前沒找到的補畫;看舊版時以 ?v= 重抓位置。 */
  const tracker = (who: string) => {
    // 看舊版時 source 是 null:串流中不畫(位置對不上這張稿)
    const src = now.current.version === undefined ? now.current.source : null;
    const lq = liveQuotes();
    const shown = new Set(marksFrom(now.current.turns, chars).map(m => m.id));   // 已在稿上的不重畫
    return {
      push(text: string) {
        if (src === null) return;
        const found: Mark[] = [];
        for (const q of lq.push(text)) {
          const at = src.indexOf(q);   // UTF-16 位移(不是 den 的位移),換成 code point
          if (at < 0) continue;        // 逐字找不到:等 message 的 spans
          const start = cpLength(src.slice(0, at));
          const m = { start, end: start + cpLength(q), character: who, id: markId(start, start + cpLength(q), who) };
          if (shown.has(m.id)) continue;
          shown.add(m.id); found.push(m);
        }
        if (found.length) { setLiveMarks(ms => [...ms, ...found]); draw(found.map(m => m.id)); }
      },
      settle(d: TalkMessage, old: boolean, mine: number) {
        setLiveMarks([]);
        if (old) {
          const v = now.current.version;
          api.session(d.session_id, v).then(s => {
            if (epoch.current === mine) { setTurns(s.turns); setSpansV(v); }
          }, () => { /* 重抓不到:這輪只是沒有位置 */ });
          return;
        }
        const by = chars.byId(d.character).id;
        const late: string[] = [];
        for (const s of d.spans) {
          if (s.start === null || s.end === null) continue;
          const id = markId(s.start, s.end, by);
          if (!shown.has(id)) { shown.add(id); late.push(id); }
        }
        draw(late);
      },
    };
  };

  /** 回傳這一輪有沒有成功存下(呼叫端據此清掉帶著的引文)。 */
  const send = useCallback(async (message: string, quotes: string[], dropped: AttachIn | null = null): Promise<boolean> => {
    if (streaming !== null || legacy || working) return false;
    const carried = dropped ?? staged ?? undefined;
    touched.current = true;
    const mine = ++epoch.current;
    const live = () => epoch.current === mine;
    setError(null); setStreaming(""); setPending(message ? { text: message, quotes } : null);
    let acc = "", got = false, ok = false;
    const live_ = tracker(chars.byId(whoId).id);
    const fail = (e: DashError) => {
      if (!live()) return;
      if (e.code !== "aborted") setError(e);
      if (!ok) setDraft(d => d || message);
    };
    const ctl = abort.current = new AbortController();
    try {
      for await (const ev of api.talk(slug, { session, message, character: whoId, quotes, attach: carried }, ctl.signal)) {
        if (!live()) return false;
        if (!got) { got = true; setDraft(""); }
        if (ev.event === "token") {
          acc += ev.data.text; setStreaming(acc);
          live_.push(ev.data.text);
        }
        else if (ev.event === "message") {
          const d: TalkMessage = ev.data, ts = Date.now() / 1000;
          // message 的 spans 對最新版;看舊版時先不帶位置,下面以 ?v= 重抓
          const old = now.current.version !== undefined;
          setSession(d.session_id);
          if (d.session_id !== session) now.current.onSession?.(d.session_id);
          setTurns(t => [...t,
            ...(message ? [{ seq: userSeq(message, d.seq), role: "user", text: message, ts, character: null, quotes, spans: [], v: d.v }] : []),
            { seq: d.seq, role: "assistant", text: d.text, ts, character: d.character, quotes: [], spans: old ? [] : d.spans, v: d.v }]);
          if (carried && d.attachment != null) {
            const n = d.attachment;
            setAttachments(as => [...as, { n, seq: userSeq(message, d.seq) ?? d.seq, name: carried.name, chars: cpLength(carried.text.trim()), adopted: false }]);
            setStaged(null);
          }
          if (slug) markSeen(slug);
          ok = true;
          live_.settle(d, old, mine);
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
      if (ok && slug) refreshSessions(slug);
    }
    return ok;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, session, whoId, streaming, legacy, working, staged, setDraft, refreshSessions, chars, draw]);

  /** 重說這局最後一則讀伴回覆:新的字在同一格串流,成功就換上新版;沒成功那格回到舊字。 */
  const regenerate = useCallback(async (seq: number): Promise<boolean> => {
    if (!session || streaming !== null || legacy || working) return false;
    const target = now.current.turns.find(x => x.seq === seq);
    if (!target) return false;
    const mine = ++epoch.current;
    const live = () => epoch.current === mine;
    setError(null); setStreaming(""); setRedoing(seq);
    let acc = "", ok = false;
    const live_ = tracker(chars.byId(target.character).id);
    const ctl = abort.current = new AbortController();
    try {
      for await (const ev of api.regenerate(session, seq, ctl.signal)) {
        if (!live()) return false;
        if (ev.event === "token") {
          acc += ev.data.text; setStreaming(acc);
          live_.push(ev.data.text);
        } else if (ev.event === "message") {
          const d: TalkMessage = ev.data;
          const old = now.current.version !== undefined;
          setTurns(ts => ts.map(x => (x.seq === seq ? {
            ...x, text: d.text, ts: Date.now() / 1000, spans: old ? [] : d.spans, v: d.v,
            reaction: null, voice: false, edited: false, variant: { n: d.variant ?? 1, total: d.variants ?? 1 },
          } : x)));
          ok = true;
          live_.settle(d, old, mine);
        } else if (ev.event === "error") {
          if (live()) setError(new DashError(0, ev.data?.code ?? "unknown", {}, ev.data?.message ?? ""));
        }
      }
    } catch (e) {
      const err = asError(e);
      if (live() && err.code !== "aborted") setError(err);
    }
    if (live()) {
      setStreaming(null); setRedoing(null);
      if (!ok) setLiveMarks([]);
    }
    return ok;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, streaming, legacy, working, chars, draw]);

  const stop = useCallback(() => { abort.current?.abort(); }, []);

  /** 純聊天的局丟稿:沒打字就直接送一輪(讀伴先回),打了一半就等下一輪一起送。 */
  const attach = useCallback(async (file: File): Promise<boolean> => {
    if (bound !== null || !attachable(file)) return false;
    const dropped = { name: stem(file.name), text: await file.text() };
    if (now.current.draft.trim()) { setStaged(dropped); return true; }
    return send("", [], dropped);
  }, [bound, send]);

  const act = async <T,>(run: (id: string) => Promise<T>): Promise<T | null> => {
    if (!session || streaming !== null || working) return null;
    setWorking(true); setError(null);
    try { return await run(session); } catch (e) { setError(asError(e)); return null; } finally { setWorking(false); }
  };
  const mark = (turn: Turn) => setTurns(ts => [...ts, turn]);
  const clear = () => act(async id => {
    const r = await api.clearSession(id);
    mark({ seq: r.seq, role: "clear", text: "", ts: Date.now() / 1000, character: null, quotes: [], spans: [] });
  });
  const compact = () => act(async id => {
    const r = await api.compactSession(id);
    mark({ seq: r.seq, role: "compact", text: r.text, ts: Date.now() / 1000, character: null, quotes: [], spans: [] });
  });
  const adopt = (n: number): Promise<Adopted | null> => act(async id => {
    const r = await api.adoptAttachment(id, n);
    setBound(r.slug);
    setAttachments(as => as.map(a => (a.n === n ? { ...a, adopted: true } : a)));
    return r;
  });

  /** 挑版、改字:den 存好就照目前版本重抓這局(不在前端自己拼)。 */
  const pickVariant = (seq: number, n: number) => act(async id => { await api.pickVariant(id, seq, n); load(id); });
  const editReply = (seq: number, text: string) => act(async id => {
    const r = await api.editReply(id, seq, text);
    if (r.edited) load(id);
    return r.edited;
  });

  const archive = async (id: string): Promise<boolean> => {
    if (streaming !== null || working) return false;
    setError(null);
    try { await api.archiveSession(id); } catch (e) { setError(asError(e)); return false; }
    setSessions(rs => rs.filter(r => r.session !== id));
    if (id === session) fresh();
    return true;
  };

  const markTurn = useCallback((forSession: string, seq: number, reaction: TurnReaction | null) => {
    if (forSession !== shownSession.current) return;
    setTurns(ts => ts.map(x => (x.seq === seq ? { ...x, reaction } : x)));
  }, []);

  const markVoice = useCallback((forSession: string, seq: number, voice: boolean) => {
    if (forSession !== shownSession.current) return;
    setTurns(ts => ts.map(x => (x.seq === seq ? { ...x, voice } : x)));
  }, []);

  const markMemories = useCallback((forSession: string, seq: number, memories: TurnMemory[]) => {
    if (forSession !== shownSession.current) return;
    setTurns(ts => ts.map(x => (x.seq === seq ? { ...x, memories } : x)));
  }, []);

  return {
    markTurn, markMemories, markVoice, regenerate, stop, redoing, pickVariant, editReply, slug, turns, streaming, pending, send, whoId, setWho, session, error, draft, setDraft,
    sessions, open, fresh, legacy, spansV, liveMarks, drawing,
    attachments, bound, staged, dropStaged: () => setStaged(null), working, attach, clear, compact, adopt, archive,
  };
}

export type Talk = ReturnType<typeof useTalk>;
