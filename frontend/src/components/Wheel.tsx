// The Carter mark — a 10-spoke wheel on a 0 0 48 48 grid (design spec §9).
// Recolour by setting `color` (rim + spokes + hub fill): gold on ink, or ink
// on gold. Stroke weights are absolute at the 48-unit viewBox and scale cleanly.

export function Wheel({
  color = '#FFCD41',
  size = 24,
  className = '',
}: {
  color?: string
  size?: number
  className?: string
}) {
  return (
    <svg
      viewBox="0 0 48 48"
      width={size}
      height={size}
      fill="none"
      stroke={color}
      aria-label="Carter"
      className={className}
    >
      <circle cx="24" cy="24" r="20" strokeWidth="2.6" />
      <path
        strokeWidth="2.2"
        d="M30 24 L40.5 24  M28.9 27.5 L37.4 33.7
           M25.9 29.7 L29.1 39.7  M22.1 29.7 L18.9 39.7
           M19.1 27.5 L10.7 33.7  M18 24 L7.5 24
           M19.1 20.5 L10.7 14.3  M22.1 18.3 L18.9 8.3
           M25.9 18.3 L29.1 8.3   M28.9 20.5 L37.4 14.3"
      />
      <circle cx="24" cy="24" r="6" strokeWidth="1.6" />
      <circle cx="24" cy="24" r="3" fill={color} stroke="none" />
    </svg>
  )
}

// The mark badge: 40×40, radius 9, ink ground, gold wheel (sidebar + favicon).
export function MarkBadge({ size = 40 }: { size?: number }) {
  return (
    <div
      className="flex shrink-0 items-center justify-center rounded-[9px] bg-ink"
      style={{ width: size, height: size }}
    >
      <Wheel color="#FFCD41" size={size * 0.6} />
    </div>
  )
}
