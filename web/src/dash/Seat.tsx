import type { Character } from "./api";
import Avatar from "./Avatar";
import { localized, useLang, useT } from "./i18n";

/** 對話收起時,陪讀者以頭像坐在紙邊;點它展開。 */
export default function Seat({ character, onOpen }: { character: Character; onOpen: () => void }) {
  const t = useT();
  const name = localized(character.name, useLang());
  return (
    <button type="button" className="dash-seat" aria-label={t("talk.expand", { name })} onClick={onOpen}>
      <Avatar character={character} size={44} />
    </button>
  );
}
