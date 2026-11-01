import type { Character, Theme } from "../src/dash/api";

const tok = (desk: string, paper: string, accent: string, ink: string): Record<string, string> => ({
  desk, "desk-2": desk, paper, "paper-ink": ink, "paper-ink-2": ink, ink, "ink-2": ink,
  line: "rgb(0 0 0 / .14)", accent, "accent-ink": paper, spot: "rgba(70,60,30,.075)", sheen: "rgba(255,255,255,.35)",
});
export const olive: Theme = {
  id: "olive", name: { "zh-Hant": "暖橄欖", en: "Warm olive" }, source: "和田三造《配色事典》#310",
  light: tok("#f0e9cf", "#fdf9ea", "#6c6827", "#232a1f"),
  dark: tok("#1c1e14", "#dcd2b8", "#5c5823", "#e5e1cf"),
};
export const grass: Theme = {
  id: "grass", name: { "zh-Hant": "草原灰夜", en: "Grassland dusk" }, source: "#192",
  light: tok("#efe6d3", "#fdf8ec", "#5f616b", "#2b2721"),
  dark: tok("#1f1f25", "#dad0ba", "#4e5059", "#e4ded0"),
};

const ch = (id: string, mode: string, zh: string, en: string, kind = id): Character => ({
  id, mode, name: { "zh-Hant": zh, en }, line: { "zh-Hant": "一句話", en: "A line" },
  avatar: { kind, seed: id },
  colors: { light: { fill: "#cc8650", text: "#925a2b" }, dark: { fill: "#dc9a66", text: "#dc9a66" } }, voice: "",
  mark: (({ hyena: "pencil", buffalo: "highlighter", deer: "circle" }) as Record<string, Character["mark"]>)[id] ?? "pencil",
});
export const hyena = ch("hyena", "slow", "鬣狗", "Hyena");
export const buffalo = ch("buffalo", "direct", "水牛", "Water buffalo");
export const deer = ch("deer", "imaginative", "鹿", "Deer");
export { ch };
