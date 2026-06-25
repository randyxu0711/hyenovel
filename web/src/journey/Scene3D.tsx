import { Canvas, useThree, useFrame } from "@react-three/fiber";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import type { ReactNode } from "react";

// dolly:0=靜止遠景,1=拉近。換 tab 時脈衝到 1 再回 0 → 相機推進/退開。
function Rig({ dolly }: { dolly: number }) {
  const { camera } = useThree();
  useFrame(() => {
    const targetZ = 9 - dolly * 3.4;
    camera.position.z += (targetZ - camera.position.z) * 0.1;
    camera.lookAt(0, 0, 0);
  });
  return null;
}

// 持久 3D 場景:暗場 + 暖主光/冷補光 + bloom 輝光。骨頭元件當 children。
export default function Scene3D(
  { children, camera, dolly = 0, bloom = true }:
  { children: ReactNode; camera?: [number, number, number]; dolly?: number; bloom?: boolean },
) {
  return (
    <Canvas camera={{ position: camera ?? [0, 0, 9], fov: 42 }} dpr={[1, 2]} gl={{ antialias: true }}>
      <color attach="background" args={["#0c0b09"]} />
      <ambientLight intensity={0.4} />
      <directionalLight position={[4, 6, 5]} intensity={1.15} color="#ffe6c0" />
      <directionalLight position={[-5, -2, -4]} intensity={0.5} color="#9fb6d0" />
      {children}
      <Rig dolly={dolly} />
      {bloom && (
        <EffectComposer>
          <Bloom intensity={0.9} luminanceThreshold={0.22} luminanceSmoothing={0.32} mipmapBlur />
        </EffectComposer>
      )}
    </Canvas>
  );
}
