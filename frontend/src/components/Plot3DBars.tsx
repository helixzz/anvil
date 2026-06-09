import { useMemo, useRef, useState, useEffect } from "react";

interface Plot3DBarsProps {
  xLabels: string[];
  yLabels: string[];
  xAxisName: string;
  yAxisName: string;
  zAxisName: string;
  devices: {
    name: string;
    color: string;
    matrix: (number | null)[][];
  }[];
  formatter: (v: number) => string;
  height?: number;
}

interface Vec3 { x: number; y: number; z: number; }
interface Vec2 { x: number; y: number; }
interface HoverInfo {
  deviceName: string;
  xv: string;
  yv: string;
  value: number;
}
interface Quad {
  pts: Vec2[];
  depth: number;
  fill: string;
  stroke: string;
  opacity: number;
  hover?: HoverInfo;
}

const ROT_X_DEG_DEFAULT = 28;
const ROT_Y_DEG_DEFAULT = 35;
const PADDING = 64;

function rotateY(v: Vec3, sin: number, cos: number): Vec3 {
  return { x: v.x * cos + v.z * sin, y: v.y, z: -v.x * sin + v.z * cos };
}
function rotateX(v: Vec3, sin: number, cos: number): Vec3 {
  return { x: v.x, y: v.y * cos - v.z * sin, z: v.y * sin + v.z * cos };
}
function projectVec(v: Vec3, scale: number, cx: number, cy: number): Vec2 {
  return { x: cx + v.x * scale, y: cy - v.y * scale };
}
function lighten(hex: string, factor: number): string {
  const m = hex.match(/^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
  if (!m) return hex;
  const clamp = (n: number) => Math.max(0, Math.min(255, Math.round(n)));
  const r = clamp(parseInt(m[1], 16) * factor);
  const g = clamp(parseInt(m[2], 16) * factor);
  const b = clamp(parseInt(m[3], 16) * factor);
  return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${b.toString(16).padStart(2, "0")}`;
}

export default function Plot3DBars({
  xLabels, yLabels, xAxisName, yAxisName, zAxisName, devices, formatter, height = 480,
}: Plot3DBarsProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(800);
  const [rotX, setRotX] = useState(ROT_X_DEG_DEFAULT);
  const [rotY, setRotY] = useState(ROT_Y_DEG_DEFAULT);
  const [hover, setHover] = useState<{ x: number; y: number; info: HoverInfo } | null>(null);
  const dragging = useRef<{ x: number; y: number; rotX: number; rotY: number } | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        const w = e.contentRect.width;
        if (w > 0) setWidth(w);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const scene = useMemo(
    () => buildScene(devices, xLabels, yLabels, rotX, rotY, width, height, zAxisName, xAxisName, yAxisName, formatter),
    [devices, xLabels, yLabels, rotX, rotY, width, height, zAxisName, xAxisName, yAxisName, formatter],
  );

  function onPointerDown(e: React.PointerEvent) {
    (e.target as Element).setPointerCapture(e.pointerId);
    dragging.current = { x: e.clientX, y: e.clientY, rotX, rotY };
  }
  function onPointerMove(e: React.PointerEvent) {
    if (!dragging.current) return;
    const dx = e.clientX - dragging.current.x;
    const dy = e.clientY - dragging.current.y;
    setRotY(dragging.current.rotY + dx * 0.5);
    setRotX(Math.max(5, Math.min(85, dragging.current.rotX - dy * 0.5)));
  }
  function onPointerUp(e: React.PointerEvent) {
    try { (e.target as Element).releasePointerCapture(e.pointerId); } catch { void 0; }
    dragging.current = null;
  }

  return (
    <div ref={containerRef} style={{ width: "100%", position: "relative" }}>
      <div className="row" style={{ gap: 12, fontSize: 11, color: "#94a3b8", marginBottom: 8, alignItems: "center" }}>
        <span>↻ {Math.round(rotY)}°</span>
        <span>↕ {Math.round(rotX)}°</span>
        <button
          onClick={() => { setRotX(ROT_X_DEG_DEFAULT); setRotY(ROT_Y_DEG_DEFAULT); }}
          style={{ fontSize: 11, padding: "2px 8px" }}
        >
          Reset view
        </button>
        <span className="dim" style={{ marginLeft: "auto", fontSize: 10 }}>Drag to rotate</span>
      </div>
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        style={{ display: "block", cursor: dragging.current ? "grabbing" : "grab", userSelect: "none", touchAction: "none" }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        {scene.floor && (
          <polygon
            points={scene.floor.pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")}
            fill={scene.floor.fill}
            stroke={scene.floor.stroke}
            strokeWidth={0.5}
            fillOpacity={scene.floor.opacity}
          />
        )}
        {scene.axes.map((line, i) => (
          <line key={`axis-${i}`} x1={line.a.x} y1={line.a.y} x2={line.b.x} y2={line.b.y} stroke="#334155" strokeWidth={1} />
        ))}
        {scene.surfaces.map((q, i) => (
          <polygon
            key={i}
            points={q.pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")}
            fill={q.fill}
            stroke={q.stroke}
            strokeWidth={0.5}
            fillOpacity={q.opacity}
            onMouseEnter={
              q.hover
                ? (e) => {
                    const rect = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                    setHover({ x: e.clientX - rect.left, y: e.clientY - rect.top, info: q.hover! });
                  }
                : undefined
            }
            onMouseLeave={q.hover ? () => setHover(null) : undefined}
          />
        ))}
        {scene.ticks.map((tk, i) => (
          <text
            key={`tick-${i}`}
            x={tk.pos.x}
            y={tk.pos.y}
            fill={tk.bold ? "#cbd5e1" : "#94a3b8"}
            fontSize={tk.bold ? 12 : 10}
            fontWeight={tk.bold ? 500 : 400}
            textAnchor={tk.anchor}
            dominantBaseline={tk.baseline}
          >
            {tk.text}
          </text>
        ))}
      </svg>
      {hover && (
        <div
          style={{
            position: "absolute",
            left: hover.x + 12,
            top: hover.y + 12,
            background: "#111a2e",
            border: "1px solid #233256",
            borderRadius: 4,
            padding: "6px 10px",
            color: "#e2e8f0",
            fontSize: 11,
            pointerEvents: "none",
            zIndex: 10,
            whiteSpace: "nowrap",
          }}
        >
          <div style={{ fontWeight: 600 }}>{hover.info.deviceName}</div>
          <div>{xAxisName}: {hover.info.xv}</div>
          <div>{yAxisName}: {hover.info.yv}</div>
          <div>{zAxisName}: {formatter(hover.info.value)}</div>
        </div>
      )}
      <div className="row" style={{ gap: 16, fontSize: 11, marginTop: 8, flexWrap: "wrap", justifyContent: "center" }}>
        {devices.map((d) => (
          <span key={d.name} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 16, height: 10, background: d.color, opacity: 0.78, display: "inline-block", borderRadius: 2 }} />
            <span style={{ color: "#cbd5e1" }}>{d.name}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

interface SceneTick {
  pos: Vec2;
  text: string;
  anchor: "start" | "middle" | "end";
  baseline: "auto" | "middle" | "hanging";
  bold: boolean;
}
interface SceneAxis { a: Vec2; b: Vec2; }
interface Scene {
  floor: Quad | null;
  surfaces: Quad[];
  axes: SceneAxis[];
  ticks: SceneTick[];
}

function buildScene(
  devices: Plot3DBarsProps["devices"],
  xLabels: string[],
  yLabels: string[],
  rotXDeg: number,
  rotYDeg: number,
  width: number,
  height: number,
  zAxisName: string,
  xAxisName: string,
  yAxisName: string,
  formatter: (v: number) => string,
): Scene {
  const nx = xLabels.length;
  const ny = yLabels.length;
  if (nx < 1 || ny < 1) return { floor: null, surfaces: [], axes: [], ticks: [] };

  let zMax = 0;
  for (const dev of devices) {
    for (const row of dev.matrix) {
      for (const v of row) {
        if (typeof v === "number" && v > zMax) zMax = v;
      }
    }
  }
  if (zMax <= 0) zMax = 1;

  const cubeX = 1.6;
  const cubeY = 1.0;
  const cubeZ = 1.0;
  const insetX = nx > 1 ? cubeX * 0.08 : 0;
  const insetY = ny > 1 ? cubeY * 0.08 : 0;
  const stepX = nx > 1 ? (cubeX - 2 * insetX) / (nx - 1) : 0;
  const stepY = ny > 1 ? (cubeY - 2 * insetY) / (ny - 1) : 0;

  const rotXRad = (rotXDeg * Math.PI) / 180;
  const rotYRad = (rotYDeg * Math.PI) / 180;
  const sinX = Math.sin(rotXRad);
  const cosX = Math.cos(rotXRad);
  const sinY = Math.sin(rotYRad);
  const cosY = Math.cos(rotYRad);

  function transform(v: Vec3): Vec3 {
    const v1 = rotateY(v, sinY, cosY);
    return rotateX(v1, sinX, cosX);
  }

  const corners: Vec3[] = [];
  for (let i = -1; i <= 1; i += 2) {
    for (let j = -1; j <= 1; j += 2) {
      for (let k = -1; k <= 1; k += 2) {
        corners.push({ x: (i * cubeX) / 2, y: (j * cubeZ) / 2, z: (k * cubeY) / 2 });
      }
    }
  }
  const transformedCorners = corners.map(transform);
  let minTx = Infinity, maxTx = -Infinity, minTy = Infinity, maxTy = -Infinity;
  for (const c of transformedCorners) {
    if (c.x < minTx) minTx = c.x;
    if (c.x > maxTx) maxTx = c.x;
    if (c.y < minTy) minTy = c.y;
    if (c.y > maxTy) maxTy = c.y;
  }
  const dataWidth = maxTx - minTx;
  const dataHeight = maxTy - minTy;
  const availW = Math.max(width - 2 * PADDING, 100);
  const availH = Math.max(height - 2 * PADDING, 100);
  const scale = Math.min(availW / Math.max(dataWidth, 0.01), availH / Math.max(dataHeight, 0.01));
  const cx = width / 2 - ((minTx + maxTx) / 2) * scale;
  const cy = height / 2 + ((minTy + maxTy) / 2) * scale;

  function dataToWorld(xi: number, yi: number, val: number): Vec3 {
    return {
      x: -cubeX / 2 + insetX + xi * stepX,
      y: -cubeZ / 2 + (val / zMax) * cubeZ,
      z: -cubeY / 2 + insetY + yi * stepY,
    };
  }
  function wp(v: Vec3): { p: Vec2; t: Vec3 } {
    const t = transform(v);
    return { p: projectVec(t, scale, cx, cy), t };
  }

  const quads: Quad[] = [];
  const axes: SceneAxis[] = [];
  const ticks: SceneTick[] = [];

  const baseCorners = [
    { x: -cubeX / 2, y: -cubeZ / 2, z: -cubeY / 2 },
    { x: cubeX / 2, y: -cubeZ / 2, z: -cubeY / 2 },
    { x: cubeX / 2, y: -cubeZ / 2, z: cubeY / 2 },
    { x: -cubeX / 2, y: -cubeZ / 2, z: cubeY / 2 },
  ];
  const basePts = baseCorners.map(wp);
  const floor: Quad = {
    pts: basePts.map((b) => b.p),
    depth: (basePts[0].t.z + basePts[1].t.z + basePts[2].t.z + basePts[3].t.z) / 4,
    fill: "#0c1426",
    stroke: "#1e293b",
    opacity: 0.85,
  };

  for (let xi = 0; xi < nx; xi++) {
    const xWorld = -cubeX / 2 + insetX + xi * stepX;
    const a = wp({ x: xWorld, y: -cubeZ / 2, z: -cubeY / 2 });
    const b = wp({ x: xWorld, y: -cubeZ / 2, z: cubeY / 2 });
    axes.push({ a: a.p, b: b.p });
  }
  for (let yi = 0; yi < ny; yi++) {
    const zWorld = -cubeY / 2 + insetY + yi * stepY;
    const a = wp({ x: -cubeX / 2, y: -cubeZ / 2, z: zWorld });
    const b = wp({ x: cubeX / 2, y: -cubeZ / 2, z: zWorld });
    axes.push({ a: a.p, b: b.p });
  }
  const zTicks = 5;
  for (let i = 0; i <= zTicks; i++) {
    const yWorld = -cubeZ / 2 + (i / zTicks) * cubeZ;
    const a = wp({ x: -cubeX / 2, y: yWorld, z: -cubeY / 2 });
    const b = wp({ x: -cubeX / 2, y: yWorld, z: cubeY / 2 });
    axes.push({ a: a.p, b: b.p });
    const tickValue = (i / zTicks) * zMax;
    ticks.push({ pos: { x: a.p.x - 6, y: a.p.y }, text: formatter(tickValue), anchor: "end", baseline: "middle", bold: false });
  }

  for (let xi = 0; xi < nx; xi++) {
    const xWorld = -cubeX / 2 + insetX + xi * stepX;
    const p = wp({ x: xWorld, y: -cubeZ / 2, z: cubeY / 2 + 0.05 });
    ticks.push({ pos: { x: p.p.x, y: p.p.y + 14 }, text: xLabels[xi], anchor: "middle", baseline: "hanging", bold: false });
  }
  for (let yi = 0; yi < ny; yi++) {
    const zWorld = -cubeY / 2 + insetY + yi * stepY;
    const p = wp({ x: cubeX / 2 + 0.05, y: -cubeZ / 2, z: zWorld });
    ticks.push({ pos: { x: p.p.x + 6, y: p.p.y }, text: yLabels[yi], anchor: "start", baseline: "middle", bold: false });
  }
  const xLabelPos = wp({ x: 0, y: -cubeZ / 2, z: cubeY / 2 + 0.25 });
  ticks.push({ pos: { x: xLabelPos.p.x, y: xLabelPos.p.y + 32 }, text: xAxisName, anchor: "middle", baseline: "hanging", bold: true });
  const yLabelPos = wp({ x: cubeX / 2 + 0.3, y: -cubeZ / 2, z: 0 });
  ticks.push({ pos: { x: yLabelPos.p.x + 16, y: yLabelPos.p.y }, text: yAxisName, anchor: "start", baseline: "middle", bold: true });
  const zLabelPos = wp({ x: -cubeX / 2, y: cubeZ / 2 + 0.05, z: -cubeY / 2 });
  ticks.push({ pos: { x: zLabelPos.p.x - 12, y: zLabelPos.p.y - 8 }, text: zAxisName, anchor: "end", baseline: "auto", bold: true });

  for (const dev of devices) {
    const surfaceQuads = buildSurfaceQuads(dev, xLabels, yLabels, dataToWorld, transform, scale, cx, cy);
    quads.push(...surfaceQuads);
  }

  quads.sort((a, b) => a.depth - b.depth);

  return { floor, surfaces: quads, axes, ticks };
}

function buildSurfaceQuads(
  dev: Plot3DBarsProps["devices"][0],
  xLabels: string[],
  yLabels: string[],
  dataToWorld: (xi: number, yi: number, val: number) => Vec3,
  transform: (v: Vec3) => Vec3,
  scale: number,
  cx: number,
  cy: number,
): Quad[] {
  const out: Quad[] = [];
  const nx = xLabels.length;
  const ny = yLabels.length;
  const baseFill = dev.color;
  const sideFill = lighten(dev.color, 0.55);

  function project4(corners: Vec3[]): { pts: Vec2[]; tCorners: Vec3[] } {
    const tCorners = corners.map(transform);
    const pts = tCorners.map((t) => projectVec(t, scale, cx, cy));
    return { pts, tCorners };
  }

  for (let xi = 0; xi < nx - 1; xi++) {
    for (let yi = 0; yi < ny - 1; yi++) {
      const v00 = dev.matrix[xi]?.[yi];
      const v10 = dev.matrix[xi + 1]?.[yi];
      const v01 = dev.matrix[xi]?.[yi + 1];
      const v11 = dev.matrix[xi + 1]?.[yi + 1];
      if (v00 == null || v10 == null || v01 == null || v11 == null) continue;

      const corners = [
        dataToWorld(xi, yi, v00),
        dataToWorld(xi + 1, yi, v10),
        dataToWorld(xi + 1, yi + 1, v11),
        dataToWorld(xi, yi + 1, v01),
      ];
      const { pts, tCorners } = project4(corners);

      const ax = tCorners[1].x - tCorners[0].x;
      const ay = tCorners[1].y - tCorners[0].y;
      const az = tCorners[1].z - tCorners[0].z;
      const bx = tCorners[3].x - tCorners[0].x;
      const by = tCorners[3].y - tCorners[0].y;
      const bz = tCorners[3].z - tCorners[0].z;
      const ny_ = az * bx - ax * bz;
      const nlen = Math.sqrt((ay * bz - az * by) ** 2 + ny_ ** 2 + (ax * by - ay * bx) ** 2) || 1;
      const lightDot = Math.max(0.7, Math.min(1.15, (ny_ / nlen) * 0.4 + 0.85));
      const fill = lighten(baseFill, lightDot);
      const depth = Math.min(tCorners[0].z, tCorners[1].z, tCorners[2].z, tCorners[3].z);

      out.push({
        pts,
        depth,
        fill,
        stroke: lighten(baseFill, 1.3),
        opacity: 0.92,
        hover: { deviceName: dev.name, xv: xLabels[xi], yv: yLabels[yi], value: v00 },
      });
    }
  }

  for (let xi = 0; xi < nx - 1; xi++) {
    const v0 = dev.matrix[xi]?.[0];
    const v1 = dev.matrix[xi + 1]?.[0];
    if (v0 == null || v1 == null) continue;
    const corners = [
      dataToWorld(xi, 0, v0),
      dataToWorld(xi + 1, 0, v1),
      dataToWorld(xi + 1, 0, 0),
      dataToWorld(xi, 0, 0),
    ];
    const { pts, tCorners } = project4(corners);
    const depth = Math.min(tCorners[0].z, tCorners[1].z, tCorners[2].z, tCorners[3].z);
    out.push({ pts, depth, fill: sideFill, stroke: sideFill, opacity: 0.7 });
  }
  for (let yi = 0; yi < ny - 1; yi++) {
    const v0 = dev.matrix[0]?.[yi];
    const v1 = dev.matrix[0]?.[yi + 1];
    if (v0 == null || v1 == null) continue;
    const corners = [
      dataToWorld(0, yi, v0),
      dataToWorld(0, yi + 1, v1),
      dataToWorld(0, yi + 1, 0),
      dataToWorld(0, yi, 0),
    ];
    const { pts, tCorners } = project4(corners);
    const depth = Math.min(tCorners[0].z, tCorners[1].z, tCorners[2].z, tCorners[3].z);
    out.push({ pts, depth, fill: sideFill, stroke: sideFill, opacity: 0.7 });
  }

  return out;
}
