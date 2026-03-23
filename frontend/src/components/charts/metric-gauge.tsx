/**
 * Circular gauge component for percentage-based metrics (0-100%).
 *
 * The gauge color transitions from green through yellow to red as the
 * value approaches critical thresholds. This color mapping follows
 * standard SRE conventions: green indicates healthy operation, yellow
 * signals degraded performance requiring attention, and red demands
 * immediate incident response.
 *
 * Used primarily for SLA error budget remaining, compliance audit scores,
 * and cache hit ratio visualization where percentage context is essential.
 */

interface MetricGaugeProps {
  /** Value to display, clamped to 0-100. */
  value: number;
  /** Diameter of the gauge in pixels. */
  size?: number;
  /** Stroke width of the gauge arc. */
  strokeWidth?: number;
  /** Label displayed below the percentage. */
  label?: string;
  /** If true, lower values are considered better (inverts color mapping). */
  invertColor?: boolean;
}

function getGaugeColor(value: number, invert: boolean): string {
  const v = invert ? 100 - value : value;
  if (v >= 80) return "var(--fizz-400)";
  if (v >= 50) return "var(--fizzbuzz-gold, #f59e0b)";
  return "#ef4444";
}

export function MetricGauge({
  value,
  size = 96,
  strokeWidth = 8,
  label,
  invertColor = false,
}: MetricGaugeProps) {
  const clamped = Math.max(0, Math.min(100, value));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - clamped / 100);
  const color = getGaugeColor(clamped, invertColor);
  const center = size / 2;

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Background track */}
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke="var(--panel-700)"
          strokeWidth={strokeWidth}
        />
        {/* Value arc — rotated -90deg so 0% starts at 12 o'clock */}
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          transform={`rotate(-90 ${center} ${center})`}
          className="transition-all duration-500"
        />
        {/* Center value */}
        <text
          x={center}
          y={center}
          textAnchor="middle"
          dominantBaseline="central"
          className="text-sm font-mono font-semibold fill-panel-50"
        >
          {clamped.toFixed(1)}%
        </text>
      </svg>
      {label && (
        <span className="text-[10px] text-panel-400 text-center leading-tight">
          {label}
        </span>
      )}
    </div>
  );
}
