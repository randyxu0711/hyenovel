const STEM = "M24 12H42V68L33 90L24 68Z";
const TIP = "M24 68H42L33 90Z";
const LEAD = "M30 82H36L33 90Z";
const ARCH = "M42 46C46 38 53 33 62 33C73 33 79 41 79 53V66C79 71 81 73 84 73L86 84C73 87 64 80 64 68V55C64 49 62 46 58 46C52 46 47 51 42 58Z";

export default function Logo({ size = 22 }: { size?: number }) {
  return (
    <svg className="logo" viewBox="0 0 100 100" width={size} height={size} aria-hidden="true">
      <path fill="currentColor" d={STEM} />
      <path fill="var(--dash-paper)" opacity=".45" d={TIP} />
      <path fill="var(--dash-accent)" d={LEAD} />
      <path fill="currentColor" d={ARCH} />
      <circle fill="var(--dash-accent)" cx="88" cy="79" r="7" />
    </svg>
  );
}
