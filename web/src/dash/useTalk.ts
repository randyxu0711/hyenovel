import { useCallback, useEffect, useRef, useState } from "react";
import { api, DashError, type Turn } from "./api";
import { useCharacters } from "./useCharacters";

const WHO_KEY = "hyenovel.companion";
const read = (): string | null => { try { return localStorage.getItem(WHO_KEY); } catch { return null; } };
const write = (v: string) => { try { localStorage.setItem(WHO_KEY, v); } catch { /* 存不了也照用 */ } };

/** 與 den/config.py 的 MAX_CHAT_CHARS 一致(den/tests/test_app_errors.py 比對)。 */
export const MAX_CHAT = 8000;

export type Pending = { text: string; quotes: string[] };

/** 一篇作品上的一局對話:逐字稿、串流中的字、誰在陪讀。 */
export function useTalk(slug: string | null, initialSession: string | null = null) {
  const chars = useCharacters();
  // 記住的 id 要對照清單:找不到就當作沒選過、用預設。
  const saved = read();
  const [picked, setPicked] = useState<string | null>(saved && chars.list.some(c => c.id === saved) ? saved : null);
  const setWho = useCallback((id: string) => { write(id); setPicked(id); }, []);

  const [turns, setTurns] = useState<Turn[]>([]);
  const [session, setSession] = useState<string | null>(null);
  const [streaming, setStreaming] = useState<string | null>(null);   // null = 沒在串流
  const [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState<DashError | null>(null);
  const [draft, setDraft] = useState("");
  const epoch = useRef(0);
  // 沒選過人時,既有的局由最後說話的那位接著陪讀(舊局只有 mode 也照樣對到角色)。
  const last = [...turns].reverse().find(t => t.role === "assistant");
  const inherited = last ? chars.byId(last.character, last.mode).id : null;
  const whoId = picked ?? inherited ?? chars.defaultId;
  const chosen = picked !== null || inherited !== null;   // 換作品/換局後,舊串流的尾巴不准再寫進來

  useEffect(() => {
    const mine = ++epoch.current;
    setTurns([]); setSession(null); setStreaming(null); setPending(null); setError(null);
    if (!initialSession) return;
    api.session(initialSession).then(d => {
      if (epoch.current === mine) { setTurns(d.turns); setSession(d.session); }
    }, e => { if (epoch.current === mine) setError(e instanceof DashError ? e : new DashError(0, "unknown")); });
  }, [slug, initialSession]);

  /** 回傳這一輪有沒有成功存下(呼叫端據此清掉帶著的引文)。 */
  const send = useCallback(async (message: string, quotes: string[]): Promise<boolean> => {
    if (!slug || streaming !== null) return false;
    const mine = epoch.current;
    const live = () => epoch.current === mine;
    setError(null); setStreaming(""); setPending({ text: message, quotes });
    let acc = "", got = false, ok = false;
    const fail = (e: DashError) => { if (live()) { setError(e); setDraft(d => d || message); } };
    try {
      for await (const ev of api.talk(slug, { session, message, character: whoId, quotes })) {
        if (!live()) return false;
        if (!got) { got = true; setDraft(""); }
        if (ev.event === "token") { acc += ev.data.text; setStreaming(acc); }
        else if (ev.event === "message") {
          const d = ev.data, ts = Date.now() / 1000;
          setSession(d.session_id);
          setTurns(t => [...t,
            { role: "user", text: message, ts, mode: null, character: null, quotes },
            { role: "assistant", text: d.text, ts, mode: d.mode ?? null, character: d.character ?? null, quotes: [] }]);
          ok = true;
        } else if (ev.event === "error") {
          fail(new DashError(0, ev.data?.code ?? "unknown", {}, ev.data?.message ?? ""));
        }
      }
    } catch (e) {
      fail(e instanceof DashError ? e : new DashError(0, "unknown"));
    }
    if (live()) { setStreaming(null); setPending(null); }
    return ok;
  }, [slug, session, whoId, streaming]);

  return { turns, streaming, pending, send, whoId, chosen, setWho, session, error, draft, setDraft };
}

export type Talk = ReturnType<typeof useTalk>;
