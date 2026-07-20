// 大氣層(spec art-immersion §3B):塵埃分 3 深度層,各層以 par 係數跟隨相機位移做視差。
// 相機不動時只剩各自的緩慢上漂(現狀行為);相機旅行時,天空顯出深度。
// 座標是螢幕空間(Dust 在 .cam 外、position:fixed),不吃相機縮放 —— 只吃位移。
export interface DustLayer {
  n: number;      // 粒數
  par: number;    // 視差係數(0=貼死背景)
  rMin: number; rMax: number;   // 粒徑(螢幕 px;fixed 層不乘 0.75)
  drift: number;  // 上漂速度
  alpha: number;  // 亮度上限
}
export const DUST_LAYERS: DustLayer[] = [
  { n: 26, par: 0.04, rMin: 0.2, rMax: 0.7, drift: 0.03, alpha: 0.18 },
  { n: 18, par: 0.09, rMin: 0.5, rMax: 1.1, drift: 0.06, alpha: 0.26 },
  { n: 12, par: 0.16, rMin: 0.9, rMax: 1.7, drift: 0.10, alpha: 0.36 },
];

// 相機位移 → 該層畫布位移。Dust 每幀向它 lerp 逼近,自然近似相機的簽名緩動。
export const layerShift = (cam: { x: number; y: number }, par: number) =>
  ({ x: cam.x * par, y: cam.y * par });
