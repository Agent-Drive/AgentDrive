export function Logo({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 100 100"
      fill="currentColor"
      aria-hidden
    >
      <path
        fillRule="evenodd"
        d="M50 6 88.11 28v44L50 94 11.89 72V28Z M24.85 35.48 50 50v22L24.85 57.48Z"
      />
    </svg>
  );
}
