import { useEffect, useRef, type DragEvent } from "react";
import { useLocation } from "react-router-dom";
import type { SubmitResult, Work } from "./api";
import { errorMessage, localized, useLang, useT } from "./i18n";
import { DRAFT_MIN_CHARS, useSubmitDraft } from "./useSubmitDraft";
import Talk from "./Talk";
import { useCharacters } from "./useCharacters";
import { MAX_CHAT, type Talk as TalkState } from "./useTalk";

/** 進門:一欄置中的純聊天;貼長文、拖檔進來就在輸入框上方出交稿確認條。 */
export default function Home({ works: loaded, error: listError = null, onSubmitted, talk }: {
  /** null = 清單還沒到或抓不到(這時不說「沒有作品」)。 */
  works: Work[] | null;
  /** 清單抓不到的 den 錯誤碼。 */
  error?: string | null;
  /** 交稿完成(含已存在的同稿)。existing = 沒有開新 job。 */
  onSubmitted: (slug: string, existing: boolean) => void;
  talk: TalkState;
}) {
  const t = useT();
  const lang = useLang();
  const loc = useLocation();
  const chars = useCharacters();
  const area = useRef<HTMLTextAreaElement>(null);
  const { draft, busy, error, fromFile, fromText, confirm, cancel } = useSubmitDraft();

  const wantsFocus = (loc.state as { focus?: boolean } | null)?.focus === true;
  useEffect(() => { if (wantsFocus) area.current?.focus(); }, [wantsFocus, loc.key, draft]);

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f && !busy) void fromFile(f);
  };
  const submitDraft = async () => {
    const r: SubmitResult | null = await confirm();
    if (r) onSubmitted(r.slug, r.reused);
  };

  const est = draft?.estimate;
  const card = draft ? (
    <div className="home-draft" role="group" aria-label={t("feed.text")}>
      {draft.title && <b className="home-draft-title">{draft.title}</b>}
      <p className="home-meta">
        <span>{t("feed.chars", { n: draft.chars })}</span>
        {est?.v && <span>{t("feed.estimate", { min: Math.max(1, Math.round(est.v.seconds / 60)) })}</span>}
      </p>
      {error && <p role="alert" className="home-msg">{t(errorMessage(error))}</p>}
      <div className="home-actions">
        <button type="button" className="dash-key" onClick={cancel}>{t("feed.cancel")}</button>
        <span className="nc-note">{t("nc.costs")}</span>
        <button type="button" className="dash-key home-go" disabled={busy} onClick={() => void submitDraft()}>
          {busy ? t("feed.sending") : t("feed.go")}
        </button>
      </div>
    </div>
  ) : error ? <p role="alert" className="home-msg home-draft-msg">{t(errorMessage(error))}</p> : null;

  const live = talk.turns.length > 0 || talk.streaming !== null || talk.pending !== null;
  return (
    <div className="home" onDragOver={e => e.preventDefault()} onDrop={onDrop}>
      <section className="home-talk" aria-label={t("home.chat")} data-live={live ? "" : undefined}>
        <Talk talk={talk} version={0} quotes={[]} analyzing={false} onDropQuote={() => {}} onSent={() => {}} onReveal={() => {}}
          longText={{ min: live ? MAX_CHAT : DRAFT_MIN_CHARS, take: fromText }} onFile={f => { if (!busy) void fromFile(f); }}
          above={card} inputRef={area} whoSize={172}
          placeholder={t("home.say", { name: localized(chars.byId(talk.whoId).name, lang) })} />
      </section>
      {loaded === null && (listError
        ? <p role="alert" className="home-msg">{t(errorMessage(listError))}</p>
        : <p className="home-msg" role="status">{t("loading")}</p>)}
    </div>
  );
}
