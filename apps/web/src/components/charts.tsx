"use client";
import { useState } from "react";
import type { Traffic } from "@/lib/types";
import { number } from "@/lib/api";

function line(values: number[], width: number, height: number, max: number) {
  return values.map((value, index) => `${index === 0 ? "M" : "L"} ${index * width / Math.max(1, values.length - 1)} ${height - value / (max || 1) * (height - 12)}`).join(" ");
}
export function Sparkline({ values, color = "#7c7ad0", id }: { values: number[]; color?: string; id: string }) {
  if (!values.length) return <span className="muted">No samples</span>;
  const d = line(values, 110, 34, Math.max(...values) * 1.1);
  return <svg className="sparkline" viewBox="0 0 110 38" aria-hidden="true"><defs><linearGradient id={`spark-${id}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity=".17" /><stop offset="100%" stopColor={color} stopOpacity="0" /></linearGradient></defs><path d={`${d} L110 38 L0 38 Z`} fill={`url(#spark-${id})`} /><path d={d} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" /></svg>;
}
export function TrafficChart({ data }: { data: Traffic[] }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const width = 800, height = 174;
  const max = Math.max(10, ...data.map(item => item.requests)) * 1.15;
  const requests = line(data.map(item => item.requests), width, height, max);
  const errors = line(data.map(item => item.errors), width, height, max);
  const selected = hovered !== null ? data[hovered] : null;
  const ticks = Array.from({ length: 5 }, (_, index) => max * (4 - index) / 4);
  const positions = data.length > 1 ? [0, Math.floor((data.length - 1) / 4), Math.floor((data.length - 1) / 2), Math.floor((data.length - 1) * 3 / 4), data.length - 1] : [0];
  const timeLabel = (value: string) => new Date(value).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
  return <div className="traffic-chart">
    <div className="chart-y">{ticks.map((tick, index) => <span key={index}>{number(tick)}</span>)}</div>
    <div className="chart-plot">
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="API request volume and errors over the selected period" onMouseLeave={() => setHovered(null)}>
        <defs><linearGradient id="trafficFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#8981d8" stopOpacity=".17" /><stop offset="100%" stopColor="#8981d8" stopOpacity=".01" /></linearGradient></defs>
        {ticks.map((_, index) => <line key={index} x1="0" y1={index * height / 4} x2={width} y2={index * height / 4} stroke="#eceef2" strokeDasharray="4 5" />)}
        {data.length > 0 && <><path d={`${requests} L${width} ${height} L0 ${height} Z`} fill="url(#trafficFill)" /><path d={requests} fill="none" stroke="#847acb" strokeWidth="2.3" vectorEffect="non-scaling-stroke" strokeLinejoin="round" /><path d={errors} fill="none" stroke="#e5a178" strokeWidth="1.8" vectorEffect="non-scaling-stroke" /></>}
        {data.map((item, index) => <rect key={item.time} x={index * width / data.length} y="0" width={width / data.length + 1} height={height} fill="transparent" onMouseEnter={() => setHovered(index)} />)}
        {hovered !== null && <line x1={hovered * width / Math.max(1, data.length - 1)} y1="0" x2={hovered * width / Math.max(1, data.length - 1)} y2={height} stroke="#b1adc7" strokeDasharray="3 3" />}
      </svg>
      {selected && <div className="chart-tooltip" style={{ left: `${Math.min(76, hovered! / Math.max(1, data.length - 1) * 100)}%` }}><strong>{timeLabel(selected.time)}</strong><span>{number(selected.requests)} requests</span><span>{number(selected.errors)} errors</span></div>}
      <div className="chart-x">{positions.map((index, i) => <span key={i}>{data[index] ? timeLabel(data[index].time) : "—"}</span>)}</div>
    </div>
  </div>;
}
export function HealthRing({ up, total }: { up: number; total: number }) {
  const percent = total ? up / total : 0;
  return <div className="health-ring"><svg viewBox="0 0 150 150" aria-label={`${up} of ${total} monitors operational`} role="img"><circle cx="75" cy="75" r="61" fill="none" stroke="#f1ece5" strokeWidth="11" /><circle cx="75" cy="75" r="61" fill="none" stroke="#94c8ad" strokeWidth="11" strokeDasharray={`${percent * 383.27} 383.27`} strokeLinecap="round" transform="rotate(-90 75 75)" /></svg><div><strong>{up}<span>/{total}</span></strong><small>monitors healthy</small></div></div>;
}
