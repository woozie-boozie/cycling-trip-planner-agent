"use client";

interface ElevationSparklineProps {
  /** Normalised elevation points 0..1 — typically 24-48 samples. */
  points: number[];
  /** Pixel width of the SVG. Defaults to scale to container. */
  width?: number;
  /** Pixel height of the SVG. */
  height?: number;
  /** Stroke + fill colour (CSS colour or var). Defaults to primary. */
  color?: string;
  /** Decorative — not interactive, no aria-label needed unless asked. */
  className?: string;
}

/**
 * Compact area-chart sparkline of an elevation profile.
 *
 *   ELEVATION                                    ↑ 1620 m
 *   _/\__/\___/\___                              ←—— this part
 *
 * Renders as inline SVG so it scales crisply at any size and styles via
 * CSS / theme tokens. Pure presentation — caller supplies normalised
 * points in [0, 1]. We pad the bottom 6% so the line never glues to the
 * baseline.
 */
export function ElevationSparkline({
  points,
  width = 200,
  height = 36,
  color = "var(--primary)",
  className,
}: ElevationSparklineProps) {
  if (points.length < 2) return null;

  const PAD_BOTTOM = 0.06;
  const PAD_TOP = 0.10;
  const usable = height * (1 - PAD_BOTTOM - PAD_TOP);

  const stepX = width / (points.length - 1);
  const coords = points.map((p, i) => {
    const x = i * stepX;
    const y = height - height * PAD_BOTTOM - p * usable;
    return [x, y] as const;
  });

  // Smooth-ish line — straight segments are fine for sparkline density.
  const linePath = coords
    .map(([x, y], i) => `${i === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`)
    .join(" ");

  // Closed area path — line + drop to baseline + close.
  const areaPath = `${linePath} L ${width.toFixed(2)} ${height.toFixed(2)} L 0 ${height.toFixed(2)} Z`;

  const gradId = `elev-grad-${stableSparkId(points)}`;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={className}
      aria-hidden
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradId})`} />
      <path
        d={linePath}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Cheap stable id from the points themselves so two sparklines on the
 *  same page don't share a gradient def by accident. */
function stableSparkId(points: number[]): string {
  // Sum + length is enough to differentiate the three corridors here.
  const sum = points.reduce((acc, p) => acc + p, 0);
  return `${points.length}-${sum.toFixed(3).replace(".", "")}`;
}
