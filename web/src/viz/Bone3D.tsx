import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { buildBone3D, type V3 } from "../lib/bone3d";

function Rib({ base, tip, theme }: { base: V3; tip: V3; theme: boolean }) {
  const { mid, quat, length } = useMemo(() => {
    const b = new THREE.Vector3(...base), t = new THREE.Vector3(...tip);
    const dir = new THREE.Vector3().subVectors(t, b);
    const len = dir.length();
    const m = new THREE.Vector3().addVectors(b, t).multiplyScalar(0.5);
    const q = new THREE.Quaternion().setFromUnitVectors(
      new THREE.Vector3(0, 1, 0), dir.clone().normalize(),
    );
    return { mid: m.toArray() as V3, quat: q.toArray() as [number, number, number, number], length: len };
  }, [base, tip]);
  return (
    <>
      <mesh position={mid} quaternion={quat}>
        <cylinderGeometry args={[0.035, 0.06, length, 6]} />
        <meshStandardMaterial color="#e7dcc0" emissive="#3a3324" emissiveIntensity={0.5} roughness={0.55} metalness={0.12} />
      </mesh>
      <mesh position={tip}>
        <sphereGeometry args={[theme ? 0.17 : 0.09, 18, 18]} />
        <meshStandardMaterial
          color={theme ? "#ecc98a" : "#f3ead2"}
          emissive={theme ? "#c8902f" : "#5a5240"}
          emissiveIntensity={theme ? 1.8 : 0.45}
          roughness={0.4} metalness={0.1} />
      </mesh>
    </>
  );
}

export default function Bone3D(
  { seed, spin = false, targetRot }: { seed: number; spin?: boolean; targetRot?: number },
) {
  const ref = useRef<THREE.Group>(null);
  const { spine, ribs } = useMemo(() => buildBone3D(seed), [seed]);
  const curve = useMemo(
    () => new THREE.CatmullRomCurve3(spine.map(p => new THREE.Vector3(...p))),
    [spine],
  );
  useFrame((_, dt) => {
    const g = ref.current;
    if (!g) return;
    if (targetRot !== undefined) g.rotation.y += (targetRot - g.rotation.y) * 0.08; // 換 tab 轉到該面
    else if (spin) g.rotation.y += dt * 0.25;                                       // 目錄緩轉
    g.position.y = Math.sin(performance.now() * 0.0006) * 0.1;                       // 微浮
  });
  return (
    <group ref={ref}>
      <mesh>
        <tubeGeometry args={[curve, 80, 0.12, 12, false]} />
        <meshStandardMaterial color="#efe6cf" emissive="#4a4230" emissiveIntensity={0.5} roughness={0.5} metalness={0.12} />
      </mesh>
      {ribs.map((r, i) => <Rib key={i} base={r.base} tip={r.tip} theme={r.theme} />)}
    </group>
  );
}
