import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import { api, DashError } from "./api";
import { errorMessage, useT } from "./i18n";

/** 稿旁的側欄:冷讀者的筆記。首行固定,內容是 den 的備課筆記(markdown)。 */
export default function NotesPanel({ slug }: { slug: string }) {
  const t = useT();
  const [got, setGot] = useState<{ slug: string; text: string } | null>(null);
  const [err, setErr] = useState<{ slug: string; code: string } | null>(null);
  useEffect(() => {
    let live = true;
    api.part(slug, "notes").then(text => { if (live) setGot({ slug, text }); },
      e => { if (live) setErr({ slug, code: e instanceof DashError ? e.code : "unknown" }); });
    return () => { live = false; };
  }, [slug]);
  return (
    <aside className="notes" aria-label={t("notes.open")}>
      <p className="notes-lead">{t("notes.lead")}</p>
      {err?.slug === slug ? <p role="alert">{t(errorMessage(err.code))}</p>
        : got?.slug === slug ? <Markdown>{got.text}</Markdown> : <p>{t("loading")}</p>}
    </aside>
  );
}
