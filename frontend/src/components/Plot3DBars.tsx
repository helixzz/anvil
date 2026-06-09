import { useEffect, useRef } from "react";

let plotlyPromise: Promise<any> | null = null;

function loadPlotly(): Promise<any> {
  if (!plotlyPromise) {
    plotlyPromise = import("plotly.js-dist-min").then((m) => (m as any).default ?? m);
  }
  return plotlyPromise;
}

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

export default function Plot3DBars({
  xLabels, yLabels, xAxisName, yAxisName, zAxisName, devices, formatter, height = 480,
}: Plot3DBarsProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    let cancelled = false;
    let plotlyMod: any = null;

    loadPlotly().then((Plotly) => {
      if (cancelled || !node) return;
      plotlyMod = Plotly;

      const traces: any[] = [];
      const allValues: number[] = [];
      devices.forEach((d) => d.matrix.forEach((row) => row.forEach((v) => { if (v != null && v > 0) allValues.push(v); })));
      const maxVal = allValues.length ? Math.max(...allValues) : 1;

      devices.forEach((dev) => {
        const xs: number[] = [];
        const ys: number[] = [];
        const zsBase: number[] = [];
        const zsTop: number[] = [];
        const customdata: string[] = [];

        for (let xi = 0; xi < xLabels.length; xi++) {
          for (let yi = 0; yi < yLabels.length; yi++) {
            const val = dev.matrix[xi]?.[yi];
            if (val == null || val <= 0) continue;
            xs.push(xi);
            ys.push(yi);
            zsBase.push(0);
            zsTop.push(val);
            customdata.push(`<b>${dev.name}</b><br>${xAxisName}: ${xLabels[xi]}<br>${yAxisName}: ${yLabels[yi]}<br>${zAxisName}: ${formatter(val)}`);
          }
        }

        traces.push({
          type: "scatter3d",
          mode: "markers",
          name: dev.name,
          x: xs,
          y: ys,
          z: zsTop,
          marker: {
            color: dev.color,
            size: 8,
            symbol: "square",
            line: { color: "#fff", width: 0.5 },
            opacity: 0.95,
          },
          customdata,
          hovertemplate: "%{customdata}<extra></extra>",
        });

        const stemX: (number | null)[] = [];
        const stemY: (number | null)[] = [];
        const stemZ: (number | null)[] = [];
        for (let i = 0; i < xs.length; i++) {
          stemX.push(xs[i], xs[i], null);
          stemY.push(ys[i], ys[i], null);
          stemZ.push(zsBase[i], zsTop[i], null);
        }

        traces.push({
          type: "scatter3d",
          mode: "lines",
          name: dev.name,
          x: stemX,
          y: stemY,
          z: stemZ,
          line: { color: dev.color, width: 6 },
          showlegend: false,
          hoverinfo: "skip",
        });
      });

      const layout: any = {
        autosize: true,
        height,
        margin: { l: 10, r: 10, t: 10, b: 10 },
        paper_bgcolor: "rgba(0,0,0,0)",
        font: { color: "#cbd5e1", size: 11 },
        legend: {
          orientation: "h",
          y: -0.05,
          x: 0.5,
          xanchor: "center",
          font: { color: "#cbd5e1", size: 11 },
          bgcolor: "rgba(0,0,0,0)",
        },
        scene: {
          bgcolor: "rgba(0,0,0,0)",
          xaxis: {
            title: { text: xAxisName, font: { color: "#cbd5e1", size: 12 } },
            tickmode: "array",
            tickvals: xLabels.map((_, i) => i),
            ticktext: xLabels,
            color: "#94a3b8",
            gridcolor: "#1e293b",
            zerolinecolor: "#334155",
            backgroundcolor: "rgba(15,23,42,0.4)",
            showbackground: true,
          },
          yaxis: {
            title: { text: yAxisName, font: { color: "#cbd5e1", size: 12 } },
            tickmode: "array",
            tickvals: yLabels.map((_, i) => i),
            ticktext: yLabels,
            color: "#94a3b8",
            gridcolor: "#1e293b",
            zerolinecolor: "#334155",
            backgroundcolor: "rgba(15,23,42,0.4)",
            showbackground: true,
          },
          zaxis: {
            title: { text: zAxisName, font: { color: "#cbd5e1", size: 12 } },
            color: "#94a3b8",
            gridcolor: "#1e293b",
            zerolinecolor: "#334155",
            backgroundcolor: "rgba(15,23,42,0.4)",
            showbackground: true,
            tickformat: "~s",
            range: [0, maxVal * 1.1],
          },
          camera: {
            eye: { x: 1.7, y: -1.5, z: 1.1 },
          },
          aspectmode: "manual",
          aspectratio: { x: 1.4, y: 1.0, z: 0.9 },
        },
      };

      const config: any = {
        displayModeBar: true,
        displaylogo: false,
        responsive: true,
        modeBarButtonsToRemove: ["sendDataToCloud", "lasso2d", "select2d"],
      };

      Plotly.react(node, traces, layout, config);
    });

    return () => {
      cancelled = true;
      if (plotlyMod && node) {
        try { plotlyMod.purge(node); } catch { void 0; }
      }
    };
  }, [xLabels, yLabels, xAxisName, yAxisName, zAxisName, devices, formatter, height]);

  return <div ref={ref} style={{ width: "100%", height }} />;
}
