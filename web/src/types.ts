export type NodeType = "theme" | "motif" | "technique" | "effect" | "character" | "beat";
export type EdgeType =
  | "produces" | "serves" | "manifests" | "recurs_in"
  | "tensions_with" | "characterizes" | "precedes" | "relates_to";

export interface Evidence {
  quote: string;
  /** char offset of quote start in source.md */
  start: number;
  /** char offset of quote end in source.md */
  end: number;
  /** normalized text position [0..1] within source.md; null if not locatable */
  pos: number | null;
}
export interface VizNode {
  id: string; type: NodeType; label: string; note: string;
  intensity: number | null; evidence: Evidence[];
}
export interface VizEdge { type: EdgeType; from: string; to: string; note?: string; }

export interface FeedbackPoint {
  title: string; body: string; experiment?: string | null; question?: string | null;
  /** analysis node IDs this feedback anchors to */
  refs: string[];
  quotes: { quote: string; start: number; end: number }[];
}
export interface Feedback {
  read: string; strengths: FeedbackPoint[]; key_points: FeedbackPoint[];
  minor: string[]; one_line: string;
}
export interface VizData {
  slug: string; title: string;
  nodes: VizNode[]; edges: VizEdge[];
  colors: Record<string, string>; cn: Record<string, string>;
  diag: Record<string, string[]>;     // nodeId -> ["orphan"|"overloaded"|"hollow"]
  feedback: Feedback | null;
}

export interface IndexEntry {
  slug: string; title: string; synopsis: string;
  nodes: number; edges: number; has_feedback: boolean; has_viz: boolean; updated: string;
  // status 來自 run.json,值域不封閉(可能是 "cancelled" 等未列舉值)——不可窮舉 switch,
  // 前端一律靠 resumable(乾淨 boolean)判斷「該不該畫續跑星」,不做 status 字串比對。
  status: string; stage: string; resumable: boolean;
  // failed 的原因(timeout/gate/crash);paused/done 為 null。前端翻成友善字顯示在紅星上。
  reason: string | null;
}
export interface IndexFile { generated: string; count: number; stories: IndexEntry[]; }

// 孕育中星星的即時狀態(來自 SSE / /running;step 1→4)
// vizReady:後端早出 viz 已落檔(analyst 交件)→ 孕育中就能改畫真骨,不再是象徵骨。
// 與 step 分開:step 是「跑到哪格」,vizReady 是「資料在不在」——preview 不動 step。
// status:running=活訂閱中;paused/failed=串流已斷但胚胎保留(可續跑/重新分析)。
// reason/resetsAt 只在 paused/failed 時有意義,來自後端 error 事件(reason 值域見 server SSE 契約)。
export type GestationStatus = "running" | "paused" | "failed";
export type Gestation = {
  step: number; status: GestationStatus; title: string; vizReady?: boolean;
  reason?: string; resetsAt?: number | null;
};

export type UsagePhase = {
  input: number; output: number; cache_creation: number; cache_read: number;
  cost_usd: number; turns: number;
};
export type UsageTotal = {
  input: number; output: number; cache_creation: number; cache_read: number; cost_usd: number;
};
export type UsageAggregate = {
  slug: string;
  empty: boolean;
  phases: Record<string, UsagePhase>;   // key ∈ analyst | criticizer | discuss
  total: UsageTotal;
  cache_read_ratio: number;
  retry_cost_usd: number;
  retry_count: number;
  duration_ms: number;
  runs: number;                          // 這篇被 critique 過幾次(年輪)
  last_run_cost_usd: number;             // 最後一次 critique 的花費(每節點單價的分子)
};

// 跨篇總量(用量星圖):中心=total、四角=phases/retry/duration/cache、每顆星=stories[]
export type UsageStory = {
  slug: string; cost_usd: number; tokens: number;
  runs: number; retry_count: number; last_run_cost_usd: number;
};
export type UsageAll = {
  empty: boolean;
  total: UsageTotal;
  phases: Record<string, UsagePhase>;
  retry_cost_usd: number;
  retry_count: number;
  duration_ms: number;
  cache_read_ratio: number;
  stories: UsageStory[];
};
