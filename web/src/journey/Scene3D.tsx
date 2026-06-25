import { Canvas } from "@react-three/fiber";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import type { ReactNode } from "react";

// 持久 3D 場景:暗場 + 暖主光/冷補光 + bloom 輝光。骨頭元件當 children。
export default function Scene3D({ children, camera }: { children: ReactNode; camera?: [number, number, number] }) {
  return (
    <Canvas camera={{ position: camera ?? [0, 0, 9], fov: 42 }} dpr={[1, 2]} gl={{ antialias: true }}>
      <color attach="background" args={["#0c0b09"]} />
      <fog attach="fog" args={["#0c0b09", 12, 26]} />
      <ambientLight intensity={0.35} />
      <directionalLight position={[4, 6, 5]} intensity={1.15} color="#ffe6c0" />
      <directionalLight position={[-5, -2, -4]} intensity={0.5} color="#9fb6d0" />
      {children}
      <EffectComposer>
        <Bloom intensity={0.9} luminanceThreshold={0.22} luminanceSmoothing={0.32} mipmapBlur />
      </EffectComposer>
    </Canvas>
  );
}
