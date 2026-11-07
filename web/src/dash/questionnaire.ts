import type { LText } from "./api";

export const PASSAGE = "阿嬤走後第三天,灶腳的電鍋還插著電。我媽講要拔,講了兩次,人攏無行過去。保溫燈暗暗紅紅的,內鍋裡什麼都沒有。那天晚上我起來喝水,看見她坐在矮凳上,手放在鍋蓋上,像在試溫度。";

const l = (zh: string, en: string): LText => ({ "zh-Hant": zh, en });

export const WORDS: LText[][] = [
  [l("校對員", "proofreader"), l("代書", "scrivener"), l("夜班警衛", "night guard")],
  [l("夜鷺", "night heron"), l("寄居蟹", "hermit crab"), l("老狗", "old dog")],
  [l("舊收音機", "old radio"), l("捲尺", "tape measure"), l("門縫", "door crack")],
  [l("退潮", "ebb tide"), l("回音", "echo"), l("霧", "fog")],
  [l("末班車", "last bus"), l("騎樓", "arcade"), l("空教室", "empty classroom")],
  [l("失眠", "insomnia"), l("剛睡醒", "just awake"), l("等人", "waiting for someone")],
];

export type QuestionId = "attention" | "returns" | "response";
export type Question = { id: QuestionId; sets: { stem: LText; options: LText[] }[] };

const attention = l("下面都是讀完這段的反應。你最想接哪一則?", "These are all reactions to this passage. Which one do you most want to pick up?");
const returns = l("讀完一篇,它先交回什麼?", "After reading a piece, what does it hand back first?");

export const QUESTIONS: Question[] = [
  {
    id: "attention",
    sets: [
      {
        stem: attention,
        options: [
          l("我停在「人攏無行過去」:這句的聲音和前面不一樣。", "I stopped at 「人攏無行過去」: this line sounds different from the ones before it."),
          l("我停在「暗暗紅紅」:後面一直留著那盞燈。", "I stopped at 「暗暗紅紅」: that lamp stays on through what follows."),
          l("我停在「手放在鍋蓋上」:開頭的電鍋在這裡接上了。", "I stopped at 「手放在鍋蓋上」: the rice cooker from the opening connects here."),
          l("我停在「講了兩次」:不知道她當時在想什麼。", "I stopped at 「講了兩次」: I wonder what she was thinking then."),
          l("我停在「那天晚上」:想知道接下來會怎樣。", "I stopped at 「那天晚上」: I want to know what happens next."),
        ],
      },
      {
        stem: attention,
        options: [
          l("我停在「灶腳」:這個詞一出來,整段的口音就定了。", "I stopped at 「灶腳」: once this word appears, the whole passage has its accent."),
          l("我停在「內鍋裡什麼都沒有」:那個空的鍋一直留著。", "I stopped at 「內鍋裡什麼都沒有」: that empty pot stays with me."),
          l("我停在「第三天」:時間從這裡開始算,後面都掛在上面。", "I stopped at 「第三天」: time starts counting here, and the rest hangs on it."),
          l("我停在「坐在矮凳上」:她坐在那裡,心裡有什麼。", "I stopped at 「坐在矮凳上」: what's on her mind, sitting there."),
          l("我停在「我起來喝水」:想知道「我」接著有沒有開口。", "I stopped at 「我起來喝水」: I want to know if the narrator says anything next."),
        ],
      },
    ],
  },
  {
    id: "returns",
    sets: [
      {
        stem: returns,
        options: [
          l("原文裡的一句", "A line from the text"),
          l("這篇的形狀", "The shape of the piece"),
          l("一個它答不出來的問題", "A question it can't answer"),
          l("這篇讓它想到的別的東西", "Something else the piece brings to mind"),
        ],
      },
      {
        stem: returns,
        options: [
          l("它停最久的地方", "Where it stopped longest"),
          l("它沒讀懂的地方", "What it didn't understand"),
          l("這篇從頭到尾變了什麼", "What changed from start to end"),
          l("這篇的聲音", "The sound of the piece"),
        ],
      },
    ],
  },
  {
    id: "response",
    sets: [
      {
        stem: l("同樣讀到「像在試溫度」,你最想接哪一句?", "Reading the same 「像在試溫度」, which reply do you most want to pick up?"),
        options: [
          l("讀到「試」我停住了,沒有往下。", "At 「試」 I stopped and didn't read on."),
          l("「試」的是什麼,這段有給嗎?", "What's being tested at 「試」? Does the passage say?"),
          l("「試」和前面的「拔」,方向相反。", "「試」 and the earlier 「拔」 pull in opposite directions."),
          l("「試」也許不是想知道溫度。", "Maybe 「試」 isn't about wanting to know the temperature."),
        ],
      },
      {
        stem: l("同樣讀到「內鍋裡什麼都沒有」,你最想接哪一句?", "Reading the same 「內鍋裡什麼都沒有」, which reply do you most want to pick up?"),
        options: [
          l("讀到「什麼都沒有」我停住了,沒有往下。", "At 「什麼都沒有」 I stopped and didn't read on."),
          l("「什麼都沒有」,那燈在保什麼溫?", "If there's 「什麼都沒有」, what is the lamp keeping warm?"),
          l("「什麼都沒有」和「還插著電」,方向相反。", "「什麼都沒有」 and 「還插著電」 pull in opposite directions."),
          l("「什麼都沒有」也許不只在講鍋。", "Maybe 「什麼都沒有」 isn't only about the pot."),
        ],
      },
    ],
  },
];

export function quotesIn(text: string): string[] {
  return [...text.matchAll(/「([^「」]+)」/g)].map(m => m[1]);
}

export function marked(passage: string, quotes: string[]): { text: string; on: boolean }[] {
  const hits = quotes
    .map(q => [passage.indexOf(q), q.length])
    .filter(([at]) => at >= 0)
    .map(([at, n]) => [at, at + n])
    .sort((a, b) => a[0] - b[0]);
  const parts: { text: string; on: boolean }[] = [];
  let i = 0;
  for (const [a, b] of hits) {
    if (b <= i) continue;
    const from = Math.max(a, i);
    if (from > i) parts.push({ text: passage.slice(i, from), on: false });
    const last = parts[parts.length - 1];
    if (last?.on) last.text += passage.slice(from, b);
    else parts.push({ text: passage.slice(from, b), on: true });
    i = b;
  }
  if (i < passage.length) parts.push({ text: passage.slice(i), on: false });
  return parts;
}
