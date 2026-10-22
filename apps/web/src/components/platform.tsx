"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  Activity, ArrowDownRight, ArrowLeft, ArrowRight, Bell, BookOpen, Box, Check,
  ChevronDown, ChevronRight, CircleHelp, Clock3, Code2, ExternalLink, FileText,
  GitBranch, LayoutDashboard, ListFilter, Menu, MonitorDot, Network, Plus,
  Radio, RefreshCw, Search, Settings2, ShieldCheck, Sparkles, TriangleAlert, X, Zap,
} from "lucide-react";
import { ago, api, errorMessage, number } from "@/lib/api";
import { useResource } from "@/lib/use-resource";
import type { Overview, Settings } from "@/lib/types";
import { HealthRing, Sparkline, TrafficChart } from "./charts";
import { Badge, Empty, ErrorState, Loading, Modal, Toast } from "./ui";
import { MonitorsView, LogsView, IncidentsView, IncidentDetail, DeploymentsView, IntelligenceView, AuditView, SettingsView } from "./views";

const navigation = [
  { href: "/", name: "Overview", icon: LayoutDashboard },
  { href: "/monitors", name: "API monitors", icon: MonitorDot },
  { href: "/logs", name: "Log explorer", icon: FileText },
  { href: "/incidents", name: "Incidents", icon: TriangleAlert },
  { href: "/intelligence", name: "Intelligence", icon: Sparkles },
  { href: "/deployments", name: "Deployments", icon: GitBranch },
];
export type Notify = (message: string, kind?: "success" | "error") => void;
export type ViewProps = { refreshKey: number; notify: Notify };

export function PageHeading({ eyebrow, title, description, children }: { eyebrow?: string; title: string; description: string; children?: ReactNode }) {
  return <div className="page-heading"><div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h1>{title}</h1><p>{description}</p></div><div className="heading-actions">{children}</div></div>;
}

