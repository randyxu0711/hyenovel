import type { FigureSpec, Part, Pen, Pt } from "./figure/poses";
import { sseFetch, type SSEEvent } from "../data/client";

/** 與 den/app.py 的 ERROR_CODES 一致(加 den-down);den/tests/test_app_errors.py 比對兩份。 */
export const DEN_ERROR_CODES = [
  "candidates-busy", "candidates-failed",
  "bad-slug", "unknown-work", "bad-part", "not-analyzed", "no-notes", "no-feedback",
  "nothing-running", "unknown-session", "busy", "quote-not-in-source", "quote-too-long",
  "empty-story", "story-too-long", "unknown-slug-ref", "file-too-large", "extract-failed",
  "no-runner", "nothing-to-resume", "bad-host", "bad-origin", "bad-token", "bad-launch-code",
  "unknown-character", "unknown-session-id",
  "bound-session", "too-many-attachments", "empty-attachment", "attachment-too-long",
  "nothing-to-clear", "nothing-to-compact", "compact-failed", "not-archived",
  "unknown-attachment", "already-adopted",
  "session-not-of-work", "not-a-turn",
  "quote-needs-message", "too-many-quotes", "unknown-version", "legacy-session", "usage-limit", "no-response", "commit-failed", "chat-failed",
  "unknown-turn", "not-assistant-turn", "bad-mark", "comment-too-long",
  "bad-scope", "blank-memory", "slug-required", "bad-source", "quote-not-in-turn", "memory-full",
  "unknown-memory", "memory-not-current", "memory-is-current",
  "bad-card", "builtin-character",
  "not-last-turn", "unknown-variant", "blank-reply", "reply-too-long",
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
  id: string; version: number; origin: "builtin" | "imported" | "created"; archived: boolean;
  name: LText; line: LText;
  avatar: { kind: string; seed: string };
  figure?: FigureSpec | null;
  colors: { light: ColorPair; dark: ColorPair };
  voice: string;
  mark: "pencil" | "highlighter" | "circle";
  reading: string;
  examples: string;
};
export type CardDraft = { name: LText; line: LText; reading: string; examples?: string };
export type CandidateAnswers = { form: string; wish: string };
export type CandidateAgain = { reaction: string; previous: { name: string; line: string }[] };
export type Candidate = {
  name: LText; form: LText; line: LText; reading: string; sample: string;
  figure: { parts: Part[]; eyes: [Pt, Pt]; mouth: [Pt, Pt, Pt]; main: Pen; second: Pen };
  axes: string[]; card: unknown; warnings: string[];
  examples: { who: "author" | "char"; text: string }[][];
};
export type ThemeTokens = Record<string, string>;
export type Theme = { id: string; name: LText; source: string; light: ThemeTokens; dark: ThemeTokens };

