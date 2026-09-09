import type { SparkPoint } from "@/lib/price-check";

type Tone = "good" | "warn" | "neutral" | "unknown";

const STROKE: Record<Tone, string> = {
  good: "#15803d",
  warn: "#ea580c",
  neutral: "#64748b",
  unknown: "#9aa3af",
};

/**
 * Inline SVG price sparkline. No dependencies. The last point gets a dot so the
 * reader sees where "now" sits inside the 90-day range.
 */
export function Sparkline({
  points,
  tone,
  width = 520,
  height = 64,
}: {
  points: SparkPoint[];
  tone: Tone;
  width?: number;
  height?: number;
}) {
  if (points.length < 2) return null;

  const values = points.map((p) => p.c);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = 4;
  const w = width - pad * 2;
  const h = height - pad * 2;

  const xy = (p: SparkPoint, i: number): [number, number] => {
    const x = pad + (i / (points.length - 1)) * w;
    const y = pad + h - ((p.c - min) / span) * h;
    return [x, y];
  };

  const line = points.map((p, i) => xy(p, i).join(",")).join(" ");
  const [lastX, lastY] = xy(points[points.length - 1], points.length - 1);
  const stroke = STROKE[tone];

  return (
    <svg
      className="sparkline"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label="90-day price trend"
    >
      <polyline
        points={line}
        fill="none"
        stroke={stroke}
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
      <circle cx={lastX} cy={lastY} r={3.5} fill={stroke} />
    </svg>
  );
}