export function Platform() {
  const pathname = usePathname();
  const [refreshKey, setRefreshKey] = useState(0);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [toast, setToast] = useState<{ message: string; kind: "success" | "error" } | null>(null);
  const { data: settings } = useResource<Settings>("/settings", refreshKey, 60000);
  const { data: overview, error: connectionError } = useResource<Overview>("/overview", refreshKey);
  const notify = useCallback<Notify>((message, kind = "success") => setToast({ message, kind }), []);
  const closeToast = useCallback(() => setToast(null), []);
  useEffect(() => {
    const onConnection = () => setRefreshKey(value => value + 1);
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") { event.preventDefault(); setSearchOpen(value => !value); }
      if (event.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("tracehunt-connection", onConnection);
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("tracehunt-connection", onConnection); window.removeEventListener("keydown", onKey); };
  }, []);
  useEffect(() => { setMobileOpen(false); }, [pathname]);
  const current = navigation.find(item => item.href === "/" ? pathname === "/" : pathname.startsWith(item.href));
  const props = { refreshKey, notify };
  const pathParts = pathname.split("/").filter(Boolean);
  let content: ReactNode;
  if (pathname === "/") content = <OverviewView {...props} />;
  else if (pathname === "/monitors") content = <MonitorsView {...props} />;
  else if (pathname === "/logs") content = <LogsView {...props} />;
  else if (pathname === "/incidents") content = <IncidentsView {...props} />;
  else if (pathParts[0] === "incidents" && pathParts.length === 2) content = <IncidentDetail {...props} id={pathParts[1]} />;
  else if (pathname === "/deployments") content = <DeploymentsView {...props} />;
  else if (pathname === "/intelligence") content = <IntelligenceView {...props} />;
  else if (pathname === "/activity") content = <AuditView {...props} />;
  else if (pathname === "/settings") content = <SettingsView {...props} />;
  else content = <Empty title="This page is off the map" detail="Return to your workspace to find your services, logs, and incidents." action={<Link className="button primary" href="/">Back to overview</Link>} />;

  return <div className="app-shell">
    <a href="#main-content" className="skip-link">Skip to content</a>
    {mobileOpen && <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
    <aside className={`sidebar ${mobileOpen ? "is-open" : ""}`} aria-label="Main navigation">
      <Link href="/" className="brand"><span className="brand-icon"><Activity size={25} strokeWidth={2.2} /></span><span>tracehunt<span className="brand-ai">AI</span></span></Link>
      <button className="workspace-switch" onClick={() => setHelpOpen(true)}><span className="workspace-avatar">T</span><span><strong>TraceHunt workspace</strong><small>Engineering</small></span><ChevronDown size={15} /></button>
      <span className="nav-label">WORKSPACE</span>
      <nav>{navigation.map(item => <Link key={item.href} href={item.href} className={`nav-item ${current?.href === item.href ? "active" : ""}`} aria-current={current?.href === item.href ? "page" : undefined}><item.icon size={18} /><span>{item.name}</span>{item.href === "/incidents" && !!overview?.stats.active_incidents && <span className="nav-count">{overview.stats.active_incidents}</span>}{item.href === "/intelligence" && <span className="nav-new">AI</span>}</Link>)}</nav>
      <span className="nav-label second-label">MANAGE</span>
      <nav><Link href="/activity" className={`nav-item ${pathname === "/activity" ? "active" : ""}`} aria-current={pathname === "/activity" ? "page" : undefined}><Activity size={18} /><span>Activity log</span></Link><Link href="/settings" className={`nav-item ${pathname === "/settings" ? "active" : ""}`} aria-current={pathname === "/settings" ? "page" : undefined}><Settings2 size={18} /><span>Settings</span></Link></nav>
      <div className="sidebar-bottom"><div className="signal-card"><span className="signal-icon"><Sparkles size={17} /></span><strong>A little clarity. A lot less noise.</strong><p>Connect the dots between your logs, releases, and incidents.</p><Link href="/intelligence">Explore intelligence <ArrowRight size={14} /></Link></div><button className="help-button" onClick={() => setHelpOpen(true)}><CircleHelp size={17} />Help & getting started<ExternalLink size={13} /></button><div className="profile"><span className="profile-avatar">TH</span><span><strong>Workspace operator</strong><small>{settings?.demo_mode ? "Demo workspace" : "Local workspace"}</small></span><span className="online-dot" /></div></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={21} /></button><span>Workspace</span><ChevronRight size={13} /><strong>{current?.name || (pathname === "/settings" ? "Settings" : pathname === "/activity" ? "Activity log" : "Page")}</strong></div><div className="topbar-actions"><button className="global-search" onClick={() => setSearchOpen(true)}><Search size={15} /><span>Search workspace</span><kbd>Ctrl K</kbd></button><span className={`connection-status ${connectionError ? "disconnected" : ""}`}><span />{connectionError ? "Disconnected" : overview ? "Connected" : "Connecting"}</span><span className="topbar-divider" /><Link href="/incidents" className="notification-button icon-button" aria-label={`${overview?.stats.active_incidents || 0} active incidents`}><Bell size={19} />{!!overview?.stats.active_incidents && <i />}</Link><Link href="/settings" className="top-avatar" aria-label="Workspace settings">TH</Link></div></header>
      <main id="main-content" className="main-content" key={pathname}>{content}</main>
      <footer className="app-footer"><span><Activity size={13} /> TraceHunt AI <span className="footer-separator">/</span> A clearer view of your systems.</span><span>{settings?.demo_mode ? "Synthetic demo data" : "Your connected workspace"}<span className="footer-separator">·</span> v{settings?.version || "1.0.0"}</span></footer>
    </div>
    {toast && <Toast {...toast} onClose={closeToast} />}
    {searchOpen && <SearchDialog onClose={() => setSearchOpen(false)} />}
    {helpOpen && <Modal title="A clearer view starts here" description="Your observability workspace, from the first signal to the next step." onClose={() => setHelpOpen(false)}><div className="help-steps"><div><MonitorDot /><span><strong>1. Connect a service</strong><p>Create an HTTP monitor and start collecting structured logs from your application.</p></span></div><div><TriangleAlert /><span><strong>2. Follow the signal</strong><p>The worker checks endpoints and opens incidents when errors cross your configured threshold.</p></span></div><div><Sparkles /><span><strong>3. Investigate with evidence</strong><p>Open an incident to correlate logs and releases, review a hypothesis, and record its resolution.</p></span></div></div><div className="notice"><BookOpen size={18} /><p>This is a single-workspace installation. Connection credentials and runtime information are available in Settings. Demo records are synthetic and labeled.</p></div><div className="modal-actions"><Link href="/settings" className="button secondary" onClick={() => setHelpOpen(false)}>Connection settings</Link><Link href="/monitors" className="button primary" onClick={() => setHelpOpen(false)}>Explore monitors <ArrowRight size={15} /></Link></div></Modal>}
  </div>;
}

function SearchDialog({ onClose }: { onClose: () => void }) {
  const [query, setQuery] = useState("");
  const router = useRouter();
  const pages = navigation.filter(item => item.name.toLowerCase().includes(query.toLowerCase()));
  function submit(event: FormEvent) { event.preventDefault(); router.push(`/logs?search=${encodeURIComponent(query)}`); onClose(); }
  return <Modal title="Search your workspace" onClose={onClose}><form onSubmit={submit} className="command-search"><Search size={18} /><input autoFocus value={query} onChange={event => setQuery(event.target.value)} placeholder="Find a page or search log messages…" aria-label="Workspace search" /></form><div className="command-results"><span className="eyebrow">JUMP TO</span>{pages.map(item => <Link href={item.href} key={item.href} onClick={onClose}><item.icon size={18} /><span>{item.name}</span><ArrowRight size={15} /></Link>)}{query && <Link href={`/logs?search=${encodeURIComponent(query)}`} onClick={onClose}><Search size={18} /><span>Search logs for “{query}”</span><ArrowRight size={15} /></Link>}{!query && <p className="muted">Tip: use Ctrl K to open this menu from anywhere.</p>}</div></Modal>;
}

function OverviewView({ refreshKey }: ViewProps) {
  const [hours, setHours] = useState("24");
  const { data, error, loading, refreshing, reload } = useResource<Overview>(`/overview?hours=${hours}`, refreshKey);
  const activeIncidents = data?.recent_incidents.filter(item => item.status !== "resolved") || [];
  const highlighted = activeIncidents.find(item => item.analysis) || activeIncidents[0];
  return <>
    <PageHeading eyebrow="YOUR SYSTEMS, AT A GLANCE" title="Overview" description="A little less noise. A clearer picture of what matters."><span className="live-label"><Radio size={14} />Auto refresh · 30s</span><select aria-label="Overview time range" className="select compact" value={hours} onChange={event => setHours(event.target.value)}><option value="1">Last hour</option><option value="6">Last 6 hours</option><option value="24">Last 24 hours</option><option value="168">Last 7 days</option></select><button className="button secondary square" title="Refresh overview" aria-label="Refresh overview" disabled={refreshing} onClick={() => void reload()}><RefreshCw size={16} className={refreshing ? "spin" : ""} /></button></PageHeading>
    {error && <ErrorState message={error} retry={reload} />}
    {loading && <Loading />}
    {data && <>
      <div className="workspace-status"><span className={`status-orb ${data.stats.active_incidents ? "attention" : ""}`}><Activity size={17} /></span><div><strong>{data.stats.active_incidents ? "Your systems are running. A few things need a closer look." : "Looking good. Your systems are in the clear."}</strong><span>{data.stats.monitors_up} of {data.stats.monitors_total} monitors operational<span className="inline-dot">·</span>{data.stats.active_incidents} active {data.stats.active_incidents === 1 ? "incident" : "incidents"}</span></div><Link href="/incidents">View incidents <ArrowRight size={15} /></Link></div>
      <div className="stats-grid">
        <Metric label="Log events" value={number(data.stats.requests_24h)} icon={<Network size={17} />} detail={`In the last ${hours === "168" ? "7 days" : `${hours} hours`}`} values={data.traffic.map(item => item.requests)} color="#8b80cf" />
        <Metric label="Error rate" value={`${data.stats.error_rate}%`} icon={<TriangleAlert size={17} />} detail="Errors across ingested events" values={data.traffic.map(item => item.errors)} color="#dca17e" />
        <Metric label="P95 latency" value={number(data.stats.p95_latency)} unit="ms" icon={<Zap size={17} />} detail="95th percentile response time" values={data.traffic.map(item => item.latency)} color="#79a4b4" />
        <Metric label="Monitor uptime" value={`${data.stats.uptime}%`} icon={<ShieldCheck size={17} />} detail="Successful checks in this period" values={[]} color="#82b89b" />
      </div>
      {data.sampled && <div className="notice"><ListFilter size={17} /><p>Event totals include all records. Trends and service details use a sample of up to 50,000 records.</p></div>}
      <div className="overview-charts"><section className="panel traffic-panel"><div className="panel-heading"><div><h2>Traffic & errors</h2><p>Ingested event volume over time</p></div><div className="chart-legend"><span><i className="purple" />Events</span><span><i className="orange" />Errors</span></div></div>{data.traffic.some(item => item.requests) ? <TrafficChart data={data.traffic} /> : <Empty title="Waiting for your first events" detail="Ingest logs from a service to see traffic trends here." action={<Link className="text-link" href="/logs">Open log explorer <ArrowRight size={14} /></Link>} />}</section><section className="panel health-panel"><div className="panel-heading"><div><h2>Monitor health</h2><p>Right now, across your endpoints</p></div><span className="small-icon"><MonitorDot size={17} /></span></div><HealthRing up={data.stats.monitors_up} total={data.stats.monitors_total} /><div className="health-legend"><span><i className="green" />Operational <strong>{data.stats.monitors_up}</strong></span><span><i className="orange" />Other states <strong>{data.stats.monitors_total - data.stats.monitors_up}</strong></span></div><Link className="panel-bottom-link" href="/monitors">View all monitors <ArrowRight size={14} /></Link></section></div>
      <div className="overview-middle"><section className="panel services-panel"><div className="panel-heading"><div><h2>Service health <span className="count-pill">{data.services.length}</span></h2><p>Every service. One connected view.</p></div><Link className="text-link" href="/monitors">All monitors <ArrowRight size={14} /></Link></div><div className="table-scroll"><table><thead><tr><th>Service</th><th>Status</th><th>Avg. latency</th><th>Uptime</th><th /></tr></thead><tbody>{data.services.slice(0, 6).map((service, index) => <tr key={service.id}><td><Link href={`/logs?service=${encodeURIComponent(service.name)}`} className="service-name"><span className={`service-icon service-${index % 4}`}><Box size={15} /></span>{service.name}</Link></td><td><Badge value={service.status}>{service.status === "up" ? "Operational" : service.status}</Badge></td><td className="mono">{service.latency === null ? "—" : `${number(service.latency)} ms`}</td><td className="mono">{service.uptime}%</td><td><Link href={`/logs?service=${encodeURIComponent(service.name)}`} className="icon-button" aria-label={`Explore ${service.name} logs`}><ChevronRight size={15} /></Link></td></tr>)}</tbody></table></div>{!data.services.length && <Empty title="Your services will appear here" detail="Create a monitor or ingest a log event to get started." />}</section><section className="intelligence-card"><div className="intelligence-top"><span className="intelligence-icon"><Sparkles size={19} /></span><span>TRACEHUNT INTELLIGENCE</span><span className="ai-pill">AI</span></div><h2>From signal to<br />a little more certainty.</h2><p>Connect the dots across your logs, incidents, and deployments.</p>{highlighted ? <div className="insight-preview"><span className="insight-caption"><span className="pulse-dot" />INVESTIGATION SPOTLIGHT</span><strong>{highlighted.service}</strong><p>{highlighted.analysis?.probable_cause || highlighted.title}</p></div> : <div className="insight-preview"><Check size={20} /><strong>No active incidents</strong><p>When a signal needs attention, your investigation starts here.</p></div>}<Link className="button intelligence-button" href={highlighted ? `/incidents/${highlighted.id}` : "/intelligence"}>Explore the evidence <ArrowRight size={15} /></Link></section></div>
      <div className="overview-bottom"><section className="panel"><div className="panel-heading"><div><h2>Active incidents <span className="count-pill warm">{data.stats.active_incidents}</span></h2><p>Keep the important things in focus</p></div><Link className="text-link" href="/incidents">View all <ArrowRight size={14} /></Link></div><div className="incident-list">{activeIncidents.slice(0, 3).map(incident => <Link href={`/incidents/${incident.id}`} key={incident.id} className="incident-row"><span className={`incident-mark ${incident.severity}`}><TriangleAlert size={17} /></span><div><strong>{incident.title}</strong><span>{incident.service}<span className="inline-dot">·</span>{ago(incident.created_at)}</span></div><Badge value={incident.status} /><ChevronRight size={14} /></Link>)}</div>{!activeIncidents.length && <Empty title="A quiet incident queue" detail="No active incidents to investigate right now." />}</section><section className="panel"><div className="panel-heading"><div><h2>Recent deployments</h2><p>Changes that help tell the story</p></div><Link className="text-link" href="/deployments">View all <ArrowRight size={14} /></Link></div><div className="deployment-list">{data.recent_deployments.slice(0, 3).map(deployment => <div className="deployment-row" key={deployment.id}><span className="deployment-icon"><GitBranch size={17} /></span><div><strong>{deployment.service} <span className="version-tag">{deployment.version}</span></strong><span>{deployment.environment}<span className="inline-dot">·</span>{ago(deployment.created_at)}</span></div><Badge value={deployment.status} /></div>)}</div>{!data.recent_deployments.length && <Empty title="No deployments recorded" detail="Record a release to correlate changes with incidents." />}</section></div>
    </>}
  </>;
}

function Metric({ label, value, unit, detail, values, color, icon }: { label: string; value: string; unit?: string; detail: string; values: number[]; color: string; icon: ReactNode }) {
  return <section className="metric-card"><div className="metric-label">{label}<span>{icon}</span></div><div className="metric-value-row"><strong>{value}{unit && <small>{unit}</small>}</strong>{values.length ? <Sparkline values={values} id={label.replace(/\s/g, "")} color={color} /> : <span className="metric-check"><ShieldCheck size={29} /></span>}</div><span className="metric-detail">{detail}</span></section>;
}
