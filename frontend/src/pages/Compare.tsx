import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import ReactECharts from "echarts-for-react";

import { api, type CrossModelCompareEntry } from "@/api";
import { humanBps, humanIops, humanNs } from "@/lib/format";

type MetricKey =
  | "read_iops"
  | "write_iops"
  | "read_bw_bytes"
  | "write_bw_bytes"
  | "read_clat_mean_ns"
  | "read_clat_p99_ns";

const METRIC_FORMATTERS: Record<MetricKey, (v: number) => string> = {
  read_iops: humanIops,
  write_iops: humanIops,
  read_bw_bytes: humanBps,
  write_bw_bytes: humanBps,
  read_clat_mean_ns: humanNs,
  read_clat_p99_ns: humanNs,
};

const MODEL_PALETTE = [
  "#60a5fa",
  "#f4a340",
  "#4ade80",
  "#c084fc",
  "#f87171",
  "#22d3ee",
  "#facc15",
];

function parseSlugsFromUrl(raw: string | null): string[] {
  if (!raw) return [];
  return raw.split(",").map((s) => s.trim()).filter(Boolean);
}

function ShareCurrentView({ disabled }: { disabled: boolean }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    const url = window.location.href;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      window.prompt("Copy this comparison URL:", url);
    }
  }

  return (
    <button
      onClick={copy}
      disabled={disabled}
      title="Copy a shareable URL that recreates this comparison view"
      style={{ fontSize: 12 }}
    >
      {copied ? "Copied!" : "Share view"}
    </button>
  );
}

