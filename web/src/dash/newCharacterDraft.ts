import type { Candidate } from "./api";

export type Answers = { form: string; wish: string };
export type Draft = {
  form: string; wish: string; batch: Candidate[] | null; batchNo: number; scene: number; reaction: string;
  picked?: number | null; revealed?: number; asked?: Answers;
};
export type Job = { kind: "generate" | "revise"; index: number | null; text?: string; started: number; done: Promise<void> };

export const DRAFT_KEY = "hyenovel.newCharacter.v2";
const EMPTY: Draft = { form: "", wish: "", batch: null, batchNo: 0, scene: 0, reaction: "" };

let memory: Draft | null | undefined;
let job: Job | null = null;
let missed: unknown = null;
let watching = 0;

const str = (v: unknown) => typeof v === "string";
const num = (v: unknown) => typeof v === "number" && Number.isFinite(v);
const answers = (v: unknown) => !!v && typeof v === "object" && str((v as Answers).form) && str((v as Answers).wish);
function valid(d: unknown): d is Draft {
  if (!d || typeof d !== "object") return false;
  const x = d as Record<string, unknown>;
  return str(x.form) && str(x.wish) && str(x.reaction) && num(x.batchNo) && num(x.scene)
    && (x.batch === null || Array.isArray(x.batch))
    && (x.picked === undefined || x.picked === null || num(x.picked)) && (x.revealed === undefined || num(x.revealed))
    && (x.asked === undefined || answers(x.asked));
}

export function draft(): Draft | null {
  if (memory !== undefined) return memory;
  try {
    const d: unknown = JSON.parse(sessionStorage.getItem(DRAFT_KEY) ?? "null");
    memory = valid(d) ? d : null;
  } catch {
    memory = null;
  }
  return memory;
}

export function keep(d: Draft): void {
  memory = d;
  try { sessionStorage.setItem(DRAFT_KEY, JSON.stringify(d)); } catch { /* 存不了就只留在這次開著的頁面 */ }
}

export function drop(): void {
  memory = undefined;
  missed = null;
  try { sessionStorage.removeItem(DRAFT_KEY); } catch { /* 同上 */ }
}

export const running = (): Job | null => job;

export function start(kind: Job["kind"], index: number | null, work: () => Promise<(d: Draft) => Draft>, text?: string): Job {
  const done = work().then(update => { keep(update(draft() ?? EMPTY)); });
  const j: Job = { kind, index, text, started: Date.now(), done: done.finally(() => { if (job === j) job = null; }) };
  j.done.catch(e => { if (watching === 0) missed = e; });
  job = j;
  return j;
}

export function watch(): () => void {
  watching += 1;
  return () => { watching -= 1; };
}

export function takeMissed(): unknown {
  const e = missed;
  missed = null;
  return e;
}
