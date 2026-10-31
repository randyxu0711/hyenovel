import { useSyncExternalStore } from "react";
import { DEN_ERROR_CODES, type LText } from "./api";

export type Lang = "zh-Hant" | "en";

export const zhHant = {
  "brand": "hyenovel",
  "rail.works": "作品",
  "rail.feed": "捲進一張新稿",
  "desk.empty": "選一篇作品,或捲進一張新稿。",
  "talk.empty": "陪讀者在這裡。",
  "talk.pick": "選誰陪你讀",
  "talk.who": "陪讀者",
  "talk.start": "跟{name}說說你想聊什麼。",
  "talk.waiting": "{name}在讀……",
  "talk.switched": "換{name}來讀",
  "talk.send": "送出",
  "talk.input": "對話輸入",
  "talk.placeholder": "跟{name}說……",
  "talk.collapse": "收起對話",
  "talk.expand": "{name}在這裡,點開來聊",
  "talk.dropQuote": "拿掉這段引文",
  "rail.sessions": "對話",
  "rail.all": "全部",
  "rail.reading": "正在讀",
  "rail.version": "第 {n} 版",
  "rail.chars": "{n} 字",
  "rail.noSessions": "還沒聊過。",
  "rail.firstDraft": "還沒有作品。捲進第一張稿吧。",
  "reader.bring": "帶給{name}聊",
  "reader.tooLong": "選短一點(400 字內)",
  "feed.title": "捲進一張新稿",
  "feed.text": "稿子",
  "feed.paste": "把稿子貼在這裡,或把 .md / .txt 檔拖進來。",
  "feed.pick": "選檔",
  "feed.chars": "{n} 字",
  "feed.estimate": "預估約 {min} 分鐘",
  "feed.noEstimate": "第一次分析,還沒有預估。",
  "feed.go": "交稿並開始分析(會用你的訂閱額度)",
  "feed.sending": "送出中……",
  "feed.cancel": "取消",
  "feed.already": "這篇已經在了,已切過去。",
  "job.reading": "正在讀這一篇",
  "job.step.analyst": "整篇讀一遍",
  "job.step.reviewer": "寫備課筆記",
  "notes.open": "冷讀者的筆記",
  "notes.close": "收起筆記",
  "notes.running": "筆記還在寫",
  "notes.none": "還沒有筆記",
  "notes.lead": "這是另一位冷讀者的筆記",
  "nav.paper": "稿",
  "keys.theme": "佈景",
  "keys.mode": "明暗",
  "keys.lang": "語言",
  "mode.system": "跟系統",
  "mode.light": "晝",
  "mode.dark": "夜",
  "loading": "載入中……",
  "err.unknown": "出了點狀況,請再試一次。",
  "err.den-down": "連不上本機的 den,請確認它有在跑。",
  "err.bad-slug": "作品代號不合法。",
  "err.unknown-work": "找不到這篇作品。",
  "err.bad-part": "沒有這一部分。",
  "err.not-analyzed": "這篇還沒分析完。",
  "err.no-notes": "這篇還沒有備課筆記。",
  "err.no-feedback": "這篇沒有舊回饋。",
  "err.nothing-running": "目前沒有在跑的分析。",
  "err.unknown-session": "找不到這一局。",
  "err.busy": "這一局還有一輪在進行,稍等一下。",
  "err.quote-not-in-source": "引用的句子不在原文裡。",
  "err.quote-too-long": "引用的句子太長。",
  "err.empty-story": "稿子是空的。",
  "err.story-too-long": "稿子太長了。",
  "err.unknown-slug-ref": "指定的作品不存在。",
  "err.file-too-large": "檔案太大。",
  "err.extract-failed": "讀不出這個檔案的文字。",
  "err.no-runner": "找不到可用的 Claude 執行環境。",
  "err.nothing-to-resume": "沒有可以續跑的分析。",
  "err.bad-host": "不被接受的來源主機。",
  "err.bad-origin": "不被接受的請求來源。",
  "err.bad-token": "沒有權限,請重新從 hyenovel 開啟。",
  "err.bad-launch-code": "開啟連結已失效,請重新開啟。",
  "err.unknown-character": "沒有這位陪讀者。",
  "err.unknown-session-id": "找不到這一局。",
  "err.ambiguous-session": "有兩篇作品用了同一個局代號,無法判斷是哪一局。",
} as const;

export type MsgKey = keyof typeof zhHant;

