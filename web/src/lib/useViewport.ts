import { useEffect, useState } from "react";

// 視窗尺寸(隨 resize 更新)。Camera 與 Catalog 都靠它換算世界↔螢幕座標。
export function useViewport() {
  const [vp, setVp] = useState({
    w: typeof window !== "undefined" ? window.innerWidth : 1280,
    h: typeof window !== "undefined" ? window.innerHeight : 720,
  });
  useEffect(() => {
    const on = () => setVp({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return vp;
}
