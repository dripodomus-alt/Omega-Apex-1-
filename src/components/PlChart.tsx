import React, { useRef, useState, useEffect } from "react";

interface PlChartProps {
  pnlHistory: number[];
}

export default function PlChart({ pnlHistory }: PlChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 300, height: 160 });

  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      for (let entry of entries) {
        const { width, height } = entry.contentRect;
        setDimensions({
          width: width || 300,
          height: height || 160,
        });
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  const data = pnlHistory.length ? pnlHistory : Array(30).fill(8424);
  const maxVal = Math.max(...data) * 1.001;
  const minVal = Math.min(...data) * 0.999;
  const range = maxVal - minVal || 10;

  const { width, height } = dimensions;
  const paddingX = 40;
  const paddingY = 20;
  const chartWidth = width - paddingX - 10;
  const chartHeight = height - paddingY - 10;

  // Generate cubic coordinate points
  const points = data.map((val, idx) => {
    const x = paddingX + (idx / Math.max(1, data.length - 1)) * chartWidth;
    const y =
      paddingY +
      chartHeight -
      (range ? ((val - minVal) / range) * chartHeight : 0);
    return { x, y };
  });

  // SVG Path generator
  let pathD = "";
  let areaD = "";

  if (points.length > 0) {
    pathD = `M ${points[0].x} ${points[0].y}`;
    for (let i = 1; i < points.length; i++) {
      const p = points[i];
      const prev = points[i - 1];
      // Generate nice bezier coordinates
      const cpX1 = prev.x + (p.x - prev.x) / 2;
      const cpY1 = prev.y;
      const cpX2 = prev.x + (p.x - prev.x) / 2;
      const cpY2 = p.y;
      pathD += ` C ${cpX1} ${cpY1}, ${cpX2} ${cpY2}, ${p.x} ${p.y}`;
    }
    areaD = `${pathD} L ${points[points.length - 1].x} ${height - 10} L ${points[0].x} ${height - 10} Z`;
  }

  // Generate vertical grid lines
  const gridLines = 5;
  const grds = Array.from({ length: gridLines }).map((_, i) => {
    const ration = i / (gridLines - 1);
    const x = paddingX + ration * chartWidth;
    return x;
  });

  // Generate y-ticks
  const yTicks = 4;
  const ticks = Array.from({ length: yTicks }).map((_, i) => {
    const ration = i / (yTicks - 1);
    const val = maxVal - ration * range;
    const y = paddingY + ration * chartHeight;
    return { val, y };
  });

  return (
    <div
      ref={containerRef}
      className="w-full h-full min-h-[140px] relative select-none"
    >
      <svg className="w-full h-full overflow-visible">
        <defs>
          <linearGradient id="pnlGlow" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#00f5a0" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#00f5a0" stopOpacity="0.00" />
          </linearGradient>
        </defs>

        {/* Horizontal gridlines */}
        {ticks.map((t, idx) => (
          <line
            key={`h-grid-${idx}`}
            x1={paddingX}
            y1={t.y}
            x2={width - 10}
            y2={t.y}
            stroke="rgba(255,255,255,0.024)"
            strokeWidth={1}
            strokeDasharray="4 4"
          />
        ))}

        {/* Vertical gridlines */}
        {grds.map((x, idx) => (
          <line
            key={`v-grid-${idx}`}
            x1={x}
            y1={paddingY}
            x2={x}
            y2={height - 10}
            stroke="rgba(255,255,255,0.015)"
            strokeWidth={1}
          />
        ))}

        {/* Path Fill block */}
        {areaD && <path d={areaD} fill="url(#pnlGlow)" />}

        {/* Trajectory Stroke */}
        {pathD && (
          <path
            d={pathD}
            fill="none"
            stroke="#00f5a0"
            strokeWidth={1.5}
            className="drop-shadow-[0_0_6px_rgba(0,245,160,0.4)]"
          />
        )}

        {/* Interactive glowing end node */}
        {points.length > 0 && (
          <circle
            cx={points[points.length - 1].x}
            cy={points[points.length - 1].y}
            r={3}
            fill="#00f5a0"
            className="animate-pulse shadow-glow"
          />
        )}

        {/* Y Axis text label markers */}
        {ticks.map((t, idx) => (
          <text
            key={`tick-lbl-${idx}`}
            x={paddingX - 8}
            y={t.y + 3}
            fill="rgba(255,255,255,0.3)"
            fontSize={7.5}
            fontFamily="DM Mono, monospace"
            textAnchor="end"
          >
            ${t.val.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </text>
        ))}
      </svg>
    </div>
  );
}
