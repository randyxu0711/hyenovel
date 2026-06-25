import type { IndexFile, VizData } from "../types";

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`讀不到 ${url}(${res.status})`);
  return (await res.json()) as T;
}
async function getText(url: string): Promise<string> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`讀不到 ${url}(${res.status})`);
  return res.text();
}

export const getIndex = () => getJSON<IndexFile>("/data/index.json");
export const getViz = (slug: string) => getJSON<VizData>(`/data/${slug}/viz.json`);
export const getSource = (slug: string) => getText(`/data/${slug}/source.md`);
export async function getStory(slug: string): Promise<{ viz: VizData; source: string }> {
  const [viz, source] = await Promise.all([
    getViz(slug),
    getSource(slug),
  ]);
  return { viz, source };
}