export type Span = { quote: string; start: number | null; end: number | null };
export type Work = {
  slug: string; title: string; version: number; chars: number; updated_at: number; state: string;
  /** 目前分析的張力指紋(beat intensity 依文本順序);沒分析 = [] */
  curve?: number[];
  [k: string]: unknown;
};
export type WorkDetail = {
  slug: string; title: string; version: number; text: string; state: string;
  job_id: number | null; notes_ready: boolean; versions: number[];
  /** 每一版:建立時間(秒)、那版有沒有分析 / 筆記(不論 current) */
  history?: { n: number; at: number; analysed: boolean; noted: boolean }[];
};
export type SessionRow = {
  session: string; started_at: number; last_at: number; turns: number;
  character: string | null; preview: string; version: number | null; legacy: boolean;
  /** 這局發言當下的原文版本範圍 [lo, hi] */
  versions?: [number, number] | null;
};
export type RecentSession = Omit<SessionRow, "version"> & { slug: string | null; title: string | null };
export type ReactionMark = "stopped" | "misread";
export type TurnReaction = { mark: ReactionMark; comment: string | null };
export type ArchivedSession = { session: string; slug: string | null; title: string | null; preview: string; last_at: number | null; archived_at: number };
export type MemoryScope = "author" | "work";
export type TurnMemory = { id: number; scope: MemoryScope };
export type Memory = {
  id: number; root: number; scope: MemoryScope; slug: string | null; title: string | null; text: string;
  quote: string | null; session: string | null; seq: number | null;
  valid_from: number; learned_at: number; invalidated_at: number | null;
};
export type MemoryList = { memories: Memory[]; caps: { author: number; work: number } };
export type RememberBody = { scope: MemoryScope; text: string; slug?: string; session?: string; seq?: number; quote?: string };
export type Turn = {
  /** 這一局裡的序號;陪讀者先開口那輪的 user 那則沒有 */
  seq?: number;
  reaction?: TurnReaction | null;
  memories?: TurnMemory[];
  role: string; text: string; ts: number; character: string | null; quotes: string[]; spans: Span[];
  /** 這則發生時的稿版本;剛串流進來、還沒重新載入的沒有;沒作品的局是 null */
  v?: number | null;
  /** 讀伴回覆才有:作者改過字、標了「像它」、這格現在留下的是第幾版(共幾版) */
  edited?: boolean;
  voice?: boolean;
  variant?: { n: number; total: number };
};
/** den/discuss.py 的 message 事件資料。 */
export type TalkMessage = {
  role: "assistant"; text: string; session_id: string; seq: number; character: string; spans: Span[];
  /** 這輪存下當時的最新版(問與答都算這一版);沒作品的局是 null */
  v?: number | null;
  /** 這輪帶的附件存成第幾份 */
  attachment?: number | null;
  /** 重說才有:新版號與總版數 */
  variant?: number;
  variants?: number;
};
export type Attachment = { n: number; seq: number; name: string; chars: number; adopted: boolean };
export type AttachIn = { name: string; text: string };
export type Adopted = { slug: string; title: string | null; version: number; reused: boolean };
export type Estimate = { seconds: number; output_tokens: number; basis: number };
export type SubmitResult = { slug: string; title: string; version: number; new_version: boolean; reused: boolean };
export type SessionDetail = {
  session: string; slug: string | null; title: string | null; turns: Turn[]; legacy: boolean; version: number | null;
  attachments: Attachment[];
};
export type WorkMap = {
  version: number; analysis_version: number | null; notes_version: number | null;
  beats: { id: string; label: string; intensity: number | null; span: Span | null }[];
  motifs: { id: string; label: string; spans: Span[] }[];
  notes: { read: string; one_line: string; points: { kind: string; title: string; body: string; question: string | null; spans: Span[] }[] } | null;
  /** 舊分析的引文在這版還剩幾句;沒分析或分析就是這版 → null */
  drift: { total: number; lost: number; orphaned: { id: string; type: string; label: string }[] } | null;
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
  if (res.status === 204) return undefined as T;
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
    if (init?.signal?.aborted) throw new DashError(0, "aborted");
    if (e instanceof DashError) throw e;
    if (e instanceof TypeError) throw new DashError(0, "den-down");
    throw new DashError(0, "unknown");
  }
}

const BLANK_TURN: Pick<Turn, "character" | "quotes" | "spans" | "text"> = { character: null, quotes: [], spans: [], text: "" };
const sessionUrl = (session: string) => `/api/sessions/${encodeURIComponent(session)}`;
const reactionUrl = (session: string, seq: number) => `${sessionUrl(session)}/turns/${seq}/reaction`;
const turnUrl = (session: string, seq: number, what: string) => `${sessionUrl(session)}/turns/${seq}/${what}`;
const vq = (v?: number) => (v === undefined ? "" : `?v=${v}`);

