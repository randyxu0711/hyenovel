import { useEffect, useRef, useState, type ClipboardEvent, type DragEvent, type KeyboardEvent } from "react";
import { useLocation } from "react-router-dom";
import type { SubmitResult, Work } from "./api";
import Figure from "./Figure";
import Icon from "./Icon";
import { errorMessage, useT } from "./i18n";
import { DRAFT_MIN_CHARS, useSubmitDraft } from "./useSubmitDraft";
import { useCharacters } from "./useCharacters";
import { companionId } from "./useTalk";

/** 進門:只有一張交稿的紙。貼長文、拖檔、交稿鈕開檔都進確認條。 */
export default function Home({ works: loaded, error: listError = null, onSubmitted }: {
  /** null = 清單還沒到或抓不到(這時不說「沒有作品」)。 */
  works: Work[] | null;
  /** 清單抓不到的 den 錯誤碼。 */
  error?: string | null;
  /** 交稿完成(含已存在的同稿)。existing = 沒有開新 job。 */
  onSubmitted: (slug: string, existing: boolean) => void;
}) {
  const t = useT();
  const loc = useLocation();
  const chars = useCharacters();
  const area = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
  const { draft, busy, error, fromFile, fromText, confirm, cancel } = useSubmitDraft();
  const me = chars.byId(companionId(chars));

  const wantsFocus = (loc.state as { focus?: boolean } | null)?.focus === true;
  useEffect(() => { if (wantsFocus) area.current?.focus(); }, [wantsFocus, loc.key, draft]);

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== "Enter" || e.shiftKey || e.nativeEvent.isComposing) return;
    e.preventDefault();
    if (text.trim().length > DRAFT_MIN_CHARS) fromText(text);
  };
  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const pasted = e.clipboardData.getData("text");
    if (pasted.trim().length > DRAFT_MIN_CHARS) { e.preventDefault(); fromText(pasted); }
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f && !busy) void fromFile(f);
  };
  const submitDraft = async () => {
    const r: SubmitResult | null = await confirm();
    if (r) onSubmitted(r.slug, r.reused);
  };

  const none = loaded !== null && loaded.length === 0;
  const est = draft?.estimate;
  return (
    <div className="home" onDragOver={e => e.preventDefault()} onDrop={onDrop}>
      <div className="home-inner">
        {none && <p className="home-first"><Icon name="new" />{t("home.first")}</p>}
        {draft ? (
          <div className="composer home-draft" role="group" aria-label={t("feed.text")}>
            <div className="who"><Figure character={me} size={92} /></div>
            {draft.title && <b className="home-draft-title">{draft.title}</b>}
            <p className="home-meta">
              <span>{t("feed.chars", { n: draft.chars })}</span>
              {est && <span>{est.v ? t("feed.estimate", { min: Math.max(1, Math.round(est.v.seconds / 60)) }) : t("feed.noEstimate")}</span>}
            </p>
            {error && <p role="alert" className="home-msg">{t(errorMessage(error))}</p>}
            <div className="home-actions">
              <button type="button" className="dash-key" onClick={cancel}>{t("feed.cancel")}</button>
              <button type="button" className="dash-key home-go" disabled={busy} onClick={() => void submitDraft()}>
                {busy ? t("feed.sending") : t("feed.go")}
              </button>
            </div>
          </div>
        ) : (
          <form className="composer" onSubmit={e => e.preventDefault()}>
            <div className="who"><Figure character={me} size={92} /></div>
            <textarea ref={area} rows={3} value={text} aria-label={t("home.drop")} placeholder={t("home.drop")}
              onChange={e => setText(e.target.value)} onKeyDown={onKey} onPaste={onPaste} />
            {error && <p role="alert" className="home-msg">{t(errorMessage(error))}</p>}
            <div className="bar">
              <button type="button" className="ib send" aria-label={t("home.pick")} title={t("home.pick")}
                onClick={() => fileInput.current?.click()}><Icon name="new" /></button>
              <input ref={fileInput} type="file" accept=".md,.txt" hidden
                onChange={e => { const f = e.target.files?.[0]; e.target.value = ""; if (f && !busy) void fromFile(f); }} />
            </div>
          </form>
        )}
        {loaded === null && (listError
          ? <p role="alert" className="home-msg">{t(errorMessage(listError))}</p>
          : <p className="home-msg" role="status">{t("loading")}</p>)}
      </div>
    </div>
  );
}
