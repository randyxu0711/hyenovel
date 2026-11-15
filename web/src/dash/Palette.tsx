import { useEffect, useRef, useState, type ReactNode } from "react";
import { DashError, type Work } from "./api";
import Figure from "./Figure";
import Icon from "./Icon";
import { errorMessage, localized, useLang, useT, type MsgKey } from "./i18n";
import type { Characters } from "./useCharacters";
import { useThemeState } from "./theme";
import { setCompanion } from "./useTalk";

type Group = "works" | "companions" | "misc";
type Item = { id: string; label: string; text: string; group: Group; lead?: ReactNode; run: () => void | Promise<void> };
const HEADS: Partial<Record<Group, MsgKey>> = { works: "palette.g.works", companions: "palette.g.companions" };

/** ⌘K / Ctrl+K 的指令框:搜作品、換預設陪讀者、開設定、切晝夜。方向鍵移動、Enter 執行、Esc 關(焦點還給開之前的元素)。 */
export default function Palette({ works, chars, onOpen, onSettings, onToggle, onClose }: {
  works: Work[]; chars: Characters;
  onOpen: (slug: string) => void; onSettings: () => void; onToggle: () => void; onClose: () => void;
}) {
  const t = useT();
  const lang = useLang();
  const { mode } = useThemeState();
  const [q, setQ] = useState("");
  const [at, setAt] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const busy = useRef(false);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    const back = document.activeElement as HTMLElement | null;
    input.current?.focus();
    return () => { alive.current = false; back?.focus?.(); };
  }, []);

  const all: Item[] = [
    ...works.map((w): Item => ({ id: `w-${w.slug}`, group: "works", text: w.title, label: t("palette.work", { title: w.title }), run: () => onOpen(w.slug) })),
    ...chars.active.map((c): Item => {
      const name = localized(c.name, lang);
      return { id: `c-${c.id}`, group: "companions", text: name, label: t("palette.companion", { name }), lead: <Figure character={c} size={20} />, run: () => setCompanion(chars, c.id) };
    }),
    { id: "settings", group: "misc", text: t("palette.settings"), label: t("palette.settings"), lead: <Icon name="gear" />, run: onSettings },
    { id: "daynight", group: "misc", text: t("palette.dayNight"), label: t("palette.dayNight"), lead: <Icon name={mode === "dark" ? "sun" : "moon"} />, run: onToggle },
  ];
  const needle = q.trim().toLowerCase();
  const items = needle ? all.filter(i => i.label.toLowerCase().includes(needle)) : all;
  const active = Math.min(at, items.length - 1);
  const run = (i: Item | undefined) => {
    if (!i || busy.current) return;
    setErr(null);
    const done = i.run();
    if (!(done instanceof Promise)) { onClose(); return; }
    busy.current = true;
    done.then(() => { if (alive.current) onClose(); },
      e => { if (alive.current) setErr(e instanceof DashError ? e.code : "unknown"); })
      .finally(() => { busy.current = false; });
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;   // 輸入法組字中:這些鍵是給候選字的
    if (e.key === "Escape") { e.preventDefault(); onClose(); }
    else if (e.key === "ArrowDown" && items.length) { e.preventDefault(); setAt((active + 1) % items.length); }
    else if (e.key === "ArrowUp" && items.length) { e.preventDefault(); setAt((active - 1 + items.length) % items.length); }
    else if (e.key === "Enter") { e.preventDefault(); run(items[active]); }
  };
  return (
    <div className="dash-palette-scrim" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="dash-float dash-palette" role="dialog" aria-modal="true" aria-label={t("palette.label")} onKeyDown={onKey}>
        <input ref={input} type="text" role="combobox" aria-expanded="true" aria-controls="dash-palette-list" aria-autocomplete="list"
          aria-label={t("palette.input")} aria-activedescendant={items[active] ? `dash-palette-${items[active].id}` : undefined}
          placeholder={t("palette.input")} value={q} onChange={e => { setQ(e.target.value); setAt(0); }} />
        <ul id="dash-palette-list" role="listbox" aria-label={t("palette.label")}>
          {items.flatMap((i, n) => {
            const head = HEADS[i.group];
            const first = n === 0 || items[n - 1].group !== i.group;
            return [
              first && (head
                ? <li key={`h-${i.group}`} role="presentation" aria-hidden="true" className="dash-palette-h">{t(head)}</li>
                : n > 0 && <li key={`h-${i.group}`} role="presentation" aria-hidden="true" className="dash-palette-gap" />),
              <li key={i.id} id={`dash-palette-${i.id}`} role="option" aria-selected={n === active} aria-label={i.label}
                onMouseMove={() => setAt(n)} onClick={() => run(i)}>
                {i.lead && <span className="dash-palette-lead" aria-hidden="true">{i.lead}</span>}<span>{i.text}</span>
              </li>,
            ];
          })}
        </ul>
        {items.length === 0 && <p className="dash-palette-empty">{t("palette.empty")}</p>}
        {err && <p className="dash-palette-empty" role="alert">{t(errorMessage(err))}</p>}
      </div>
    </div>
  );
}
