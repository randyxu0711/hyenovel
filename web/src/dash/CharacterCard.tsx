import type { ReactNode } from "react";
import type { Character } from "./api";
import Figure from "./Figure";

export default function CharacterCard({ character, name, sub, on, scanning, size = 40, children, ...rest }: {
  character: Character; name: string; sub?: string; on?: boolean; scanning?: boolean; size?: number; children?: ReactNode;
  onMouseEnter?: () => void; onMouseLeave?: () => void; onFocus?: () => void; onBlur?: () => void;
}) {
  return (
    <article className="char-card" data-on={on} {...rest}>
      <header>
        <Figure character={character} size={size} state={scanning ? "scanning" : undefined} />
        <h2>{name}{sub && sub !== name && <small>{sub}</small>}</h2>
      </header>
      {children}
    </article>
  );
}
