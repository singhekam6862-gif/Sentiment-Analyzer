"use client";

import React, { useSyncExternalStore } from "react";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { AspectScore } from "@/types/analysis";
import { PRODUCT_THEMES } from "@/lib/productThemes";
import { Activity } from "lucide-react";

interface AspectRadarChartProps {
  series: { name: string; scores: AspectScore[] }[];
}

const ASPECT_LABELS: Record<string, string> = {
  sound_quality: "Sound Quality",
  anc_noise_cancellation: "ANC / Noise",
  mic_call_quality: "Mic & Calls",
  battery_life: "Battery Life",
  comfort_build: "Comfort & Build",
  value_for_money: "Value for Money",
};

// React 19 safe client-mount detection avoiding set-state-in-effect
function useIsClient() {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false
  );
}

export function AspectRadarChart({ series }: AspectRadarChartProps) {
  const mounted = useIsClient();
  const isComparing = series.length > 1;

  // Recharts wants one row per aspect with one numeric key per product (s0, s1).
  const chartData = series[0].scores.map((item) => {
    const row: Record<string, string | number> = { aspect: ASPECT_LABELS[item.aspect] || item.aspect };
    series.forEach((s, i) => {
      row[`s${i}`] = s.scores.find((a) => a.aspect === item.aspect)?.score ?? 50;
    });
    return row;
  });

  return (
    <div className="w-full max-w-5xl mx-auto px-4 mb-6">
      <div className="rounded-2xl bg-slate-900/70 border border-slate-800 p-5 md:p-6 backdrop-blur-sm shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 pb-4 mb-5 border-b border-slate-800">
          <div>
            <h2 className="text-base md:text-lg font-bold text-white flex items-center gap-2">
              <Activity className="w-5 h-5 text-emerald-400" />
              <span>Aspect-Based Sentiment Analysis (ABSA)</span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              6-pillar hardware evaluation (0–100 score). Logistics complaints excluded from product scoring.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs">
            {series.map((s, i) => (
              <span key={`${s.name}-${i}`} className={`flex items-center gap-1.5 font-semibold ${PRODUCT_THEMES[i].text}`}>
                <span className={`w-2.5 h-2.5 rounded-full ${PRODUCT_THEMES[i].dot}`} />
                {s.name}
              </span>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
          {/* Radar Chart (Recharts) */}
          <div className="lg:col-span-6 w-full h-[320px] md:h-[360px] flex items-center justify-center relative">
            {!mounted ? (
              <div className="flex items-center justify-center w-full h-full text-slate-500 text-sm">
                Loading radar visualization...
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart cx="50%" cy="50%" outerRadius="75%" data={chartData}>
                  <PolarGrid stroke="#334155" strokeDasharray="3 3" />
                  <PolarAngleAxis
                    dataKey="aspect"
                    tick={{ fill: "#94a3b8", fontSize: 11, fontWeight: 600 }}
                  />
                  <PolarRadiusAxis
                    angle={30}
                    domain={[0, 100]}
                    stroke="#475569"
                    tick={{ fill: "#64748b", fontSize: 10 }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0f172a",
                      borderColor: "#334155",
                      borderRadius: "12px",
                      color: "#f8fafc",
                      fontSize: "12px",
                      boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.5)",
                    }}
                    formatter={(value: unknown, name: unknown) => [`${String(value ?? 0)} / 100`, String(name)]}
                  />
                  {series.map((s, i) => (
                    <Radar
                      key={`${s.name}-${i}`}
                      name={s.name}
                      dataKey={`s${i}`}
                      stroke={PRODUCT_THEMES[i].hex}
                      fill={PRODUCT_THEMES[i].hex}
                      fillOpacity={0.25}
                      strokeWidth={2}
                    />
                  ))}
                </RadarChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Aspect Breakdown Cards with Summaries */}
          <div className="lg:col-span-6 space-y-3">
            {series[0].scores.map((item) => {
              const label = ASPECT_LABELS[item.aspect] || item.aspect;
              const perProduct = series.map((s) => s.scores.find((a) => a.aspect === item.aspect));
              // Badges describe the primary product; in compare mode the bars show the gap.
              const isHigh = item.score >= 70;
              const isLow = item.score < 50;

              return (
                <div
                  key={item.aspect}
                  className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 hover:border-slate-700 transition-all"
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-semibold text-slate-200 text-xs flex items-center gap-1.5">
                      {label}
                      {!isComparing && isHigh && (
                        <span className="text-[10px] text-emerald-400 font-mono bg-emerald-500/10 px-1.5 py-0.2 rounded border border-emerald-500/20">
                          Strong
                        </span>
                      )}
                      {!isComparing && isLow && (
                        <span className="text-[10px] text-rose-400 font-mono bg-rose-500/10 px-1.5 py-0.2 rounded border border-rose-500/20">
                          Weak
                        </span>
                      )}
                    </span>
                    <div className="flex items-center gap-3 text-xs font-mono font-bold">
                      {perProduct.map((a, i) => (
                        <span key={i} className={PRODUCT_THEMES[i].text} title={series[i].name}>
                          {a?.score ?? 50}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-1 mb-2">
                    {perProduct.map((a, i) => (
                      <div key={i} className="h-1.5 w-full bg-slate-900 rounded-full overflow-hidden">
                        <div
                          style={{ width: `${a?.score ?? 50}%` }}
                          className={`h-full rounded-full transition-all duration-500 ${PRODUCT_THEMES[i].bar}`}
                        />
                      </div>
                    ))}
                  </div>

                  {perProduct.map((a, i) => (
                    <p key={i} className="text-[11px] text-slate-400 leading-relaxed italic">
                      {isComparing && <span className={`not-italic font-semibold ${PRODUCT_THEMES[i].text}`}>{series[i].name}: </span>}
                      &ldquo;{a?.summary}&rdquo;
                    </p>
                  ))}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
