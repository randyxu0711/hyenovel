import { useEffect, useState } from "react";
import type { WorkMap } from "./api";
import { Matrix } from "./ChartTab";
import { useT } from "./i18n";

/** 印一次的時間:欄一欄一欄出現約 1.2s,印完停一下再收起。 */
const PRINT_MS = 1600;
const still = () => !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** 紙頂的印字頭:running 時來回移動(只表示「在跑」,不畫點陣、不顯示進度);
 *  printed(analyst 那一步完成、這版的分析到手)時把點陣張力印一次,印完或點一下就收起。減動時不顯示。 */
export default function PrintHead({ running, printed, map }: { running: boolean; printed: boolean; map: WorkMap | null }) {
  const t = useT();
  const [over, setOver] = useState(false);
  const printing = printed && !over && !!map && map.beats.length > 0;
  useEffect(() => {
    if (!printing) return;
    const h = setTimeout(() => setOver(true), PRINT_MS);
    return () => clearTimeout(h);
  }, [printing]);
  if (still() || over) return null;
  if (printing) {
    return (
      <div className="dash-print" title={t("print.skip")} onClick={() => setOver(true)}>
        <Matrix beats={map!.beats} marks={[]} print />
      </div>
    );
  }
  return running ? <div className="dash-printhead" aria-hidden="true"><i /></div> : null;
}
