export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M50 5L90 25V75L50 95L10 75V25L50 5Z"
        stroke="#FFD700"
        strokeWidth="6"
        fill="none"
      />
      <path
        d="M50 20L75 33V67L50 80L25 67V33L50 20Z"
        fill="#FFD700"
        fillOpacity="0.15"
        stroke="#FFD700"
        strokeWidth="3"
      />
      <path
        d="M38 45L48 55L62 38"
        stroke="#10B981"
        strokeWidth="6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