export default function Compare() {
  const { t } = useTranslation();
  const [search, setSearch] = useSearchParams();
  const urlSlugs = parseSlugsFromUrl(search.get("models"));
  const urlPhase = search.get("phase") || "";
  const urlMetric = (search.get("metric") as MetricKey) || "read_iops";

  const [selected, setSelected] = useState<string[]>(urlSlugs);
  const [phaseName, setPhaseName] = useState<string>(urlPhase);
  const [metric, setMetric] = useState<MetricKey>(urlMetric);

  useEffect(() => {
    const params = new URLSearchParams();
    if (selected.length) params.set("models", selected.join(","));
    if (phaseName) params.set("phase", phaseName);
    params.set("metric", metric);
    setSearch(params, { replace: true });
  }, [selected, phaseName, metric, setSearch]);

  const modelsQ = useQuery({ queryKey: ["models"], queryFn: api.listModels });

  const commonPhasesQ = useQuery({
    queryKey: ["common-phases", selected],
    queryFn: () => api.commonPhasesAcrossModels(selected),
    enabled: selected.length > 0,
  });

  useEffect(() => {
    const phases = commonPhasesQ.data?.phase_names ?? [];
    if (phases.length === 0) {
      if (phaseName) setPhaseName("");
      return;
    }
    if (!phases.includes(phaseName)) setPhaseName(phases[0]);
  }, [commonPhasesQ.data, phaseName]);

  const compareQ = useQuery({
    queryKey: ["compare", selected, phaseName],
    queryFn: () => api.compareAcrossModels(selected, phaseName),
    enabled: selected.length > 0 && !!phaseName,
  });

  function toggleSlug(slug: string) {
    setSelected((prev) =>
      prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug],
    );
  }

  const chartOption = useMemo(() => {
    const data = compareQ.data;
    if (!data || data.models.length === 0) return null;
    const labels = data.models.map(
      (m) => `${m.brand ?? "?"}\n${m.model ?? m.slug}`,
    );
    const formatter = METRIC_FORMATTERS[metric];

    const meanValues = data.models.map((m) => {
      const s = m.summary[metric];
      return s ? s.mean : 0;
    });
    const bestValues = data.models.map((m) => {
      const s = m.summary[metric];
      return s ? s.best : 0;
    });
    const scatterPoints: { value: [number, number]; itemStyle: { color: string } }[] = [];
    data.models.forEach((m, idx) => {
      const color = MODEL_PALETTE[idx % MODEL_PALETTE.length];
      for (const sample of m.samples) {
        const v = (sample as unknown as Record<string, number | null>)[metric];
        if (v == null) continue;
        scatterPoints.push({ value: [idx, v], itemStyle: { color } });
      }
    });

    return {
      animation: false,
      textStyle: { fontFamily: "inherit" },
      grid: { top: 50, right: 24, bottom: 70, left: 90 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: "#111a2e",
        borderColor: "#233256",
        textStyle: { color: "#e2e8f0" },
        valueFormatter: (v: number) => formatter(v),
      },
      legend: {
        top: 10,
        textStyle: { color: "#94a3b8" },
        data: [t("compare.mean"), t("compare.best"), t("compare.sample")],
      },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { lineStyle: { color: "#233256" } },
        axisLabel: { color: "#94a3b8", interval: 0, fontSize: 10 },
      },
      yAxis: {
        type: "value",
        axisLine: { lineStyle: { color: "#233256" } },
        axisLabel: { color: "#94a3b8", formatter },
        splitLine: { lineStyle: { color: "#1a2440" } },
      },
      series: [
        {
          name: t("compare.mean"),
          type: "bar",
          data: meanValues,
          itemStyle: { color: "rgba(96,165,250,0.55)" },
        },
        {
          name: t("compare.best"),
          type: "bar",
          data: bestValues,
          itemStyle: { color: "rgba(244,163,64,0.55)" },
        },
        {
          name: t("compare.sample"),
          type: "scatter",
          data: scatterPoints,
          symbolSize: 9,
          z: 10,
        },
      ],
    };
  }, [compareQ.data, metric, t]);

  const testableModels = modelsQ.data ?? [];
  const commonPhases = commonPhasesQ.data?.phase_names ?? [];

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <div>
          <h2>{t("compare.title")}</h2>
          <div className="dim" style={{ fontSize: 12 }}>
            {t("compare.subtitle")}
          </div>
        </div>
        <ShareCurrentView disabled={selected.length === 0} />
      </div>

      <div className="card">
        <h3>{t("compare.pickModels")}</h3>
        {testableModels.length === 0 ? (
          <div className="dim">{t("common.loading")}</div>
        ) : (
          <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
            {testableModels.map((m) => {
              const active = selected.includes(m.slug);
              const disabled = !active && m.run_count === 0;
              return (
                <button
                  key={m.slug}
                  onClick={() => !disabled && toggleSlug(m.slug)}
                  className={active ? "btn-primary" : ""}
                  disabled={disabled}
                  title={disabled ? t("compare.noRuns") : undefined}
                  style={{ fontSize: 12 }}
                >
                  <span style={{ fontWeight: 600 }}>{m.brand}</span>{" "}
                  <span className="mono">{m.model}</span>{" "}
                  <span className="dim" style={{ fontSize: 10 }}>
                    ({m.run_count})
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {selected.length >= 1 && (
        <div className="card">
          <div className="row" style={{ alignItems: "center", gap: 16 }}>
            <div className="col">
              <label className="dim" style={{ fontSize: 12 }}>
                {t("compare.pickPhase")}
              </label>
              <select value={phaseName} onChange={(e) => setPhaseName(e.target.value)}>
                <option value="">
                  {commonPhases.length === 0
                    ? t("compare.noCommonPhases")
                    : "—"}
                </option>
                {commonPhases.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            <div className="col">
              <label className="dim" style={{ fontSize: 12 }}>
                {t("compare.pickMetric")}
              </label>
              <select
                value={metric}
                onChange={(e) => setMetric(e.target.value as MetricKey)}
              >
                <option value="read_iops">{t("runs.readIops")}</option>
                <option value="write_iops">{t("runs.writeIops")}</option>
                <option value="read_bw_bytes">{t("runs.readBw")}</option>
                <option value="write_bw_bytes">{t("runs.writeBw")}</option>
                <option value="read_clat_mean_ns">
                  {t("runs.readIops")} · {t("runs.meanLat")}
                </option>
                <option value="read_clat_p99_ns">
                  {t("runs.readIops")} · {t("runs.p99Lat")}
                </option>
              </select>
            </div>
          </div>
        </div>
      )}

      {compareQ.isError && (
        <div className="card" style={{ background: "#3b1820", border: "1px solid #7f1d1d" }}>
          <h3>Could not load comparison</h3>
          <div className="dim" style={{ fontSize: 12 }}>
            {String((compareQ.error as Error)?.message ?? compareQ.error)}
          </div>
        </div>
      )}

      {compareQ.data && chartOption && (
        <div className="card">
          <ReactECharts
            style={{ height: 380 }}
            option={chartOption}
            notMerge
            lazyUpdate
          />
        </div>
      )}

      {compareQ.data && (
        <div className="card">
          <h3>{t("compare.summary")}</h3>
          <table>
            <thead>
              <tr>
                <th>{t("compare.model")}</th>
                <th>{t("compare.runs")}</th>
                <th>{t("compare.mean")}</th>
                <th>{t("compare.median")}</th>
                <th>{t("compare.best")}</th>
              </tr>
            </thead>
            <tbody>
              {compareQ.data.models.map((m: CrossModelCompareEntry) => {
                const s = m.summary[metric];
                const fmt = METRIC_FORMATTERS[metric];
                return (
                  <tr key={m.slug}>
                    <td>
                      <span className="badge">{m.brand ?? "?"}</span>{" "}
                      <span className="mono">{m.model ?? m.slug}</span>
                    </td>
                    <td className="mono">{m.summary.sample_count}</td>
                    <td className="mono">{s ? fmt(s.mean) : "—"}</td>
                    <td className="mono">{s ? fmt(s.median) : "—"}</td>
                    <td className="mono">{s ? fmt(s.best) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
