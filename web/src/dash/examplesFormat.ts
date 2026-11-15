export type ExampleTurn = { who: "author" | "char"; text: string };
export type Examples = { lead: string; scenes: ExampleTurn[][] };

const BLOCK = /<example>([\s\S]*?)<\/example>/g;
const SPEAKER = /^([^:：\n]{1,24})[:：]\s?(.*)$/;
const AUTHORS = new Set(["作者", "{{user}}"]);

function scene(body: string): ExampleTurn[] {
  const turns: ExampleTurn[] = [];
  for (const raw of body.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const m = SPEAKER.exec(line);
    if (m) turns.push({ who: AUTHORS.has(m[1].trim()) ? "author" : "char", text: m[2] });
    else if (turns.length) turns[turns.length - 1].text += "\n" + line;
    else turns.push({ who: "char", text: line });
  }
  return turns;
}

export function parseExamples(text: string): Examples | null {
  const scenes = [...text.matchAll(BLOCK)].map(m => scene(m[1])).filter(s => s.length > 0);
  if (!scenes.length) return null;
  const lead = text.slice(0, text.indexOf("<example>")).trim();
  return { lead, scenes };
}
