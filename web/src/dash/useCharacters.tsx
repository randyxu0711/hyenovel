import { createContext, useContext, type ReactNode } from "react";
import type { Character } from "./api";

export type Characters = {
  list: Character[];
  /** 沒封存的:選單、預設都只從這裡挑。byId 查全部,舊發言才顯示得出名字。 */
  active: Character[];
  reload: () => Promise<void>;
  /** 永遠回一個角色:找不到 id(角色之後被刪、舊局沒記)→ 預設。 */
  byId: (id: string | null) => Character;
  defaultId: string;
};

export function makeCharacters(list: Character[], defaultId: string, reload: () => Promise<void> = async () => {}): Characters {
  const fallback = list.find(c => c.id === defaultId) ?? list[0];
  return {
    list, defaultId, reload,
    active: list.filter(c => !c.archived),
    byId: id => list.find(c => c.id === id) ?? fallback,
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
