import { useState, type KeyboardEvent } from "react";
import { useT, type MsgKey } from "./i18n";
import { cleanWord, composePlist, type Plist } from "./plistFormat";
import Icon from "./Icon";

type Side = "traits" | "speech";
const SIDES: { side: Side; key: MsgKey; add: MsgKey }[] = [
  { side: "traits", key: "card.depth.traits", add: "card.depth.addTraits" },
  { side: "speech", key: "card.depth.speech", add: "card.depth.addSpeech" },
];

export default function PlistWords({ plist, limit, onChange }: { plist: Plist; limit?: number; onChange?: (next: Plist) => void }) {
  const t = useT();
  return (
    <div className="plist" role="group" aria-label={t("card.depth")} data-edit={onChange ? "" : undefined}>
      {SIDES.map(({ side, key, add }) => (plist[side].length > 0 || onChange) && (
        <div key={side} className="plist-row">
          <span className="plist-k">{t(key)}</span>
          <span className="plist-words">
            {plist[side].map((w, i) => (
              <span key={`${i}-${w}`} className="plist-w">
                {w}
                {onChange && (
                  <button type="button" className="plist-x" aria-label={t("card.depth.drop", { word: w })} title={t("card.depth.drop", { word: w })}
                    onClick={() => onChange({ ...plist, [side]: plist[side].filter((_, j) => j !== i) })}><Icon name="close" /></button>
                )}
              </span>
            ))}
            {onChange && <WordInput label={t(add)} onAdd={ws => {
              const next = { ...plist, [side]: [...plist[side], ...ws] };
              if (limit !== undefined && composePlist(next).length > limit) return false;
              onChange(next);
              return true;
            }} onPop={() => plist[side].length > 0 && onChange({ ...plist, [side]: plist[side].slice(0, -1) })} />}
          </span>
        </div>
      ))}
    </div>
  );
}

function WordInput({ label, onAdd, onPop }: { label: string; onAdd: (words: string[]) => boolean; onPop: () => void }) {
  const [text, setText] = useState("");
  const commit = (raw: string, rest = "") => {
    const ws = raw.split(/[,，、]/).map(cleanWord).filter(Boolean);
    if (ws.length === 0 || onAdd(ws)) setText(rest);
  };
  const key = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.nativeEvent.isComposing) return;
    if (e.key === "Enter") { e.preventDefault(); commit(text); }
    else if (e.key === "Backspace" && text === "") onPop();
  };
  return (
    <input className="plist-in" aria-label={label} title={label} autoComplete="off" value={text} placeholder="+" size={Math.max(1, text.length)}
      onKeyDown={key} onBlur={() => commit(text)}
      onChange={e => {
        const v = e.target.value;
        const cut = Math.max(v.lastIndexOf(","), v.lastIndexOf("，"), v.lastIndexOf("、"));
        if (cut >= 0) commit(v.slice(0, cut), v.slice(cut + 1));
        else setText(v);
      }} />
  );
}
