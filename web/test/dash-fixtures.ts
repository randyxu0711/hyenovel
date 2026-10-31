import type { Character, Theme } from "../src/dash/api";

export const olive: Theme = {
  id: "olive", name: { "zh-Hant": "暖橄欖", en: "Warm olive" }, source: "和田三造《配色事典》#310",
  light: { enamel: "#6c6827", "enamel-ink": "#fbf7e6", desk: "#f0e9cf", panel: "#f6f0dc", bubble: "#fdf9ea", paper: "#fdf9ea",
    "paper-ink": "#232a1f", "paper-ink-2": "#5f6352", "ui-ink": "#262b20", "ui-ink-2": "#64685a",
    line: "rgb(35 42 31 / .14)", platen: "#2a2b1a", knob: "#cfc28e", muzzle: "#f6eccd" },
  dark: { enamel: "#5c5823", "enamel-ink": "#ece7cf", desk: "#1c1e14", panel: "#25271c", bubble: "#303325", paper: "#dcd2b8",
    "paper-ink": "#232a1f", "paper-ink-2": "#575b4a", "ui-ink": "#e5e1cf", "ui-ink-2": "#a9a690",
    line: "rgb(229 225 207 / .12)", platen: "#111209", knob: "#a99f72", muzzle: "#e6dcbd" },
};
export const grass: Theme = {
  id: "grass", name: { "zh-Hant": "草原灰夜", en: "Grassland dusk" }, source: "#192",
  light: { enamel: "#5f616b", "enamel-ink": "#f4f1ea", desk: "#efe6d3", panel: "#f5eee0", bubble: "#fdf8ec", paper: "#fdf8ec",
    "paper-ink": "#2a241c", "paper-ink-2": "#6a5f52", "ui-ink": "#2b2721", "ui-ink-2": "#6b6458",
    line: "rgb(42 36 28 / .14)", platen: "#2d2e35", knob: "#c9b48a", muzzle: "#f6ead0" },
  dark: { enamel: "#4e5059", "enamel-ink": "#e6e2d8", desk: "#1f1f25", panel: "#27272e", bubble: "#33333b", paper: "#dad0ba",
    "paper-ink": "#2a241c", "paper-ink-2": "#5e5446", "ui-ink": "#e4ded0", "ui-ink-2": "#a9a397",
    line: "rgb(228 222 208 / .12)", platen: "#121216", knob: "#a8966f", muzzle: "#e7dcc2" },
};

const ch = (id: string, mode: string, zh: string, en: string, kind = id): Character => ({
  id, mode, name: { "zh-Hant": zh, en }, line: { "zh-Hant": "一句話", en: "A line" },
  avatar: { kind, seed: id },
  colors: { light: { fill: "#cc8650", text: "#925a2b" }, dark: { fill: "#dc9a66", text: "#dc9a66" } }, voice: "",
});
export const hyena = ch("hyena", "slow", "鬣狗", "Hyena");
export const buffalo = ch("buffalo", "direct", "水牛", "Water buffalo");
export const deer = ch("deer", "imaginative", "鹿", "Deer");
export { ch };
