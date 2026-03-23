/**
 * Reusable SVG sparkline component for compact metric visualization.
 *
 * Renders a polyline with optional gradient fill area beneath the curve.
 * Designed for embedding within metric cards at small dimensions where
 * axis labels would be illegible and wasteful. The sparkline communicates
 * trend direction and volatility at a glance — the only two properties
 * that matter when monitoring 15+ metrics simultaneously.
 */

interface SparklineProps {
  /** Ordered numeric values to plot. Minimum 2 points required. */
  data: number[];
  /** SVG viewport width in pixels. */
  width?: number;
  /** SVG viewport height in pixels. */
  height?: number;
  /** Stroke color. Accepts CSS custom properties. */
  color?: string;
  /** Whether to render a gradient fill beneath the polyline. */
  showArea?: boolean;
}

export function Sparkline({
  data,
  width = 120,
  height = 32,
  color = "var(--fizzbuzz-400)",
  showArea = true,
}: SparklineProps) {
  if (data.length < 2) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const padding = 2;

  const points = data
    .map((value, index) => {
      const x = (index / (data.length - 1)) * width;
      const y =
        height - ((value - min) / range) * (height - padding * 2) - padding;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  // Unique gradient ID to avoid collisions when multiple sparklines render
  const gradientId = `sparkline-fill-${Math.random().toString(36).slice(2, 8)}`;

  const areaPoints = `0,${height} ${points} ${width},${height}`;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="overflow-visible"
      aria-label="Metric sparkline"
    >
      {showArea && (
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.25" />
            <stop offset="100%" stopColor={color} stopOpacity="0.02" />
          </linearGradient>
        </defs>
      )}
      {showArea && <polygon points={areaPoints} fill={`url(#${gradientId})`} />}
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
