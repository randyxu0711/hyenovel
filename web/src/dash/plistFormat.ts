export type Plist = { traits: string[]; label: string; speech: string[] };

const SHAPE = /^\[\s*[^:：;；[\]]+[:：]\s*([^;；[\]]*?)\s*[;；]\s*([^:：;；[\]]+?)\s*[:：]\s*([^;；[\]]*?)\s*\]$/;
const SPLIT = /[,，、]/;
const BANNED = /[[\]:：;；,，、{}]/g;

const words = (s: string) => s.split(SPLIT).map(w => w.trim()).filter(Boolean);

export function parsePlist(prompt: string): Plist | null {
  const m = SHAPE.exec(prompt.trim());
  return m ? { traits: words(m[1]), label: m[2], speech: words(m[3]) } : null;
}

export const cleanWord = (w: string) => w.replace(BANNED, "").trim();

export const speechLabel = (lang: string) => (lang === "en" ? "Speech" : "說話");

export function composePlist({ traits, label, speech }: Plist): string {
  if (traits.length === 0 && speech.length === 0) return "";
  return `[{{char}}: ${traits.join(", ")}; ${label}: ${speech.join(", ")}]`;
}
