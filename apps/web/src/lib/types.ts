export interface Monitor {
  id: string; name: string; url: string; method: string; interval_seconds: number;
  timeout_seconds: number; expected_status: number; latency_threshold_ms: number;
  enabled: boolean; status: string; last_latency: number | null; last_checked: string | null; uptime: number; is_demo?: boolean;
}
export interface LogEntry {
  id: string; service: string; level: string; message: string; trace_id?: string;
  metadata: Record<string, unknown>; created_at: string;
}
export interface Analysis {
  summary: string; probable_cause: string; confidence: number; evidence: string[];
  recommended_actions: string[]; source: string; generated_at: string;
}
export interface TimelineEntry { id: string; kind: string; message: string; created_at: string }
export interface Incident {
  id: string; title: string; service: string; severity: string; status: string; summary: string;
  created_at: string; updated_at: string; resolved_at?: string | null;
  timeline?: TimelineEntry[]; analysis?: Analysis | null;
}
export interface Deployment {
  id: string; service: string; version: string; environment: string; status: string;
  commit_sha?: string; created_at: string;
}
export interface Audit { id: string; action: string; actor: string; resource: string; detail: string; created_at: string }
export interface Traffic { time: string; requests: number; errors: number; latency: number }
export interface Service {
  id: string; name: string; status: string; uptime: number; latency: number | null; error_rate: number; requests: number;
}
export interface Overview {
  stats: { requests_24h: number; error_rate: number; p95_latency: number; uptime: number; active_incidents: number; monitors_up: number; monitors_total: number };
  traffic: Traffic[]; services: Service[]; recent_incidents: Incident[]; recent_deployments: Deployment[]; activity: Audit[]; sampled?: boolean;
}
export interface Settings {
  ai_enabled: boolean; demo_mode: boolean; version: string; ai_provider: string;
  redis_configured: boolean; alerts_enabled: boolean; monitor_allow_private_networks: boolean;
  retention_days: number; error_threshold: number; error_window_seconds: number;
}
