import { sseFetch, type SSEEvent } from "../data/client";

/** 與 den/app.py 的 ERROR_CODES 一致(加 den-down);den/tests/test_app_errors.py 比對兩份。 */
export const DEN_ERROR_CODES = [
  "bad-slug", "unknown-work", "bad-part", "not-analyzed", "no-notes", "no-feedback",
  "nothing-running", "unknown-session", "busy", "quote-not-in-source", "quote-too-long",
  "empty-story", "story-too-long", "unknown-slug-ref", "file-too-large", "extract-failed",
  "no-runner", "nothing-to-resume", "bad-host", "bad-origin", "bad-token", "bad-launch-code",
  "unknown-character", "unknown-session-id", "ambiguous-session",
  "quote-needs-message", "too-many-quotes", "unknown-version", "legacy-session", "usage-limit", "no-response", "commit-failed", "chat-failed",
  "den-down",
];

export class DashError extends Error {
  constructor(public status: number, public code: string, public params: Record<string, unknown> = {}, detail = "") {
    super(detail || code);
  }
}

export type LText = { "zh-Hant"?: string; en?: string };
export type ColorPair = { fill: string; text: string };
export type Character = {
  id: string; mode: string; name: LText; line: LText;
  avatar: { kind: string; seed: string };
  colors: { light: ColorPair; dark: ColorPair };
  voice: string;
  mark: "pencil" | "highlighter" | "circle";
};
export type ThemeTokens = Record<string, string>;
export type Theme = { id: string; name: LText; source: string; light: ThemeTokens; dark: ThemeTokens };

export type Span = { quote: string; start: number | null; end: number | null };
export type Work = {
  slug: string; title: string; version: number; chars: number; updated_at: number; state: string; [k: string]: unknown;
};
export type WorkDetail = {
  slug: string; title: string; version: number; text: string; state: string;
  job_id: number | null; notes_ready: boolean; versions: number[];
};
export type SessionRow = {
  session: string; started_at: number; last_at: number; turns: number;
  character: string | null; mode: string | null; preview: string; version: number | null; legacy: boolean;
};
export type RecentSession = Omit<SessionRow, "version"> & { slug: string; title: string };
export type Turn = {
  role: string; text: string; ts: number; mode: string | null; character: string | null; quotes: string[]; spans: Span[];
};
/** den/discuss.py 的 message 事件資料。 */
export type TalkMessage = {
  role: "assistant"; text: string; session_id: string; mode: string; character: string; spans: Span[];
};
export type Estimate = { seconds: number; output_tokens: number; basis: number };
export type SubmitResult = { slug: string; title: string; version: number; new_version: boolean; reused: boolean };
export type SessionDetail = { session: string; slug: string; title: string; turns: Turn[]; legacy: boolean; version: number };
export type WorkMap = {
  version: number; analysis_version: number | null; notes_version: number | null;
  beats: { id: string; label: string; intensity: number | null; span: Span | null }[];
  motifs: { id: string; label: string; spans: Span[] }[];
  notes: { read: string; one_line: string; points: { kind: string; title: string; body: string; question: string | null; spans: Span[] }[] } | null;
};

/** 非 2xx 回應 → DashError(讀 den 的 {detail, code, params})。request 與串流共用。 */
async function throwDashError(res: Response): Promise<never> {
  let body: any = {};
  try { body = await res.json(); } catch { /* 非 JSON 的錯誤 */ }
  throw new DashError(res.status, body.code ?? "unknown", body.params ?? {}, typeof body.detail === "string" ? body.detail : "");
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new DashError(0, "den-down");
  }
  if (!res.ok) await throwDashError(res);
  return res.json() as Promise<T>;
}

const post = (body: unknown): RequestInit => ({
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

/** 非 2xx 由 throwDashError 接手(保留 den 的 code);網路斷(TypeError)→ den-down。 */
async function* stream(url: string, init?: RequestInit): AsyncGenerator<SSEEvent> {
  try {
    yield* sseFetch(url, init, throwDashError);
  } catch (e) {
    if (e instanceof DashError) throw e;
    if (e instanceof TypeError) throw new DashError(0, "den-down");
    throw new DashError(0, "unknown");
  }
}

const vq = (v?: number) => (v === undefined ? "" : `?v=${v}`);

export const api = {
  works: async () => (await request<{ works: Work[] }>("/api/works")).works,
  work: (slug: string, v?: number) => request<WorkDetail>(`/api/works/${encodeURIComponent(slug)}${vq(v)}`),
  map: (slug: string, v?: number) => request<WorkMap>(`/api/works/${encodeURIComponent(slug)}/map${vq(v)}`),
  sessions: async (slug: string, opts: { legacy?: boolean } = {}) =>
    (await request<{ sessions: SessionRow[] }>(
      `/api/works/${encodeURIComponent(slug)}/sessions${opts.legacy ? "?legacy=1" : ""}`)).sessions,
  session: (session: string, v?: number) => request<SessionDetail>(`/api/sessions/${encodeURIComponent(session)}${vq(v)}`),
  recentSessions: async (limit = 20, opts: { legacy?: boolean } = {}) =>
    (await request<{ sessions: RecentSession[] }>(`/api/sessions?limit=${limit}${opts.legacy ? "&legacy=1" : ""}`)).sessions,
  characters: () => request<{ characters: Character[]; default: string }>("/api/characters"),
  themes: () => request<{ themes: Theme[]; default: string }>("/api/themes"),
  estimate: async (chars: number) =>
    (await request<{ estimate: Estimate | null }>(`/api/estimate?chars=${chars}`)).estimate,
  extract: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ filename: string; text: string; chars: number }>("/api/extract", { method: "POST", body: fd });
  },
  submit: (text: string, title?: string) =>
    request<SubmitResult>("/api/stories", post({ text, title })),
  /** resumeOnly:只接續停住的那次分析,沒有可續的就 409 nothing-to-resume(不開新的一次)。 */
  startJob: (slug: string, opts: { resumeOnly?: boolean } = {}) =>
    request<{ job_id: number }>("/api/jobs", post({ kind: "critique", slug, ...(opts.resumeOnly ? { resume_only: true } : {}) })),
  jobEvents: (jobId: number) => stream(`/api/jobs/${jobId}/events`),
  /** session 為 null = 開新局(局 id 在 done 事件裡回)。 */
  talk: (slug: string, body: { session: string | null; message: string; character: string; quotes: string[] }) =>
    stream(`/api/discuss/${encodeURIComponent(slug)}`, post({
      session_id: body.session, message: body.message, character: body.character, quotes: body.quotes,
    })),
};