export const en: Record<MsgKey, string> = {
  "brand": "hyenovel",
  "rail.works": "Works",
  "rail.feed": "Feed in a new draft",
  "desk.empty": "Pick a work, or feed in a new draft.",
  "talk.empty": "Your reading companion is here.",
  "talk.pick": "Who reads with you?",
  "talk.who": "Companion",
  "talk.start": "Tell {name} what you'd like to talk about.",
  "talk.waiting": "{name} is reading...",
  "talk.switched": "{name} takes over",
  "talk.send": "Send",
  "talk.input": "Message",
  "talk.placeholder": "Say something to {name}...",
  "talk.collapse": "Collapse conversation",
  "talk.expand": "{name} is here. Open to talk",
  "talk.dropQuote": "Remove this quote",
  "rail.sessions": "Conversations",
  "rail.all": "All",
  "rail.reading": "Reading",
  "rail.version": "Version {n}",
  "rail.chars": "{n} chars",
  "rail.noSessions": "No conversations yet.",
  "rail.firstDraft": "No works yet. Feed in your first draft.",
  "reader.bring": "Bring to {name}",
  "reader.tooLong": "Select less (within 400 characters)",
  "feed.title": "Feed in a new draft",
  "feed.text": "Draft",
  "feed.paste": "Paste the draft here, or drop a .md / .txt file.",
  "feed.pick": "Choose file",
  "feed.chars": "{n} chars",
  "feed.estimate": "About {min} min",
  "feed.noEstimate": "First analysis, no estimate yet.",
  "feed.go": "Submit and analyze (uses your subscription quota)",
  "feed.sending": "Sending...",
  "feed.cancel": "Cancel",
  "feed.already": "This draft is already here. Switched to it.",
  "job.reading": "Reading this one",
  "job.step.analyst": "Reading it through",
  "job.step.reviewer": "Writing prep notes",
  "notes.open": "Cold reader's notes",
  "notes.close": "Close notes",
  "notes.running": "Notes are still being written",
  "notes.none": "No notes yet",
  "notes.lead": "These are another cold reader's notes",
  "nav.paper": "Paper",
  "keys.theme": "Theme",
  "keys.mode": "Light or dark",
  "keys.lang": "Language",
  "mode.system": "System",
  "mode.light": "Light",
  "mode.dark": "Dark",
  "loading": "Loading...",
  "err.unknown": "Something went wrong. Please try again.",
  "err.den-down": "Can't reach the local den. Check that it is running.",
  "err.bad-slug": "That work id is not valid.",
  "err.unknown-work": "That work was not found.",
  "err.bad-part": "There is no such part.",
  "err.not-analyzed": "This work has not finished its analysis.",
  "err.no-notes": "This work has no prep notes yet.",
  "err.no-feedback": "This work has no old feedback.",
  "err.nothing-running": "No analysis is running.",
  "err.unknown-session": "That session was not found.",
  "err.busy": "This session still has a turn in progress. Wait a moment.",
  "err.quote-not-in-source": "The quoted line is not in the text.",
  "err.quote-too-long": "The quoted line is too long.",
  "err.empty-story": "The draft is empty.",
  "err.story-too-long": "The draft is too long.",
  "err.unknown-slug-ref": "The referenced work does not exist.",
  "err.file-too-large": "The file is too large.",
  "err.extract-failed": "Could not read text from that file.",
  "err.no-runner": "No usable Claude runtime was found.",
  "err.nothing-to-resume": "There is no analysis to resume.",
  "err.bad-host": "Host not accepted.",
  "err.bad-origin": "Request origin not accepted.",
  "err.bad-token": "Not authorized. Please reopen from hyenovel.",
  "err.bad-launch-code": "The launch link has expired. Please open it again.",
  "err.unknown-character": "No such companion.",
  "err.unknown-session-id": "That session was not found.",
  "err.ambiguous-session": "Two works share this session id, so it can't be told which one you mean.",
};

const dicts: Record<Lang, Record<MsgKey, string>> = { "zh-Hant": zhHant, en };

/** den 的錯誤代碼 → 訊息鍵;不認得的代碼 → err.unknown。 */
export function errorMessage(code: string): MsgKey {
  const key = `err.${code}` as MsgKey;
  return DEN_ERROR_CODES.includes(code) && key in zhHant ? key : "err.unknown";
}

export function localized(text: LText, lang: Lang): string {
  return text[lang] ?? text[lang === "en" ? "zh-Hant" : "en"] ?? "";
}

// ── 語言狀態:localStorage → navigator.language ──
const LANG_KEY = "hyenovel.lang";
const listeners = new Set<() => void>();

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    if (saved === "zh-Hant" || saved === "en") return saved;
  } catch { /* 讀不到就跟瀏覽器 */ }
  return navigator.language.toLowerCase().startsWith("zh") ? "zh-Hant" : "en";
}

let current: Lang = initialLang();

export const getLang = () => current;

export function setLang(lang: Lang): void {
  current = lang;
  try { localStorage.setItem(LANG_KEY, lang); } catch { /* 存不了也照用 */ }
  listeners.forEach(l => l());
}

const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l); }; };

export const useLang = (): Lang => useSyncExternalStore(subscribe, getLang);

export function translate(lang: Lang, key: MsgKey, params?: Record<string, string | number>): string {
  const s = dicts[lang][key];
  return params ? s.replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k]) : m)) : s;
}

export function useT(): (key: MsgKey, params?: Record<string, string | number>) => string {
  const lang = useLang();
  return (key, params) => translate(lang, key, params);
}

/** 測試用:重讀 localStorage / navigator。 */
export function resetLang(): void { current = initialLang(); }
