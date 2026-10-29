import index from "./fixtures/index.json";

/** 把舊 index fixture 轉成 den `GET /stories` 的領域形狀(畫面測試的 fetch mock 用)。 */
export const denIndex = {
  stories: (index as any).stories.map((s: any) => ({
    slug: s.slug, title: s.title, synopsis: s.synopsis, nodes: s.nodes, edges: s.edges,
    current: {
      analysis: s.has_viz ? { id: 1, created_at: 1_700_000_000 } : null,
      feedback: s.has_feedback ? { id: 2, created_at: 1_700_000_000 } : null,
    },
    latest_job: null,
  })),
};
