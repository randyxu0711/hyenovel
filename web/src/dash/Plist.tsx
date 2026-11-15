import { useEffect, useState, type KeyboardEvent } from "react";
import { useT, type MsgKey } from "./i18n";
import { cleanWord, composePlist, type Plist } from "./plistFormat";
import Icon from "./Icon";

type Side = "traits" | "speech";
const SIDES: { side: Side; key: MsgKey; add: MsgKey }[] = [
  { side: "traits", key: "card.depth.traits", add: "card.depth.addTraits" },
  { side: "speech", key: "card.depth.speech", add: "card.depth.addSpeech" },
];
const SEP = /[,，、]/;

export default function PlistWords({ plist, limit, onChange, onPending }: {
  plist: Plist; limit?: number; onChange?: (next: Plist) => void; onPending?: (pending: boolean) => void;
}) {
  const t = useT();
  const [drafts, setDrafts] = useState<Record<Side, string>>({ traits: "", speech: "" });
  const [marked, setMarked] = useState<Side | null>(null);
  const [full, setFull] = useState<Side | null>(null);
  const pending = drafts.traits.trim() !== "" || drafts.speech.trim() !== "";
  useEffect(() => { onPending?.(pending); }, [pending, onPending]);

  const setDraft = (side: Side, text: string) => setDrafts(d => ({ ...d, [side]: text }));
  const add = (side: Side, raw: string, rest: string) => {
    const ws = raw.split(SEP).map(cleanWord).filter(Boolean);
    if (ws.length === 0) { setDraft(side, rest); return; }
    const next = { ...plist, [side]: [...plist[side], ...ws] };
    if (limit !== undefined && composePlist(next).length > limit) { setFull(side); setDraft(side, raw + rest); return; }
    setFull(null);
    setDraft(side, rest);
    onChange!(next);
  };
  const drop = (side: Side, i: number) => {
    setFull(null); setMarked(null);
    onChange!({ ...plist, [side]: plist[side].filter((_, j) => j !== i) });
  };
  const key = (side: Side) => (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.nativeEvent.isComposing) return;
    if (e.key === "Enter") { e.preventDefault(); add(side, drafts[side], ""); return; }
    if (e.key === "Backspace" && drafts[side] === "" && plist[side].length > 0) {
      if (marked === side) drop(side, plist[side].length - 1);
      else setMarked(side);
      return;
    }
    setMarked(null);
  };

  return (
    <div className="plist" role="group" aria-label={t("card.depth")} data-edit={onChange ? "" : undefined}>
      {SIDES.map(({ side, key: label, add: addLabel }) => (plist[side].length > 0 || onChange) && (
        <div key={side} className="plist-row">
          <span className="plist-k">{t(label)}</span>
          <span className="plist-words">
            {plist[side].map((w, i) => (
              <span key={`${i}-${w}`} className="plist-w" data-marked={marked === side && i === plist[side].length - 1 ? "" : undefined}>
                {w}
                {onChange && (
                  <button type="button" className="plist-x" aria-label={t("card.depth.drop", { word: w })} title={t("card.depth.drop", { word: w })}
                    onClick={() => drop(side, i)}><Icon name="close" /></button>
                )}
              </span>
            ))}
            {onChange && (
              <input className="plist-in" aria-label={t(addLabel)} title={t(addLabel)} autoComplete="off" placeholder="+"
                aria-invalid={full === side || undefined} value={drafts[side]} size={Math.max(1, drafts[side].length)}
                onKeyDown={key(side)} onBlur={() => { setMarked(null); add(side, drafts[side], ""); }}
                onChange={e => {
                  const v = e.target.value;
                  const cut = Math.max(v.lastIndexOf(","), v.lastIndexOf("，"), v.lastIndexOf("、"));
                  if (cut >= 0) add(side, v.slice(0, cut), v.slice(cut + 1));
                  else { setDraft(side, v); if (full === side) setFull(null); }
                }} />
            )}
          </span>
          {full === side && <p className="nc-warn plist-full" role="alert">{t("card.depth.full", { n: limit ?? 0 })}</p>}
        </div>
      ))}
    </div>
  );
}
