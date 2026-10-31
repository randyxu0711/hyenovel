import { useEffect, useRef, useState } from "react";
import { api, DashError, type WorkDetail } from "./api";
import { errorMessage, useT } from "./i18n";
import { useSelectionQuote } from "./useSelectionQuote";

/** 打字紙:滾筒在上、稿在下;選一段 → 浮動鈕帶進對話。 */
export default function Reader({ slug, companion, onQuote }: {
  slug: string; companion: string; onQuote: (q: string) => void;
}) {
  const t = useT();
  const [work, setWork] = useState<WorkDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const sheet = useRef<HTMLElement>(null);
  const { quote, tooLong, clear } = useSelectionQuote(sheet);

  useEffect(() => {
    let live = true;
    setWork(null); setErr(null);
    api.work(slug).then(w => { if (live) setWork(w); },
      e => { if (live) setErr(e instanceof DashError ? e.code : "unknown"); });
    return () => { live = false; };
  }, [slug]);

  if (err) return <div className="reader-note" role="alert">{t(errorMessage(err))}</div>;
  if (!work) return <div className="reader-note">{t("loading")}</div>;

  return (
    <div className="reader">
      <div className="platen">
        <i /><span className="platen-tools">{t("rail.version", { n: work.version })}</span><i />
      </div>
      <article className="sheet" ref={sheet}>
        <h1>{work.title}</h1>
        {work.text.split(/\n+/).filter(Boolean).map((p, i) => <p key={i}>{p}</p>)}
      </article>
      {quote && (
        <div className="reader-float">
          <button type="button" className="reader-bring" disabled={tooLong}
            onMouseDown={e => e.preventDefault()}
            onClick={() => { onQuote(quote); clear(); }}>
            {t("reader.bring", { name: companion })}
          </button>
          {tooLong && <span role="status">{t("reader.tooLong")}</span>}
        </div>
      )}
    </div>
  );
}
