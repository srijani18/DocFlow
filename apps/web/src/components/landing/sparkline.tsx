/** A decorative trend line for preview stat cards. */
export function Sparkline({ points, id }: { points: number[]; id: string }) {
  const width = 96;
  const height = 40;
  const max = Math.max(...points);
  const min = Math.min(...points);
  const step = width / (points.length - 1);
  const y = (value: number) => height - 4 - ((value - min) / (max - min || 1)) * (height - 8);
  const line = points
    .map((value, index) => `${index === 0 ? "M" : "L"}${index * step},${y(value)}`)
    .join(" ");
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-10 w-24" aria-hidden>
      <defs>
        <linearGradient id={`${id}-stroke`} x1="0" x2="1">
          <stop offset="0%" stopColor="var(--brand-from)" />
          <stop offset="100%" stopColor="var(--brand-to)" />
        </linearGradient>
        <linearGradient id={`${id}-fill`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--brand-via)" stopOpacity="0.18" />
          <stop offset="100%" stopColor="var(--brand-via)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${line} L${width},${height} L0,${height} Z`} fill={`url(#${id}-fill)`} />
      <path
        d={line}
        fill="none"
        stroke={`url(#${id}-stroke)`}
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}