export const api = {
  works: async () => (await request<{ works: Work[] }>("/api/works")).works,
  work: (slug: string, v?: number) => request<WorkDetail>(`/api/works/${encodeURIComponent(slug)}${vq(v)}`),
  map: (slug: string, v?: number) => request<WorkMap>(`/api/works/${encodeURIComponent(slug)}/map${vq(v)}`),
  sessions: async (slug: string, opts: { legacy?: boolean } = {}) =>
    (await request<{ sessions: SessionRow[] }>(
      `/api/works/${encodeURIComponent(slug)}/sessions${opts.legacy ? "?legacy=1" : ""}`)).sessions,
  session: async (session: string, v?: number) => {
    const d = await request<SessionDetail>(`${sessionUrl(session)}${vq(v)}`);
    return { ...d, attachments: d.attachments ?? [], turns: (d.turns ?? []).map(x => ({ ...BLANK_TURN, ...x })) };
  },
  recentSessions: async (limit = 20, opts: { legacy?: boolean } = {}) =>
    (await request<{ sessions: RecentSession[] }>(`/api/sessions?limit=${limit}${opts.legacy ? "&legacy=1" : ""}`)).sessions,
  characters: () => request<{ characters: Character[]; default: string }>("/api/characters"),
  setDefaultCharacter: (character: string) =>
    request<{ default: string }>("/api/characters/default", { ...post({ character }), method: "PUT" }),
  importCharacter: (card: unknown, confirm: boolean) =>
    request<{ imported: boolean; warnings: string[]; character?: Character }>("/api/characters/import", post({ card, confirm })),
  characterCardUrl: (id: string) => `/api/characters/${encodeURIComponent(id)}/card`,
  characterCandidates: (answers: CandidateAnswers, lang: string, again?: CandidateAgain) =>
    request<{ seed: number; candidates: Candidate[] }>("/api/characters/candidates", post({ answers, lang, ...again })),
  reviseCandidate: (candidate: Candidate, feedback: string, lang: string) =>
    request<Candidate>("/api/characters/candidates/revise", post({ candidate, feedback, lang })),
  createCharacter: (candidate: Candidate, confirm: boolean) =>
    request<{ created: boolean; warnings?: string[]; character?: Character }>("/api/characters", post({ candidate, confirm })),
  copyCharacter: (id: string) =>
    request<{ character: Character }>(`/api/characters/${encodeURIComponent(id)}/copy`, { method: "POST" }),
  editCharacter: (id: string, draft: CardDraft, confirm: boolean) =>
    request<{ edited: boolean; warnings?: string[]; character?: Character }>(
      `/api/characters/${encodeURIComponent(id)}`, { ...post({ ...draft, confirm }), method: "PATCH" }),
  archiveCharacter: (id: string) =>
    request<{ archived: string }>(`/api/characters/${encodeURIComponent(id)}`, { method: "DELETE" }),
  themes: () => request<{ themes: Theme[]; default: string }>("/api/themes"),
  estimate: async (chars: number) =>
    (await request<{ estimate: Estimate | null }>(`/api/estimate?chars=${chars}`)).estimate,
  extract: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ filename: string; text: string; chars: number }>("/api/extract", { method: "POST", body: fd });
  },
  submit: (text: string, title?: string, slug?: string) =>
    request<SubmitResult>("/api/stories", post({ text, title, ...(slug ? { slug } : {}) })),
  /** resumeOnly:只接續停住的那次分析,沒有可續的就 409 nothing-to-resume(不開新的一次)。 */
  startJob: (slug: string, opts: { resumeOnly?: boolean } = {}) =>
    request<{ job_id: number }>("/api/jobs", post({ kind: "critique", slug, ...(opts.resumeOnly ? { resume_only: true } : {}) })),
  jobEvents: (jobId: number) => stream(`/api/jobs/${jobId}/events`),
  job: (id: number) => request<{ id: number; state: string; step: string | null; created_at: number }>(`/api/jobs/${id}`),
  cancelJob: (id: number) => request<unknown>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  setReaction: (session: string, seq: number, mark: ReactionMark, comment?: string) =>
    request<TurnReaction>(reactionUrl(session, seq), {
      ...post({ mark, comment }), method: "PUT",
    }),
  clearReaction: (session: string, seq: number) =>
    request<void>(reactionUrl(session, seq), { method: "DELETE" }),
  regenerate: (session: string, seq: number, signal?: AbortSignal) =>
    stream(turnUrl(session, seq, "regenerate"), { method: "POST", signal }),
  pickVariant: (session: string, seq: number, n: number) =>
    request<{ variant: number; variants: number }>(turnUrl(session, seq, "variant"), { ...post({ n }), method: "PUT" }),
  editReply: (session: string, seq: number, text: string) =>
    request<{ edited: boolean }>(turnUrl(session, seq, "text"), { ...post({ text }), method: "PUT" }),
  setVoice: (session: string, seq: number) => request<void>(turnUrl(session, seq, "voice"), { method: "PUT" }),
  clearVoice: (session: string, seq: number) => request<void>(turnUrl(session, seq, "voice"), { method: "DELETE" }),
  clearSession: (session: string) => request<{ seq: number }>(`${sessionUrl(session)}/clear`, { method: "POST" }),
  compactSession: (session: string) => request<{ seq: number; text: string }>(`${sessionUrl(session)}/compact`, { method: "POST" }),
  archiveSession: (session: string) => request<void>(`${sessionUrl(session)}/archive`, { method: "POST" }),
  unarchiveSession: (session: string) => request<void>(`${sessionUrl(session)}/unarchive`, { method: "POST" }),
  deleteSession: (session: string) => request<void>(sessionUrl(session), { method: "DELETE" }),
  archivedSessions: () => request<{ sessions: ArchivedSession[] }>("/api/archived-sessions").then(r => r.sessions),
  adoptAttachment: (session: string, n: number) =>
    request<Adopted>(`${sessionUrl(session)}/attachments/${n}/adopt`, { method: "POST" }),
  memories: () => request<MemoryList>("/api/memory"),
  remember: (body: RememberBody) => request<Memory>("/api/memory", post(body)),
  editMemory: (id: number, text: string) => request<Memory>(`/api/memory/${id}`, { ...post({ text }), method: "PATCH" }),
  archiveMemory: (id: number) => request<void>(`/api/memory/${id}/archive`, { method: "POST" }),
  revertMemory: (id: number) => request<Memory>(`/api/memory/${id}/revert`, { method: "POST" }),
  /** session 為 null = 開新局(局 id 在 done 事件裡回);slug 為 null = 不帶作品的局。 */
  talk: (slug: string | null, body: { session: string | null; message: string; character: string; quotes: string[]; attach?: AttachIn },
    signal?: AbortSignal) =>
    stream(slug === null ? "/api/discuss" : `/api/discuss/${encodeURIComponent(slug)}`, {
      ...post({
        session_id: body.session, message: body.message, character: body.character, quotes: body.quotes,
        ...(body.attach ? { attach: body.attach } : {}),
      }), signal,
    }),
};
