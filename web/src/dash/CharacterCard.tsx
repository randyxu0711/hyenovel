import type { ReactNode } from "react";
import type { Character } from "./api";
import Blob from "./Blob";

export default function CharacterCard({ character, name, sub, on, scanning, children, ...rest }: {
  character: Character; name: string; sub?: string; on?: boolean; scanning?: boolean; children?: ReactNode;
  onMouseEnter?: () => void; onMouseLeave?: () => void; onFocus?: () => void; onBlur?: () => void;
}) {
  return (
    <article className="char-card" data-on={on} {...rest}>
      <header>
        <Blob character={character} size={40} state={scanning ? "scanning" : undefined} />
        <h2>{name}{sub && sub !== name && <small>{sub}</small>}</h2>
      </header>
      {children}
    </article>
  );
}
