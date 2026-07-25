import type { Conclusion } from "../types";

/** 依 refs 把結論攤到每顆節點(一條多 ref 落多顆)。refs=[] 者不落任何節點——
 *  以節點錨定的必然盲點(spec §5.4b),不硬塞。 */
export function embersByRef(conclusions: Conclusion[]): Record<string, Conclusion[]> {
  const out: Record<string, Conclusion[]> = {};
  for (const c of conclusions)
    for (const ref of c.refs) (out[ref] ??= []).push(c);
  return out;
}
