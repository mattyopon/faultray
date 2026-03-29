let _logoCounter = 0;

export function Logo({ size = 28 }: { size?: number }) {
  const id = `logo-${++_logoCounter}`;

  // Small size (< 64px): simplified design — fault line + background only
  if (size < 64) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 100 100"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <rect width="100" height="100" rx="20" fill="#0a0e1a" />
        {/* Grid lines — thicker for small size */}
        <g opacity="0.2">
          <line x1="25" y1="0" x2="25" y2="100" stroke="#e2e8f0" strokeWidth="2" />
          <line x1="50" y1="0" x2="50" y2="100" stroke="#e2e8f0" strokeWidth="2" />
          <line x1="75" y1="0" x2="75" y2="100" stroke="#e2e8f0" strokeWidth="2" />
          <line x1="0" y1="25" x2="100" y2="25" stroke="#e2e8f0" strokeWidth="2" />
          <line x1="0" y1="50" x2="100" y2="50" stroke="#e2e8f0" strokeWidth="2" />
          <line x1="0" y1="75" x2="100" y2="75" stroke="#e2e8f0" strokeWidth="2" />
        </g>
        {/* Fault line glow */}
        <line x1="0" y1="65" x2="65" y2="0" stroke="#FFD700" strokeWidth="12" opacity="0.15" strokeLinecap="round" />
        {/* Fault line */}
        <line x1="0" y1="65" x2="65" y2="0" stroke="#FFD700" strokeWidth="4" strokeLinecap="round" />
        {/* Ray */}
        <line x1="32" y1="32" x2="85" y2="15" stroke="#FFD700" strokeWidth="2" opacity="0.4" strokeLinecap="round" />
      </svg>
    );
  }

  // Full detail for larger sizes
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 512 512"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <clipPath id={`upper-${id}`}>
          <polygon points="0,0 512,0 307,205 0,512" />
        </clipPath>
        <clipPath id={`lower-${id}`}>
          <polygon points="307,0 512,0 512,512 0,512 0,307" />
        </clipPath>
      </defs>

      <rect width="512" height="512" rx="96" fill="#0a0e1a" />

      <g clipPath={`url(#upper-${id})`} opacity="0.18">
        <line x1="64"  y1="0" x2="64"  y2="512" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="128" y1="0" x2="128" y2="512" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="192" y1="0" x2="192" y2="512" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="256" y1="0" x2="256" y2="512" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="320" y1="0" x2="320" y2="512" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="384" y1="0" x2="384" y2="512" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="448" y1="0" x2="448" y2="512" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="0" y1="64"  x2="512" y2="64"  stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="0" y1="128" x2="512" y2="128" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="0" y1="192" x2="512" y2="192" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="0" y1="256" x2="512" y2="256" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="0" y1="320" x2="512" y2="320" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="0" y1="384" x2="512" y2="384" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="0" y1="448" x2="512" y2="448" stroke="#e2e8f0" strokeWidth="1.5" />
      </g>

      <g clipPath={`url(#lower-${id})`} opacity="0.18" transform="translate(20, 12)">
        <line x1="64"  y1="0" x2="64"  y2="512" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="128" y1="0" x2="128" y2="512" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="192" y1="0" x2="192" y2="512" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="256" y1="0" x2="256" y2="512" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="320" y1="0" x2="320" y2="512" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="384" y1="0" x2="384" y2="512" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="448" y1="0" x2="448" y2="512" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="0" y1="64"  x2="512" y2="64"  stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="0" y1="128" x2="512" y2="128" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="0" y1="192" x2="512" y2="192" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="0" y1="256" x2="512" y2="256" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="0" y1="320" x2="512" y2="320" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="0" y1="384" x2="512" y2="384" stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1="0" y1="448" x2="512" y2="448" stroke="#e2e8f0" strokeWidth="1.5" />
      </g>

      <line x1="0" y1="307" x2="307" y2="0" stroke="#FFD700" strokeWidth="28" opacity="0.12" strokeLinecap="round" />
      <line x1="0" y1="307" x2="307" y2="0" stroke="#FFD700" strokeWidth="14" opacity="0.25" strokeLinecap="round" />
      <line x1="0" y1="307" x2="307" y2="0" stroke="#FFD700" strokeWidth="5" strokeLinecap="round" />

      <line x1="153" y1="153" x2="420" y2="60" stroke="#FFD700" strokeWidth="2.5" opacity="0.35" strokeLinecap="round" />
      <line x1="153" y1="153" x2="90" y2="420" stroke="#FFD700" strokeWidth="2.5" opacity="0.35" strokeLinecap="round" />
    </svg>
  );
}
