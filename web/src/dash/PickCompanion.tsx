import Avatar from "./Avatar";
import { localized, useLang, useT } from "./i18n";
import { useThemeState } from "./theme";
import { useCharacters } from "./useCharacters";

/** 第一次開對話:選誰陪你讀。每個角色一張卡,來自 /api/characters。 */
export default function PickCompanion({ onPick }: { onPick: (id: string) => void }) {
  const t = useT();
  const lang = useLang();
  const { list } = useCharacters();
  const { mode } = useThemeState();
  return (
    <section className="pick" aria-labelledby="pick-h">
      <h2 id="pick-h" className="pick-h">{t("talk.pick")}</h2>
      <ul className="pick-list">
        {list.map(c => (
          <li key={c.id}>
            <button type="button" className="pick-card" onClick={() => onPick(c.id)}>
              <Avatar character={c} size={48} />
              <span className="pick-text">
                <b style={{ color: c.colors[mode].text }}>{localized(c.name, lang)}</b>
                <span>{localized(c.line, lang)}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
