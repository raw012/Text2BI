import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import { GripVertical, MoreHorizontal, TrendingUp } from "lucide-react";
import { api } from "../lib/api";
import type { ChartData, DashboardComponent } from "../types";

interface Props {
  component: DashboardComponent;
  datasetId: number;
  primary: string;
  accent: string;
  selected: boolean;
  onSelect: () => void;
  filters: Record<string, string>;
}

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

export function ChartCard({ component, datasetId, primary, accent, selected, onSelect, filters }: Props) {
  const [data, setData] = useState<ChartData>({});

  useEffect(() => {
    api.query(datasetId, component.query, filters).then(setData).catch(() => setData({ value: 0 }));
  }, [component.query, datasetId, filters]);

  const option = useMemo(() => {
    const categories = data.categories || [];
    const values = data.values || [];
    const common = {
      animationDuration: 700,
      color: [primary, accent, "#8B5CF6", "#F59E0B", "#F97316", "#94A3B8"],
      tooltip: { trigger: "axis", borderWidth: 0, backgroundColor: "#0f172a", textStyle: { color: "#fff" } },
      grid: { left: 8, right: 10, top: 22, bottom: 8, containLabel: true },
    };
    if (component.type === "pie") {
      return {
        ...common,
        tooltip: { trigger: "item" },
        legend: { bottom: 0, icon: "circle", itemWidth: 8, textStyle: { color: "#64748b", fontSize: 10 } },
        series: [{ type: "pie", radius: ["52%", "74%"], center: ["50%", "43%"], label: { show: false }, data: categories.map((name, i) => ({ name, value: values[i] })) }],
      };
    }
    const line = component.type === "line" || component.type === "area";
    return {
      ...common,
      xAxis: { type: "category", data: categories, axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: "#94a3b8", fontSize: 10, interval: 0, rotate: categories.some((x) => x.length > 8) ? 20 : 0 } },
      yAxis: { type: "value", splitLine: { lineStyle: { color: "#eef2f7" } }, axisLabel: { color: "#94a3b8", fontSize: 10 }, axisLine: { show: false } },
      series: [{
        data: values,
        type: line ? "line" : "bar",
        smooth: true,
        barMaxWidth: 28,
        showSymbol: false,
        areaStyle: component.type === "area" ? { opacity: .12 } : undefined,
        lineStyle: { width: 3 },
        itemStyle: { borderRadius: line ? 0 : [5, 5, 0, 0] },
      }],
    };
  }, [data, component.type, primary, accent]);

  const isKpi = component.type === "kpi";
  return (
    <article
      onClick={onSelect}
      className={`group relative rounded-2xl border bg-white transition-all ${selected ? "border-blue-500 ring-2 ring-blue-100 shadow-panel" : "border-slate-200/80 hover:border-slate-300 hover:shadow-panel"}`}
      style={{ gridColumn: `span ${Math.min(12, component.layout.w)}` }}
    >
      <div className="flex items-start justify-between px-5 pt-4">
        <div>
          <p className={`${isKpi ? "text-xs font-semibold uppercase tracking-[.08em] text-slate-500" : "text-[15px] font-semibold text-slate-800"}`}>{component.title}</p>
          {component.subtitle && !isKpi && <p className="mt-0.5 text-xs text-slate-400">{component.subtitle}</p>}
        </div>
        <div className="flex items-center gap-1 text-slate-300 opacity-0 transition group-hover:opacity-100">
          <GripVertical size={15} />
          <MoreHorizontal size={16} />
        </div>
      </div>
      {isKpi ? (
        <div className="flex items-end justify-between px-5 pb-5 pt-4">
          <p className="text-[32px] font-bold tracking-tight text-slate-900">{compact.format(data.value || 0)}</p>
          <span className="mb-1 inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-1 text-[11px] font-semibold text-emerald-600"><TrendingUp size={12} /> Live</span>
        </div>
      ) : (
        <ReactECharts option={option} style={{ height: Math.max(230, component.layout.h * 45) }} opts={{ renderer: "svg" }} />
      )}
    </article>
  );
}
