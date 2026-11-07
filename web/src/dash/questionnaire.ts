import type { LText } from "./api";

const l = (zh: string, en: string): LText => ({ "zh-Hant": zh, en });

export const WORDS: LText[][] = [
  [l("校對員", "proofreader"), l("代書", "scrivener"), l("夜班警衛", "night guard")],
  [l("夜鷺", "night heron"), l("寄居蟹", "hermit crab"), l("老狗", "old dog")],
  [l("舊收音機", "old radio"), l("捲尺", "tape measure"), l("門縫", "door crack")],
  [l("退潮", "ebb tide"), l("回音", "echo"), l("霧", "fog")],
  [l("末班車", "last bus"), l("騎樓", "arcade"), l("空教室", "empty classroom")],
  [l("失眠", "insomnia"), l("剛睡醒", "just awake"), l("等人", "waiting for someone")],
];
