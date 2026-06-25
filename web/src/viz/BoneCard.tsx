import Scene3D from "../journey/Scene3D";
import Bone3D from "./Bone3D";

// 目錄卡片:迷你 3D 骨頭(緩轉,關 bloom 省效能)。與單篇是同一根骨。
export default function BoneCard({ seed, w = 300, h = 196 }: { seed: number; w?: number; h?: number }) {
  return (
    <div style={{ width: w, height: h }}>
      <Scene3D bloom={false} camera={[0, 0, 8]}><Bone3D seed={seed} spin /></Scene3D>
    </div>
  );
}
