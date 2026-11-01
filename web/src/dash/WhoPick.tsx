import { useRef, useState } from "react";
import type { Character } from "./api";
import Avatar from "./Avatar";
import { localized, useLang, useT } from "./i18n";
import { useCharacters } from "./useCharacters";

/** 輸入框旁的陪讀者選擇 ▾:鍵帽 + 往上開的清單;Esc 關閉。 */
export default function WhoPick({ me, onPick }: { me: Character; onPick: (id: string) => void }) {
  const t = useT();
  const lang = useLang();
  const chars = useCharacters();
  const [open, setOpen] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  return (
    <div className="dash-who">
      <button type="button" ref={toggle} className="dash-key" aria-haspopup="true" aria-expanded={open}
        aria-label={t("talk.who")} onClick={() => setOpen(m => !m)}>
        <Avatar character={me} size={22} />{localized(me.name, lang)} <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="dash-float dash-who-menu" role="group" aria-label={t("talk.who")}
          onKeyDown={e => { if (e.key === "Escape") { e.stopPropagation(); setOpen(false); toggle.current?.focus(); } }}>
          {chars.list.map(c => (
            <button key={c.id} type="button" className="dash-who-item" aria-pressed={c.id === me.id}
              autoFocus={c.id === me.id}
              onClick={() => { onPick(c.id); setOpen(false); toggle.current?.focus(); }}>
              <Avatar character={c} size={22} />{localized(c.name, lang)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
