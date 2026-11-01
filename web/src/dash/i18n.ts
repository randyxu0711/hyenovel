import { useSyncExternalStore } from "react";
import { DEN_ERROR_CODES, type LText } from "./api";

export type Lang = "zh-Hant" | "en";

export const zhHant = {
  "brand": "hyenovel",
  "rail.works": "作品",
  "rail.settings": "設定",
  "rail.dayNight": "切換晝夜",
  "rail.new": "新對話",
  "rail.fresh": "有新東西",
  "rail.busy": "分析中",
  "menu.submitNew": "交一篇新的",
  "home.waiting": "《{title}》讀完了。",
  "home.listen": "聽聽看 ›",
  "home.placeholder": "想聊什麼?也可以把稿拖進來",
  "home.placeholderEmpty": "把稿拖進來,或貼上",
  "home.which": "聊哪一篇",
  "home.meet": "陪讀者",
  "talk.empty": "陪讀者在這裡。",
  "talk.who": "陪讀者",
  "talk.start": "跟{name}說說你想聊什麼。",
  "talk.waiting": "{name}在讀……",
  "talk.switched": "換{name}來讀",
  "talk.send": "送出",
  "talk.input": "對話輸入",
  "talk.placeholder": "跟{name}說……",
  "talk.dropQuote": "拿掉這段引文",
  "reader.bring": "帶進對話",
  "reader.tooLong": "選短一點(400 字內)",
  "paper.versions": "版本",
  "paper.oldVersion": "這是第 {n} 版",
  "paper.latest": "回到最新版",
  "paper.resume": "續跑",
  "state.running": "分析中",
  "state.notesRunning": "分析好了,筆記還在寫",
  "state.notesStopped": "筆記停住了",
  "state.allReady": "分析和筆記都好了",
  "state.ready": "分析好了",
  "state.stopped": "分析停住了",
  "state.stale": "新版還沒分析",
  "state.none": "還沒分析",
  "feed.text": "稿子",
  "feed.chars": "{n} 字",
  "feed.estimate": "預估約 {min} 分鐘",
  "feed.noEstimate": "第一次分析,還沒有預估。",
  "feed.go": "交稿並開始分析(會用你的訂閱額度)",
  "feed.sending": "送出中……",
  "feed.cancel": "取消",
  "feed.already": "這篇已經在了,已切過去。",
  "notice.dismiss": "關閉提示",
  "job.step.analyst": "整篇讀一遍",
  "job.step.reviewer": "寫備課筆記",
  "notes.open": "冷讀者的筆記",
  "notes.close": "收起筆記",
  "notes.running": "筆記還在寫",
  "notes.none": "還沒有筆記",
  "notes.lead": "這是另一位冷讀者的筆記",
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
  "err.quote-needs-message": "帶著引文時,也寫一句你想問的。",
  "err.too-many-quotes": "一次最多帶 4 段。",
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
  "err.unknown-version": "找不到這個版本。",
  "err.legacy-session": "這是改版前的舊討論,只能看,不能接著聊。",
  "err.ambiguous-session": "有兩篇作品用了同一個局代號,無法判斷是哪一局。",
  "err.usage-limit": "訂閱用量到上限了,現在重試也沒用;等額度回來再聊。",
  "err.no-response": "陪讀者沒有回應,這輪沒有存下。可以再送一次。",
  "err.commit-failed": "存檔失敗,這輪沒有存下。可以再送一次。",
  "err.chat-failed": "陪讀者這輪沒讀成,沒有存下。稍後再試。",
} as const;

export type MsgKey = keyof typeof zhHant;

export const en: Record<MsgKey, string> = {
  "brand": "hyenovel",
  "rail.works": "Works",
  "rail.settings": "Settings",
  "rail.dayNight": "Toggle light or dark",
  "rail.new": "New conversation",
  "rail.fresh": "Something new",
  "rail.busy": "Analyzing",
  "menu.submitNew": "Submit a new one",
  "home.waiting": "\"{title}\" is read.",
  "home.listen": "Listen ›",
  "home.placeholder": "What's on your mind? You can also drop a draft in",
  "home.placeholderEmpty": "Drop a draft here, or paste it",
  "home.which": "About which one",
  "home.meet": "Companions",
  "talk.empty": "Your reading companion is here.",
  "talk.who": "Companion",
  "talk.start": "Tell {name} what you'd like to talk about.",
  "talk.waiting": "{name} is reading...",
  "talk.switched": "{name} takes over",
  "talk.send": "Send",
  "talk.input": "Message",
  "talk.placeholder": "Say something to {name}...",
  "talk.dropQuote": "Remove this quote",
  "reader.bring": "Bring into the talk",
  "reader.tooLong": "Select less (within 400 characters)",
  "paper.versions": "Versions",
  "paper.oldVersion": "This is version {n}",
  "paper.latest": "Back to the latest",
  "paper.resume": "Resume",
  "state.running": "Analyzing",
  "state.notesRunning": "Analysis done; notes still being written",
  "state.notesStopped": "The notes stalled",
  "state.allReady": "Analysis and notes are both done",
  "state.ready": "Analysis done",
  "state.stopped": "The analysis stalled",
  "state.stale": "The new version isn't analyzed yet",
  "state.none": "Not analyzed yet",
  "feed.text": "Draft",
  "feed.chars": "{n} chars",
  "feed.estimate": "About {min} min",
  "feed.noEstimate": "First analysis, no estimate yet.",
  "feed.go": "Submit and analyze (uses your subscription quota)",
  "feed.sending": "Sending...",
  "feed.cancel": "Cancel",
  "feed.already": "This draft is already here. Switched to it.",
  "notice.dismiss": "Dismiss notice",
  "job.step.analyst": "Reading it through",
  "job.step.reviewer": "Writing prep notes",
  "notes.open": "Cold reader's notes",
  "notes.close": "Close notes",
  "notes.running": "Notes are still being written",
  "notes.none": "No notes yet",
  "notes.lead": "These are another cold reader's notes",
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
  "err.quote-needs-message": "Add a line of your own when you bring a quote.",
  "err.too-many-quotes": "You can bring at most 4 passages at a time.",
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
  "err.unknown-version": "That version doesn't exist.",
  "err.legacy-session": "This is an archived discussion from before the redesign. You can read it but not continue it.",
  "err.ambiguous-session": "Two works share this session id, so it can't be told which one you mean.",
  "err.usage-limit": "The subscription usage limit is reached. Retrying now won't help; wait until it resets.",
  "err.no-response": "The companion did not respond, and this turn was not saved. You can send it again.",
  "err.commit-failed": "Saving failed, and this turn was not saved. You can send it again.",
  "err.chat-failed": "The companion could not finish this turn, and it was not saved. Try again later.",
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
