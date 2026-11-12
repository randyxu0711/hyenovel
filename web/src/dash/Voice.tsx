import { useEffect, useRef, useState } from "react";
import { api, DashError } from "./api";
import Icon from "./Icon";
import { errorMessage, useT } from "./i18n";

export default function Voice({ session, seq, initial, onChange }: {
  session: string; seq: number; initial: boolean;
  onChange: (voice: boolean) => void;
}) {
  const t = useT();
  const [voiced, setVoiced] = useState(initial);
  const [code, setCode] = useState<string | null>(null);
  const confirmed = useRef(initial);
  const latest = useRef(0);
  const queue = useRef<Promise<void>>(Promise.resolve());

  const reported = useRef(initial);

  useEffect(() => {
    if (initial === reported.current) return;
    reported.current = initial; confirmed.current = initial; setVoiced(initial);
  }, [initial]);

  const show = (next: boolean) => { reported.current = next; setVoiced(next); onChange(next); };

  const press = () => {
    const next = !voiced;
    const mine = ++latest.current;
    show(next); setCode(null);
    queue.current = queue.current.then(async () => {
      try {
        await (next ? api.setVoice(session, seq) : api.clearVoice(session, seq));
        confirmed.current = next;
      } catch (e) {
        if (mine !== latest.current) return;
        show(confirmed.current);
        setCode(e instanceof DashError ? e.code : "unknown");
      }
    });
  };

  return (
    <>
      <button type="button" className={voiced ? "chat-act chat-voice is-on" : "chat-act chat-voice"} aria-pressed={voiced}
        aria-label={t("reply.voice")} title={t("reply.voiceNote")} onClick={press}>
        <Icon name={voiced ? "forkOn" : "fork"} />
      </button>
      {code && <p className="chat-react-err" role="alert">{t(errorMessage(code))}</p>}
    </>
  );
}
