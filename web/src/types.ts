export type NodeType = "theme" | "motif" | "technique" | "effect" | "character" | "beat";
export type EdgeType =
  | "produces" | "serves" | "manifests" | "recurs_in"
  | "tensions_with" | "characterizes" | "precedes" | "relates_to";

export interface Evidence { quote: string; start: number; end: number; pos: number | null; }
export interface VizNode {
  id: string; type: NodeType; label: string; note: string;
  intensity: number | null; evidence: Evidence[];
}
export interface VizEdge { type: EdgeType; from: string; to: string; note?: string; }

export interface FeedbackPoint {
  title: string; body: string; experiment?: string | null; question?: string | null;
  refs: string[]; quotes: { quote: string; start: number; end: number }[];
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
}
export interface IndexFile { generated: string; count: number; stories: IndexEntry[]; }
