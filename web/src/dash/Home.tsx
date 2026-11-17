import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import type { Work } from "./api";
import { errorMessage, localized, useLang, useT } from "./i18n";
import { DRAFT_MIN_CHARS } from "./useSubmitDraft";
import Talk from "./Talk";
import { useCharacters } from "./useCharacters";
import { MAX_CHAT, type Talk as TalkState } from "./useTalk";

const NAME_MAX = 40;
/** 貼上的稿:第一個非空行當名字(去掉 markdown 標題記號)。 */
export const pastedName = (text: string) =>
  [...(text.split("\n").map(l => l.replace(/^#+\s*/, "").trim()).find(Boolean) ?? "")].slice(0, NAME_MAX).join("");

/** 進門:一欄置中的純聊天;拖檔、貼長文都當附件(要分析就「開成作品」)。 */
export default function Home({ works: loaded, error: listError = null, talk }: {
  /** null = 清單還沒到或抓不到(這時不說「沒有作品」)。 */
  works: Work[] | null;
  /** 清單抓不到的 den 錯誤碼。 */
  error?: string | null;
  talk: TalkState;
}) {
  const t = useT();
  const lang = useLang();
  const loc = useLocation();
  const chars = useCharacters();
  const area = useRef<HTMLTextAreaElement>(null);

  const wantsFocus = (loc.state as { focus?: boolean } | null)?.focus === true;
  useEffect(() => { if (wantsFocus) area.current?.focus(); }, [wantsFocus, loc.key]);

  const live = talk.turns.length > 0 || talk.streaming !== null || talk.pending !== null;
  const paste = (text: string) => { void talk.attachText(pastedName(text) || t("home.pasted"), text); };
  return (
    <div className="home" onDragOver={e => e.preventDefault()}
      onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) void talk.attach(f); }}>
      <section className="home-talk" aria-label={t("home.chat")} data-live={live ? "" : undefined}>
        <Talk talk={talk} version={0} quotes={[]} analyzing={false} onDropQuote={() => {}} onSent={() => {}} onReveal={() => {}}
          longText={{ min: live ? MAX_CHAT : DRAFT_MIN_CHARS, take: paste }} inputRef={area} whoSize={live ? 72 : 172}
          placeholder={t("home.say", { name: localized(chars.byId(talk.whoId).name, lang) })} />
      </section>
      {loaded === null && (listError
        ? <p role="alert" className="home-msg">{t(errorMessage(listError))}</p>
        : <p className="home-msg" role="status">{t("loading")}</p>)}
    </div>
  );
}
