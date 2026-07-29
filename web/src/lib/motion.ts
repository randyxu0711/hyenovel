// 運鏡家法的 TS 鏡像(正本語意同 theme.css --ease-house/--d-cam/--d-cam-out;framer-motion 吃不到 CSS var)。
// test/motion-tokens.test.ts 釘兩邊同步。
import type { Stage } from "./camera";

export const EASE_HOUSE: [number, number, number, number] = [0.66, 0, 0.2, 1];
export const D_CAM = 1.4;
export const D_CAM_OUT = 0.8;

// 進退場非對稱:俯衝下去是儀式(對焦、承諾),抬起來是視野張開,不必等值。
// 判定用「上一個 stage」而非呼叫端傳旗標 → 所有離開單篇的路徑(退鈕、上一頁、直接改網址)一律涵蓋。
export function camDuration(prev: Stage | null, next: Stage): number {
  return prev === "single" && next !== "single" ? D_CAM_OUT : D_CAM;
}
