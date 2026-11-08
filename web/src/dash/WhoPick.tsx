import { useRef, useState } from "react";
import type { Character } from "./api";
import Figure, { type FigureState } from "./Figure";
import { localized, useLang, useT } from "./i18n";
import { useCharacters } from "./useCharacters";

/** 陪讀者選擇:輸入紙上緣的角色本身就是鈕,點它往上開清單;Esc 關閉。 */
export default function WhoPick({ me, onPick, size = 22, state }: {
  me: Character; onPick: (id: string) => void; size?: number; state?: FigureState;
}) {
  const t = useT();
  const lang = useLang();
  const chars = useCharacters();
  const [open, setOpen] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  return (
    <div className="dash-who who">
      <button type="button" ref={toggle} className="ib dash-who-key" aria-haspopup="true" aria-expanded={open}
        aria-label={t("talk.whoIs", { name: localized(me.name, lang) })} title={t("talk.whoIs", { name: localized(me.name, lang) })}
        onClick={() => setOpen(m => !m)}>
        <Figure character={me} size={size} state={state} />
      </button>
      {open && (
        <div className="dash-float dash-who-menu" role="group" aria-label={t("talk.who")}
          onKeyDown={e => { if (e.key === "Escape") { e.stopPropagation(); setOpen(false); toggle.current?.focus(); } }}>
          {chars.active.map(c => (
            <button key={c.id} type="button" className="dash-who-item" aria-pressed={c.id === me.id}
              autoFocus={c.id === me.id}
              onClick={() => { onPick(c.id); setOpen(false); toggle.current?.focus(); }}>
              <Figure character={c} size={48} /><span className="dash-who-name">{localized(c.name, lang)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
