import { useEffect, useRef, useState } from "react";
import type { Work } from "./api";
import { localized, useLang, useT } from "./i18n";
import type { Characters } from "./useCharacters";
import { setCompanion } from "./useTalk";

type Item = { id: string; label: string; run: () => void };

/** ⌘K / Ctrl+K 的指令框:搜作品、換預設陪讀者、開設定、切晝夜。方向鍵移動、Enter 執行、Esc 關(焦點還給開之前的元素)。 */
export default function Palette({ works, chars, onOpen, onSettings, onToggle, onClose }: {
  works: Work[]; chars: Characters;
  onOpen: (slug: string) => void; onSettings: () => void; onToggle: () => void; onClose: () => void;
}) {
  const t = useT();
  const lang = useLang();
  const [q, setQ] = useState("");
  const [at, setAt] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const back = document.activeElement as HTMLElement | null;
    input.current?.focus();
    return () => back?.focus?.();
  }, []);

  const all: Item[] = [
    ...works.map(w => ({ id: `w-${w.slug}`, label: t("palette.work", { title: w.title }), run: () => onOpen(w.slug) })),
    ...chars.list.map(c => ({ id: `c-${c.id}`, label: t("palette.companion", { name: localized(c.name, lang) }), run: () => setCompanion(c.id) })),
    { id: "settings", label: t("palette.settings"), run: onSettings },
    { id: "daynight", label: t("palette.dayNight"), run: onToggle },
  ];
  const needle = q.trim().toLowerCase();
  const items = needle ? all.filter(i => i.label.toLowerCase().includes(needle)) : all;
  const active = Math.min(at, items.length - 1);
  const run = (i: Item | undefined) => { if (!i) return; i.run(); onClose(); };
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
          value={q} onChange={e => { setQ(e.target.value); setAt(0); }} />
        <ul id="dash-palette-list" role="listbox" aria-label={t("palette.label")}>
          {items.map((i, n) => (
            <li key={i.id} id={`dash-palette-${i.id}`} role="option" aria-selected={n === active}
              onMouseMove={() => setAt(n)} onClick={() => run(i)}>{i.label}</li>
          ))}
        </ul>
        {items.length === 0 && <p className="dash-palette-empty">{t("palette.empty")}</p>}
      </div>
    </div>
  );
}
