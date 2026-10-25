/**
 * CareRelay brand mark: a shield (coverage/insurance) with a pulse/check
 * line (clinical + deterministic verification) cut through it. Mirrors
 * public/pulse.svg (the favicon) so the mark is consistent everywhere.
 */
export function BrandMark({ size = 32, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="brandmark-g1" x1="8" y1="4" x2="56" y2="60" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#3fb6a6" />
          <stop offset="1" stopColor="#0f3f3a" />
        </linearGradient>
        <linearGradient id="brandmark-g2" x1="16" y1="10" x2="48" y2="10" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.55" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d="M32 4 L54 12 V30 C54 46 44 56 32 60 C20 56 10 46 10 30 V12 Z" fill="url(#brandmark-g1)" />
      <path d="M32 4 L54 12 V30 C54 46 44 56 32 60" fill="url(#brandmark-g2)" />
      <path
        d="M18 33h7l3.5-9 6 18 4-13h3.5l3-6h7.5"
        stroke="#ffffff"
        strokeWidth="3.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
}
