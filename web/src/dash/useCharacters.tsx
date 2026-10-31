import { createContext, useContext, type ReactNode } from "react";
import type { Character } from "./api";

export type Characters = {
  list: Character[];
  /** 永遠回一個角色:找不到 id(角色之後被刪、舊局沒記)→ 同 mode 的 → 預設。 */
  byId: (id: string | null, mode?: string | null) => Character;
  defaultId: string;
};

export function makeCharacters(list: Character[], defaultId: string): Characters {
  const fallback = list.find(c => c.id === defaultId) ?? list[0];
  return {
    list, defaultId,
    byId: (id, mode) =>
      list.find(c => c.id === id) ?? (mode ? list.find(c => c.mode === mode) : undefined) ?? fallback,
  };
}

const Ctx = createContext<Characters | null>(null);

/** 角色清單載入一次、整個 dashboard 共用。 */
export function CharactersProvider({ value, children }: { value: Characters; children: ReactNode }) {
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCharacters(): Characters {
  const v = useContext(Ctx);
  if (!v) throw new Error("useCharacters 要在 CharactersProvider 底下用");
  return v;
}
