import { useEffect, useRef, useState, type ClipboardEvent, type DragEvent, type KeyboardEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api, type SubmitResult, type Work } from "./api";
import Avatar from "./Avatar";
import { errorMessage, localized, useLang, useT } from "./i18n";
import { DRAFT_MIN_CHARS, useSubmitDraft } from "./useSubmitDraft";
import { useCharacters } from "./useCharacters";
import WhoPick from "./WhoPick";
import { companionId, MAX_CHAT } from "./useTalk";

const CHIPS = 5;
const READ_STATES = ["ready", "notes-running", "notes-stopped"];

/** 最近一篇讀完了、而且它的最新版還沒聊過 → 回它,否則 null。works 已依最近活動排序。 */
export function waitingLine(works: Work[], talkedVersions: Record<string, number[]>): { slug: string; title: string } | null {
  const w = works[0];
  if (!w || !READ_STATES.includes(w.state)) return null;
  if ((talkedVersions[w.slug] ?? []).includes(w.version)) return null;
  return { slug: w.slug, title: w.title };
}

/** 進門:一句話、一個輸入框。送出不在這裡做,導到作品頁由那邊以新局送出。 */
export default function Home({ works, onSubmitted }: {
  works: Work[];
  /** 交稿完成(含已存在的同稿)。existing = 沒有開新 job。 */
  onSubmitted: (slug: string, existing: boolean) => void;
}) {
  const t = useT();
  const lang = useLang();
  const nav = useNavigate();
  const loc = useLocation();
  const chars = useCharacters();
  const area = useRef<HTMLTextAreaElement>(null);
  const [text, setText] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
  const [talked, setTalked] = useState<Record<string, number[]>>({});
  const { draft, busy, error, fromFile, fromText, confirm, cancel } = useSubmitDraft();
  const [who, setWho] = useState<string | null>(null);
  const me = chars.byId(who ?? companionId(chars));
  const latest = works[0];
  const chosen = picked && works.slice(0, CHIPS).some(w => w.slug === picked) ? picked : latest?.slug;

  // 新對話 / 交一篇新的 回到這裡時,把游標放進輸入框。
  const wantsFocus = (loc.state as { focus?: boolean } | null)?.focus === true;
  useEffect(() => { if (wantsFocus) area.current?.focus(); }, [wantsFocus, loc.key, draft]);

  // 只為最近那一篇查有沒有聊過它的最新版。
  const slug = latest && READ_STATES.includes(latest.state) ? latest.slug : null;
  useEffect(() => {
    if (!slug) return;
    let live = true;
    api.sessions(slug).then(rows => {
      if (live) setTalked(m => ({ ...m, [slug]: rows.flatMap(r => (r.version === null ? [] : [r.version])) }));
    }, () => { /* 查不到就不顯示等候的那句 */ });
    return () => { live = false; };
  }, [slug, latest?.version]);
  const waiting = slug && talked[slug] ? waitingLine(works, talked) : null;

  const send = () => {
    const message = text.trim();
    if (!message || !chosen) return;
    nav(`/w/${encodeURIComponent(chosen)}`, { state: { firstMessage: message, character: me.id } });
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); }
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

  const none = works.length === 0;
  const est = draft?.estimate;
  return (
    <div className="home" onDragOver={e => e.preventDefault()} onDrop={onDrop}>
      <div className="home-inner">
        {waiting && (
          <div className="home-waiting">
            <Avatar character={me} size={32} />
            <div>
              <p className="home-who">{localized(me.name, lang)}</p>
              <p className="home-line">{t("home.waiting", { title: waiting.title })}</p>
              <Link className="home-listen" to={`/w/${encodeURIComponent(waiting.slug)}`}>{t("home.listen")}</Link>
            </div>
          </div>
        )}
        {draft ? (
          <div className="dash-float home-box home-draft" role="group" aria-label={t("feed.text")}>
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
          <form className="dash-float home-box" onSubmit={e => { e.preventDefault(); send(); }}>
            <textarea ref={area} rows={2} value={text} maxLength={MAX_CHAT} aria-label={t("talk.input")}
              placeholder={t(none ? "home.placeholderEmpty" : "home.placeholder")}
              onChange={e => setText(e.target.value)} onKeyDown={onKey} onPaste={onPaste} />
            {error && <p role="alert" className="home-msg">{t(errorMessage(error))}</p>}
            {!none && (
              <div className="home-row">
                <WhoPick me={me} onPick={setWho} />
                <button type="submit" className="dash-key home-send" disabled={!text.trim()}>{t("talk.send")}</button>
              </div>
            )}
          </form>
        )}
        {none ? (
          <ul className="home-meet" aria-label={t("home.meet")}>
            {chars.list.map(c => (
              <li key={c.id}>
                <Avatar character={c} size={26} />
                <b>{localized(c.name, lang)}</b>
                <span>{localized(c.line, lang)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="home-recent" role="group" aria-label={t("home.which")}>
            <span>{t("home.which")}</span>
            {works.slice(0, CHIPS).map(w => (
              <button key={w.slug} type="button" className="home-chip" aria-pressed={w.slug === chosen}
                onClick={() => setPicked(w.slug)}>{w.title}</button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
