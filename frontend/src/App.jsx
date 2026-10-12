import { useCallback, useEffect, useState } from 'react';
import { NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import {
  AlertTriangle, ArrowDownRight, ArrowRight, ArrowUpRight, Bell, ChevronDown,
  ChevronLeft, ChevronRight, CircleHelp, ClipboardList, Cloud, Droplets, FileClock,
  Gauge, Leaf, LogOut, MapPin, Menu, Plus, Search, Settings as SettingsIcon, ShieldCheck,
  Sprout, Tractor, Wifi, X, Check, Clock3, Battery, LayoutDashboard,
  ScanLine, SlidersHorizontal, Download, Eye, Pencil, Trash2, RefreshCw,
  CircleCheck, CircleAlert, LoaderCircle, LockKeyhole, Mail, UserRound, Radio,
} from 'lucide-react';
import { api, relativeTime, saveCsv, timestamp } from './api.js';
import { createDemoPlant, deleteDemoPlant, markDemoAlertRead, updateDemoPlant } from './demoData.js';
import { useDataSource } from './useDataSource.js';
import { useLoad } from './useLoad.js';
const NAV = [
  { label: 'Overview', to: '/', icon: LayoutDashboard },
  { label: 'Crop management', to: '/crops', icon: Sprout },
  { label: 'Disease detection', to: '/detections', icon: ScanLine },
  { label: 'Irrigation', to: '/irrigation', icon: Droplets },
  { label: 'Rover monitoring', to: '/rover', icon: Tractor },
  { label: 'GPS / field map', to: '/field', icon: MapPin },
  { label: 'Alerts', to: '/alerts', icon: Bell },
  { label: 'Reports & history', to: '/history', icon: FileClock },
  { label: 'Settings', to: '/settings', icon: SettingsIcon },
];
const POLL_MS = Math.max(30_000, Number(import.meta.env.VITE_POLL_INTERVAL_MS) || 60_000);
const API_DOCS_URL = `${(import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')}/docs`;
const EMPTY_LIST = [];

export default function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem('flora_token'));
  const [demoMode, setDemoMode] = useState(() => localStorage.getItem('flora_demo_mode') === 'true');
  const [user, setUser] = useState(null);
  const [authChecking, setAuthChecking] = useState(Boolean(sessionStorage.getItem('flora_token')));
  const [authError, setAuthError] = useState('');
  const navigate = useNavigate();

  useEffect(() => { localStorage.setItem('flora_demo_mode', String(demoMode)); }, [demoMode]);

  useEffect(() => {
    if (!token) { setAuthChecking(false); setUser(null); return; }
    const controller = new AbortController();
    api.me(token, controller.signal).then(setUser).catch((error) => {
      if (error.status === 401) { sessionStorage.removeItem('flora_token'); setToken(null); }
      else setAuthError(error.message);
    }).finally(() => setAuthChecking(false));
    return () => controller.abort();
  }, [token]);

  const signIn = async (payload, mode) => {
    setAuthError('');
    try {
      const result = mode === 'register' ? await api.register(payload) : await api.login(payload);
      sessionStorage.setItem('flora_token', result.access_token);
      setToken(result.access_token);
    } catch (error) { setAuthError(error.message); throw error; }
  };
  const signOut = () => { sessionStorage.removeItem('flora_token'); setToken(null); setUser(null); navigate('/'); };

  if (!token) return <AuthScreen onSubmit={signIn} error={authError} />;
  if (authChecking) return <div className="auth-loading"><LoaderCircle className="spin" size={24} /> Checking your session…</div>;
  if (!user && authError) return <AuthScreen onSubmit={signIn} error={authError} />;
  return <DashboardShell token={token} user={user} demoMode={demoMode} onDemoModeChange={setDemoMode} onSignOut={signOut} />;
}

function AuthScreen({ onSubmit, error }) {
  const [mode, setMode] = useState('login');
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');
  async function submit(event) {
    event.preventDefault(); setFormError('');
    const data = new FormData(event.currentTarget);
    const payload = { email: data.get('email'), password: data.get('password') };
    if (mode === 'register') payload.full_name = data.get('full_name');
    if (mode === 'register' && payload.password.length < 10) { setFormError('Use at least 10 characters for your password.'); return; }
    setBusy(true);
    try { await onSubmit(payload, mode); } catch (e) { setFormError(e.message); } finally { setBusy(false); }
  }
  return (
    <main className="auth-page">
      <section className="auth-card">
        <BrandMark large />
        <p className="eyebrow auth-eyebrow">CROP CARE INTELLIGENCE</p>
        <h1>{mode === 'login' ? 'Welcome back' : 'Create your operator account'}</h1>
        <p className="auth-subtitle">Sign in to connect with your Flora-Bot workspace.</p>
        {(formError || error) && <div className="inline-error"><CircleAlert size={16} />{formError || error}</div>}
        <form onSubmit={submit} className="auth-form">
          {mode === 'register' && <label>Full name<div className="input-wrap"><UserRound size={17} /><input name="full_name" autoComplete="name" required minLength="1" maxLength="160" placeholder="Your name" /></div></label>}
          <label>Email address<div className="input-wrap"><Mail size={17} /><input name="email" type="email" autoComplete="email" required placeholder="you@example.com" /></div></label>
          <label>Password<div className="input-wrap"><LockKeyhole size={17} /><input name="password" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required placeholder={mode === 'register' ? 'At least 10 characters' : 'Enter your password'} /></div></label>
          <button className="button button-primary button-wide" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : null}{mode === 'login' ? 'Sign in' : 'Create account'}<ArrowRight size={17} /></button>
        </form>
        <p className="auth-switch">{mode === 'login' ? 'New to Flora-Bot?' : 'Already registered?'} <button onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setFormError(''); }}>{mode === 'login' ? 'Create account' : 'Sign in'}</button></p>
        <div className="auth-note"><ShieldCheck size={16} /> Your credentials are sent only to the configured Flora-Bot API.</div>
      </section>
      <div className="auth-aside"><div className="auth-aside-content"><div className="aside-icon"><Leaf size={20} /></div><p className="eyebrow">FIELD INTELLIGENCE, CONNECTED</p><h2>A clearer picture of every growing day.</h2><p>Bring crop records, disease observations and rover reports into one considered workspace.</p><div className="aside-footer"><span><span className="pulse-dot" /> Live data appears when your backend receives it</span><span>Flora-Bot · Crop Care</span></div></div></div>
    </main>
  );
}

function BrandMark({ large = false }) {
  return <div className={`brand ${large ? 'brand-large' : ''}`}><span className="brand-icon"><Leaf size={large ? 23 : 20} strokeWidth={2.1} /></span><span><strong>Flora-Bot</strong><small>Crop Care Intelligence</small></span></div>;
}

function DashboardShell({ token, user, demoMode, onDemoModeChange, onSignOut }) {
  const [collapsed, setCollapsed] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [network, setNetwork] = useState('checking');
  const alertState = useDataSource(token, demoMode, 'alerts', (signal) => api.alerts(token, signal));
  const alertCount = alertState.data?.filter((item) => !item.is_read).length ?? null;
  const location = useLocation();
  const page = NAV.find((item) => item.to === location.pathname) || NAV[0];
  const refreshHealth = useCallback((signal) => {
    api.health(signal).then(() => setNetwork('connected')).catch((error) => { if (error.name !== 'AbortError') setNetwork('unavailable'); });
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    refreshHealth(controller.signal);
    const timer = window.setInterval(() => { if (!document.hidden) refreshHealth(controller.signal); }, POLL_MS);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [refreshHealth]);
  return (
    <div className={`app-shell ${collapsed ? 'is-collapsed' : ''}`}>
      {drawer && <button className="drawer-scrim" aria-label="Close navigation" onClick={() => setDrawer(false)} />}
      <aside className={`sidebar ${drawer ? 'drawer-open' : ''}`}>
        <div className="sidebar-brand"><BrandMark /><button className="icon-button collapse-button" aria-label="Collapse sidebar" onClick={() => setCollapsed(!collapsed)}><ChevronLeft size={17} /></button><button className="icon-button drawer-close" aria-label="Close navigation" onClick={() => setDrawer(false)}><X size={18} /></button></div>
        <div className="workspace-label">WORKSPACE</div>
        <nav className="sidebar-nav" aria-label="Main navigation">{NAV.map(({ label, to, icon: Icon }) => <NavLink key={to} to={to} end={to === '/'} title={collapsed ? label : undefined} onClick={() => setDrawer(false)} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}><Icon size={18} strokeWidth={1.8} /><span>{label}</span>{label === 'Alerts' && alertCount > 0 && <em className="nav-count">{alertCount}</em>}</NavLink>)}</nav>
        <div className="sidebar-bottom"><a className="help-card" href={API_DOCS_URL} target="_blank" rel="noopener noreferrer" aria-label="Open Flora-Bot API documentation in a new tab"><span className="help-icon"><CircleHelp size={17} /></span><div><strong>Need a hand?</strong><small>Explore the API guide</small></div><ArrowRight size={15} /></a><div className="sidebar-user"><span className="avatar">{user?.full_name?.slice(0, 1)?.toUpperCase() || 'F'}</span><div className="sidebar-user-text"><strong>{user?.full_name || 'Flora-Bot user'}</strong><small>{user?.role || 'Operator'}</small></div><button className="icon-button logout-button" aria-label="Sign out" title="Sign out" onClick={onSignOut}><LogOut size={16} /></button></div></div>
      </aside>
      <div className="main-area">
        <header className="topbar"><button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setDrawer(true)}><Menu size={20} /></button><div className="page-heading"><span className="breadcrumb">Workspace <ChevronRight size={13} /> {page.label}</span><h1>{page.label}</h1></div><div className="topbar-actions">{demoMode && <span className="demo-mode-badge">DEMO DATA</span>}<div className={`api-status ${network}`} title={network === 'connected' ? 'Backend health endpoint responded' : network === 'unavailable' ? 'Backend health endpoint is unavailable' : 'Checking backend'}><span className="status-dot" />{network === 'connected' ? 'API connected' : network === 'unavailable' ? 'API unavailable' : 'Checking API'}</div><NavLink className="icon-button notification-button" to="/alerts" aria-label="Alerts"><Bell size={18} />{alertCount > 0 && <i>{alertCount > 9 ? '9+' : alertCount}</i>}</NavLink><div className="top-user"><span className="avatar small-avatar">{user?.full_name?.slice(0, 1)?.toUpperCase() || 'F'}</span><span>{user?.full_name?.split(' ')[0] || 'Account'}</span><ChevronDown size={14} /><button className="user-logout" onClick={onSignOut}>Sign out</button></div></div></header>
        <main className="content"><Routes><Route path="/" element={<Overview token={token} demoMode={demoMode} alertState={alertState} />} /><Route path="/crops" element={<Crops token={token} demoMode={demoMode} />} /><Route path="/detections" element={<Detections token={token} demoMode={demoMode} />} /><Route path="/irrigation" element={<Irrigation token={token} demoMode={demoMode} />} /><Route path="/rover" element={<Rover token={token} demoMode={demoMode} />} /><Route path="/field" element={<Field token={token} demoMode={demoMode} />} /><Route path="/alerts" element={<Alerts token={token} demoMode={demoMode} alertState={alertState} />} /><Route path="/history" element={<History token={token} demoMode={demoMode} alertState={alertState} />} /><Route path="/settings" element={<Settings token={token} user={user} demoMode={demoMode} onDemoModeChange={onDemoModeChange} />} /><Route path="*" element={<Overview token={token} demoMode={demoMode} alertState={alertState} />} /></Routes><footer className="page-footer"><span>Flora-Bot · Crop Care Intelligence</span><span>{demoMode ? "Demo data is isolated from PostgreSQL" : "Dashboard refreshes periodically when the page is active"}</span></footer></main>
      </div>
    </div>
  );
}

function PageIntro({ eyebrow, title, description, action }) { return <div className="page-intro"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2><p>{description}</p></div>{action}</div>; }
function Panel({ title, subtitle, action, children, className = '' }) { return <section className={`panel ${className}`}><div className="panel-head"><div><h3>{title}</h3>{subtitle && <p>{subtitle}</p>}</div>{action}</div>{children}</section>; }
function EmptyState({ icon: Icon = Cloud, title = 'No data available', text = 'No records have been received yet. Data will appear here after the backend receives it.' }) { return <div className="empty-state"><span className="empty-icon"><Icon size={20} /></span><strong>{title}</strong><p>{text}</p></div>; }
function LoadingState({ slow = false }) { return <div className="loading-state"><LoaderCircle size={19} className="spin" /><span>{slow ? 'This is taking longer than usual…' : 'Loading records…'}</span></div>; }
function ErrorState({ message, onRetry }) { return <div className="error-state"><CircleAlert size={18} /><span>{message}</span>{onRetry && <button className="text-button" onClick={() => onRetry()}>Retry</button>}</div>; }
function Badge({ children, kind = '' }) { return <span className={`badge ${kind}`}>{children}</span>; }
function useLookups(token, demoMode) {
  const plants = useDataSource(token, demoMode, 'plants', (signal) => api.plants(token, signal));
  const detections = useDataSource(token, demoMode, 'detections', (signal) => api.detections(token, signal));
  const telemetry = useDataSource(token, demoMode, 'telemetry', (signal) => api.telemetry(token, signal));
  const watering = useDataSource(token, demoMode, 'watering', (signal) => api.watering(token, signal));
  return { plants, detections, telemetry, watering };
}

function Overview({ token, demoMode, alertState }) {
  const data = useLookups(token, demoMode);
  const plants = data.plants.data || EMPTY_LIST, detections = data.detections.data || EMPTY_LIST;
  const telemetry = data.telemetry.data || EMPTY_LIST;
  const watering = data.watering.data || EMPTY_LIST, alerts = alertState.data || EMPTY_LIST;
  const latestRobot = telemetry[0];
  const recentDetections = [...detections].sort((a, b) => new Date(b.detected_at) - new Date(a.detected_at)).slice(0, 5);
  const unread = alerts.filter((alert) => !alert.is_read);
  return <>
    <div className="welcome-row"><div><p className="eyebrow">FIELD OVERVIEW</p><h2>Your crops, at a glance.</h2><p>{demoMode ? 'A consistent example workspace for demonstrating Flora-Bot.' : 'Live operational data from your Flora-Bot workspace.'}</p></div><div className="last-refresh"><span className="refresh-mark"><RefreshCw size={14} /></span><span>{demoMode ? 'Fixed example dataset' : `Updates every ${Math.round(POLL_MS / 1000)} seconds`}</span></div></div>
    {(Object.values(data).some((item) => item.error) || alertState.error) && <ErrorState message="Some dashboard data could not be loaded. Values shown are limited to the data received." />}
    <section className="metric-grid">
      <Metric title="Registered crops" value={data.plants.data === null ? '—' : plants.length} note="Plant records" icon={Sprout} tint="green" href="/crops" />
      <Metric title="Disease detections" value={data.detections.data === null ? '—' : detections.length} note="Inference results received" icon={ScanLine} tint="amber" href="/detections" />
      <Metric title="Recorded watering events" value={data.watering.data === null ? '—' : watering.length} note="Events received" icon={Droplets} tint="blue" href="/irrigation" />
      <Metric title="Rover state" value={latestRobot?.robot_state || 'Unavailable'} note={latestRobot ? relativeTime(latestRobot.recorded_at) : 'No telemetry received'} icon={Tractor} tint="olive" href="/rover" compact />
    </section>
    <section className="overview-grid">
      <Panel className="detections-panel" title="Recent detections" subtitle="Results reported by the inference service" action={<NavLink className="panel-link" to="/detections">View all <ArrowRight size={14} /></NavLink>}>
        {data.detections.loading && !data.detections.data ? <LoadingState slow={data.detections.slow} /> : data.detections.error ? <ErrorState message={data.detections.error} onRetry={data.detections.reload} /> : recentDetections.length ? <DetectionList rows={recentDetections} plants={plants} /> : <EmptyState icon={ScanLine} title="No detections received" text="When the Raspberry Pi submits a result, it will appear here." />}
      </Panel>
      <Panel title="Rover status" subtitle="Latest reported telemetry" action={<NavLink className="panel-link" to="/rover">Details <ArrowRight size={14} /></NavLink>}>
        {latestRobot ? <RoverMini robot={latestRobot} /> : <EmptyState icon={Radio} title="Rover not reporting" text="No telemetry has been received. The rover connection state is unavailable." />}
      </Panel>
    </section>
    <section className="overview-grid lower-grid">
      <Panel title="Recent activity" subtitle="Alerts and watering records" action={<NavLink className="panel-link" to="/history">History <ArrowRight size={14} /></NavLink>}>
        {unread.length || watering.length ? <ActivityList alerts={unread.slice(0, 3)} watering={watering.slice(0, 3)} /> : <EmptyState icon={FileClock} title="No recent activity" text="New alerts and recorded watering events will appear here." />}
      </Panel>
      <Panel title="Recent watering" subtitle={demoMode ? 'Illustrative events only; no pump is controlled' : 'Completed events recorded by the backend'} action={<NavLink className="panel-link" to="/irrigation">Irrigation <ArrowRight size={14} /></NavLink>}>
        {watering.length ? <WateringList rows={watering.slice(0, 3)} plants={plants} /> : <EmptyState icon={Droplets} title="No watering records" text="Recorded irrigation events will appear here when submitted." />}
      </Panel>
    </section>
  </>;
}

function Metric({ title, value, note, icon: Icon, tint, href, compact }) { return <NavLink to={href} className="metric-card"><div className={`metric-icon ${tint}`}><Icon size={19} /></div><span className="metric-title">{title}</span><strong className={compact ? 'metric-value compact-value' : 'metric-value'}>{value}</strong><span className="metric-note">{note}</span><ArrowUpRight className="metric-arrow" size={15} /></NavLink>; }
function DetectionList({ rows, plants = [] }) { const plantMap = new Map(plants.map((item) => [item.id, item])); return <div className="detection-list">{rows.map((row) => { const isHealthy = row.class_name?.endsWith('_Healthy'); return <div className="detection-row" key={row.id}><span className={`detection-symbol ${isHealthy ? 'healthy' : 'flagged'}`}>{isHealthy ? <Leaf size={17} /> : <AlertTriangle size={17} />}</span><div className="detection-main"><strong>{row.class_name?.replaceAll('_', ' ') || 'Unknown class'}</strong><span>{row.plant_id ? plantMap.get(row.plant_id)?.crop_type || `Plant #${row.plant_id}` : 'Plant not linked'} · {timestamp(row.detected_at)}</span></div><div className="detection-meta"><Badge kind={confidenceKind(row.confidence_status)}>{row.confidence_status?.replaceAll('_', ' ') || 'Status unavailable'}</Badge><span>{Number.isFinite(row.confidence) ? `${(row.confidence * 100).toFixed(1)}%` : 'Confidence unavailable'}</span></div></div>; })}</div>; }
function confidenceKind(value) { return value === 'HIGH_CONFIDENCE' ? 'badge-green' : value === 'REVIEW_RECOMMENDED' ? 'badge-amber' : value === 'UNCERTAIN' ? 'badge-gray' : ''; }
function RoverMini({ robot, simulated = false }) { return <div className="rover-mini"><div className="rover-topline"><span className="rover-device-icon"><Tractor size={23} /></span><span><strong>{robot.robot_id}</strong><small>{relativeTime(robot.recorded_at)}</small></span>{simulated && <Badge kind="badge-amber">SIMULATED ROVER</Badge>}</div><div className="rover-mini-grid"><InfoCell label="Battery" value={display(robot.battery_level, '%')} icon={Battery} /><InfoCell label="Movement" value={robot.movement_status || 'Unavailable'} icon={ArrowRight} /><InfoCell label="Coordinates" value={robot.latitude != null && robot.longitude != null ? `${robot.latitude.toFixed(4)}, ${robot.longitude.toFixed(4)}` : 'Unavailable'} icon={MapPin} /></div></div>; }
function InfoCell({ label, value, icon: Icon }) { return <div className="info-cell"><span><Icon size={14} />{label}</span><strong>{value}</strong></div>; }
function display(value, unit = '') { return value == null ? 'Unavailable' : `${value}${unit}`; }
function ActivityList({ alerts, watering }) { const events = [...alerts.map((item) => ({ kind: 'alert', at: item.created_at, title: item.message, caption: item.alert_type?.replaceAll('_', ' ') })), ...watering.map((item) => ({ kind: 'water', at: item.started_at, title: `Watering recorded · ${item.robot_id}`, caption: item.trigger_source || 'Source not specified' }))].sort((a, b) => new Date(b.at) - new Date(a.at)).slice(0, 4); return <div className="activity-list">{events.map((event, i) => <div className="activity-row" key={`${event.kind}-${event.at}-${i}`}><span className={`activity-icon ${event.kind}`}><i>{event.kind === 'alert' ? <Bell size={14} /> : <Droplets size={14} />}</i></span><span><strong>{event.title}</strong><small>{event.caption} · {relativeTime(event.at)}</small></span></div>)}</div>; }
function WateringList({ rows, plants = [] }) { const plantMap = new Map(plants.map((plant) => [plant.id, plant])); return <div className="activity-list">{rows.map((row) => <div className="activity-row" key={row.id}><span className="activity-icon water"><Droplets size={14} /></span><span><strong>{plantMap.get(row.plant_id)?.crop_type || (row.plant_id ? `Plant #${row.plant_id}` : 'Unlinked crop')} · {row.duration_seconds ?? '—'} sec</strong><small>{timestamp(row.started_at)} · {row.trigger_source || 'Source not provided'}</small></span></div>)}</div>; }

function Crops({ token, demoMode }) {
  const { data, loading, slow, error, reload } = useDataSource(token, demoMode, 'plants', (signal) => api.plants(token, signal));
  const [query, setQuery] = useState(''), [modal, setModal] = useState(null), [feedback, setFeedback] = useState('');
  const [busy, setBusy] = useState(false);
  const rows = (data || EMPTY_LIST).filter((plant) => `${plant.crop_type} ${plant.variety || ''} ${plant.field_area || ''} ${plant.health_status || ''}`.toLowerCase().includes(query.toLowerCase()));
  async function save(event) {
    event.preventDefault(); setBusy(true); setFeedback(''); const fd = new FormData(event.currentTarget);
    const nullableNumber = (value) => value === '' ? null : Number(value);
    const body = { crop_type: String(fd.get('crop_type')).trim(), variety: String(fd.get('variety')).trim() || null, field_area: String(fd.get('field_area')).trim() || null, latitude: nullableNumber(fd.get('latitude')), longitude: nullableNumber(fd.get('longitude')), health_status: String(fd.get('health_status')).trim() || null };
    try {
      if (demoMode) {
        if (modal?.id) await updateDemoPlant(modal.id, body); else await createDemoPlant(body);
      } else if (modal?.id) await api.updatePlant(token, modal.id, body); else await api.createPlant(token, body);
      setModal(null); setFeedback(demoMode ? 'Demo crop updated in this browser only.' : modal?.id ? 'Crop record updated.' : 'Crop record added.'); await reload({ force: true });
    }
    catch (e) { setFeedback(e.message); } finally { setBusy(false); }
  }
  async function remove(plant) { if (!window.confirm(`Delete ${demoMode ? 'demo ' : ''}crop record #${plant.id}? This action cannot be undone.`)) return; setFeedback(''); try { if (demoMode) await deleteDemoPlant(plant.id); else await api.deletePlant(token, plant.id); setFeedback(demoMode ? 'Demo crop removed from this browser.' : 'Crop record deleted.'); await reload({ force: true }); } catch (e) { setFeedback(e.message); } }
  return <>
    <PageIntro eyebrow="CROP REGISTRY" title="Crop management" description="Manage crop and plant records registered in your workspace." action={<button className="button button-primary" onClick={() => setModal({})}><Plus size={17} /> Add crop</button>} />
    {feedback && <div className="notice"><CircleCheck size={16} />{feedback}<button className="notice-close" aria-label="Dismiss" onClick={() => setFeedback('')}><X size={15} /></button></div>}
    <Panel title="Registered crops" subtitle={`${data?.length ?? '—'} records in the ${demoMode ? 'demo workspace' : 'workspace'}`} action={<div className="table-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search crops" aria-label="Search crops" /></div>}>
      {loading && !data ? <LoadingState slow={slow} /> : error ? <ErrorState message={error} onRetry={reload} /> : rows.length ? <div className="table-wrap"><table><thead><tr><th>Crop / variety</th><th>Field / area</th><th>Location</th><th>Health status</th><th>Last scanned</th><th>Last watered</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{rows.map((plant) => <tr key={plant.id}><td><span className="table-primary">{plant.crop_type}</span><small>{plant.variety || 'Variety not specified'} · #{plant.id}</small></td><td>{plant.field_area || 'Not specified'}</td><td>{plant.latitude != null && plant.longitude != null ? <span className="coordinate"><MapPin size={13} />{plant.latitude.toFixed(4)}, {plant.longitude.toFixed(4)}</span> : <span className="muted">Unavailable</span>}</td><td>{plant.health_status ? <Badge kind="badge-gray">{plant.health_status}</Badge> : <span className="muted">Not reported</span>}</td><td>{plant.last_scanned_at ? timestamp(plant.last_scanned_at) : <span className="muted">Not scanned</span>}</td><td>{plant.last_watered_at ? timestamp(plant.last_watered_at) : <span className="muted">Not recorded</span>}</td><td><div className="row-actions"><button className="icon-button" title="Edit crop" aria-label={`Edit ${plant.crop_type}`} onClick={() => setModal(plant)}><Pencil size={15} /></button><button className="icon-button danger-icon" title="Delete crop (Admin only)" aria-label={`Delete ${plant.crop_type}`} onClick={() => remove(plant)}><Trash2 size={15} /></button></div></td></tr>)}</tbody></table></div> : <EmptyState icon={Sprout} title={query ? 'No matching crops' : 'No crop records yet'} text={query ? 'Try another crop, variety or area.' : 'Register a crop to start building your field record. No crops are added automatically.'} />}
    </Panel>
    {modal && <Modal title={modal.id ? 'Edit crop record' : 'Register a crop'} close={() => setModal(null)}><form className="form-grid" onSubmit={save}><label>Crop type <input name="crop_type" required maxLength="100" defaultValue={modal.crop_type || ''} placeholder="e.g. Tomato" /></label><label>Variety <input name="variety" defaultValue={modal.variety || ''} placeholder="Optional variety" /></label><label className="field-span">Field / area <input name="field_area" defaultValue={modal.field_area || ''} placeholder="Field or growing area name" /></label><label>Latitude <input name="latitude" type="number" step="any" min="-90" max="90" defaultValue={modal.latitude ?? ''} placeholder="Optional GPS latitude" /></label><label>Longitude <input name="longitude" type="number" step="any" min="-180" max="180" defaultValue={modal.longitude ?? ''} placeholder="Optional GPS longitude" /></label><label className="field-span">Health status <input name="health_status" defaultValue={modal.health_status || ''} placeholder="Optional observed status" /></label><div className="form-actions field-span"><button type="button" className="button button-secondary" onClick={() => setModal(null)}>Cancel</button><button className="button button-primary" disabled={busy}>{busy ? <LoaderCircle size={16} className="spin" /> : <Check size={16} />}{modal.id ? 'Save changes' : 'Create crop'}</button></div>{feedback && <div className="inline-error field-span">{feedback}</div>}</form></Modal>}
  </>;
}

function Modal({ title, children, close }) { useEffect(() => { const onKey = (event) => { if (event.key === 'Escape') close(); }; window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey); }, [close]); return <div className="modal-scrim" onMouseDown={(event) => { if (event.target === event.currentTarget) close(); }}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div className="modal-head"><div><p className="eyebrow">CROP REGISTRY</p><h3 id="modal-title">{title}</h3></div><button className="icon-button" aria-label="Close dialog" onClick={close}><X size={18} /></button></div>{children}</section></div>; }

function Detections({ token, demoMode }) {
  const { data, loading, slow, error, reload } = useDataSource(token, demoMode, 'detections', (signal) => api.detections(token, signal));
  const plantsQuery = useDataSource(token, demoMode, 'plants', (signal) => api.plants(token, signal));
  const model = useLoad((signal) => api.inferenceStatus(token, signal), [token]);
  const [query, setQuery] = useState(''), [confidence, setConfidence] = useState('all');
  const plants = plantsQuery.data || EMPTY_LIST;
  const rows = (data || EMPTY_LIST).filter((item) => (confidence === 'all' || item.confidence_status === confidence) && `${item.class_name} ${item.model_version || ''} ${item.plant_id || ''}`.toLowerCase().includes(query.toLowerCase())).sort((a, b) => new Date(b.detected_at) - new Date(a.detected_at));
  return <><PageIntro eyebrow="INFERENCE RECORDS" title="Disease detection" description={demoMode ? 'Clearly labelled example results; actual predictions require the configured model.' : 'Stored inference results, plus an image test workflow when the local classifier is configured.'} /><InferenceTool token={token} demoMode={demoMode} plants={plants} model={model} reload={reload} /><Panel title="Detection results" subtitle={`${data?.length ?? '—'} results received${demoMode ? ' · examples' : ''}`} action={<div className="table-tools"><div className="table-search"><Search size={15} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search class or plant" aria-label="Search detections" /></div><select aria-label="Filter by confidence status" value={confidence} onChange={(e) => setConfidence(e.target.value)}><option value="all">All confidence states</option><option value="HIGH_CONFIDENCE">High confidence</option><option value="REVIEW_RECOMMENDED">Review recommended</option><option value="UNCERTAIN">Uncertain</option></select></div>}>
    {loading && !data ? <LoadingState slow={slow} /> : error ? <ErrorState message={error} onRetry={reload} /> : rows.length ? <div className="table-wrap"><table><thead><tr><th>Predicted class</th><th>Plant</th><th>Confidence</th><th>Timestamp</th><th>Location</th><th>Model</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td><span className="table-primary">{row.class_name.replaceAll('_', ' ')}</span><small>Prediction · #{row.id}</small></td><td>{row.plant_id ? plants.find((p) => p.id === row.plant_id)?.crop_type || `Plant #${row.plant_id}` : 'Not linked'}</td><td><div className="confidence-cell"><Badge kind={confidenceKind(row.confidence_status)}>{row.confidence_status?.replaceAll('_', ' ') || 'Unavailable'}</Badge><strong>{Number.isFinite(row.confidence) ? `${(row.confidence * 100).toFixed(1)}%` : '—'}</strong></div></td><td>{timestamp(row.detected_at)}</td><td>{row.latitude != null && row.longitude != null ? `${row.latitude.toFixed(4)}, ${row.longitude.toFixed(4)}` : 'Unavailable'}</td><td>{row.model_version || 'Not provided'}</td></tr>)}</tbody></table></div> : <EmptyState icon={ScanLine} title={query || confidence !== 'all' ? 'No matching detections' : 'No inference results received'} text={query || confidence !== 'all' ? 'Change your search or status filter.' : 'Upload a leaf image above when the local classifier is available, or wait for an inference result from a connected client.'} />}
  </Panel><div className="info-banner"><ShieldCheck size={17} /><span><strong>Inference records are not diagnoses.</strong> Confidence labels reflect submitted classifier output; agronomic review may still be appropriate.</span></div></>;
}

function InferenceTool({ token, demoMode, plants, model, reload }) {
  const [file, setFile] = useState(null), [plantId, setPlantId] = useState(''), [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null), [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault();
    if (!file || !model.data?.available || demoMode) return;
    setBusy(true); setError(''); setResult(null);
    try { const prediction = await api.inferImage(token, file, plantId); setResult(prediction); await reload({ force: true }); }
    catch (failure) { setError(failure.message || 'The model could not process this image.'); }
    finally { setBusy(false); }
  }
  return <Panel title="Test a leaf image" subtitle={demoMode ? 'Switch Demo Mode off before running and saving an actual model result.' : model.data?.available ? `Classifier ready · ${model.data.model_version}` : model.loading ? 'Checking the backend model…' : model.error ? 'Model availability could not be checked.' : model.data?.reason || 'Classifier unavailable'}>
    {demoMode ? <p className="settings-help">Example predictions remain isolated from model inference. Turn Demo Mode off in Settings to submit an image.</p> : <form className="inference-form" onSubmit={submit}>
      <label>Leaf image <input type="file" accept="image/*" onChange={(event) => { setFile(event.target.files?.[0] || null); setResult(null); setError(''); }} /></label>
      <label>Link to crop (optional)<select value={plantId} onChange={(event) => setPlantId(event.target.value)}><option value="">No crop association</option>{plants.map((plant) => <option key={plant.id} value={plant.id}>{plant.crop_type}{plant.variety ? ` · ${plant.variety}` : ''}</option>)}</select></label>
      <button className="button button-primary" disabled={!file || !model.data?.available || busy}>{busy ? <LoaderCircle size={16} className="spin" /> : <ScanLine size={16} />}{busy ? 'Running classifier…' : 'Run actual model'}</button>
      {!model.loading && !model.error && !model.data?.available && <p className="settings-help">A local model file and the optional inference runtime are required. No prediction is generated while either is unavailable.</p>}
      {model.error && <ErrorState message={model.error} onRetry={() => model.reload({ force: true })} />}
      {error && <ErrorState message={error} />}
      {result && <div className="inference-result"><Badge kind="badge-green">ACTUAL MODEL RESULT</Badge><strong>{result.class_name.replaceAll('_', ' ')} · {(result.confidence * 100).toFixed(1)}%</strong><small>{result.confidence_status.replaceAll('_', ' ')} · {timestamp(result.detected_at)} · {result.model_version}</small><small>The uploaded image was processed in memory and was not stored.</small></div>}
      {file && <small className="muted">Selected: {file.name}</small>}
    </form>}
  </Panel>;
}

function Irrigation({ token, demoMode }) {
  const watering = useDataSource(token, demoMode, 'watering', (signal) => api.watering(token, signal));
  const plantsQuery = useDataSource(token, demoMode, 'plants', (signal) => api.plants(token, signal));
  const plants = plantsQuery.data || EMPTY_LIST;
  const rows = [...(watering.data || EMPTY_LIST)].sort((a, b) => new Date(b.started_at) - new Date(a.started_at));
  return <><PageIntro eyebrow="WATER MANAGEMENT" title="Irrigation" description="Review recorded watering events. This page does not control a physical pump." />
    <div className="metric-grid irrigation-metrics"><Metric title="Watering events" value={watering.data === null ? '—' : rows.length} note={demoMode ? 'Example records' : 'Stored backend records'} icon={Droplets} tint="blue" href="/history" /><Metric title="Latest event" value={rows[0] ? new Date(rows[0].started_at).toLocaleDateString() : 'No records'} note={rows[0] ? timestamp(rows[0].started_at) : 'No watering submitted'} icon={Clock3} tint="green" href="/history" /><div className="control-unavailable"><span className="control-icon"><LockKeyhole size={16} /></span><span><strong>Pump control unavailable</strong><small>No physical control endpoint is exposed.</small></span></div><div className="control-unavailable"><span className="control-icon"><ShieldCheck size={16} /></span><span><strong>Disease is separate</strong><small>Predictions do not trigger irrigation.</small></span></div></div>
    <Panel title="Watering history" subtitle={demoMode ? "Consistent example records · no hardware action" : "Events recorded by the API"}>{watering.loading && !watering.data ? <LoadingState slow={watering.slow} /> : watering.error ? <ErrorState message={watering.error} onRetry={watering.reload} /> : rows.length ? <div className="table-wrap"><table><thead><tr><th>Started</th><th>Crop</th><th>Robot</th><th>Duration</th><th>Water amount</th><th>Trigger / source</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td><span className="table-primary">{timestamp(row.started_at)}</span><small>{row.ended_at ? "Ended " + timestamp(row.ended_at) : 'End time not recorded'}</small></td><td>{row.plant_id ? plants.find((plant) => plant.id === row.plant_id)?.crop_type || "Plant #" + row.plant_id : 'Not linked'}</td><td>{row.robot_id}</td><td>{row.duration_seconds == null ? 'Not recorded' : row.duration_seconds + ' sec'}</td><td>{row.water_amount_liters == null ? 'Not measured' : row.water_amount_liters + ' L'}</td><td>{row.trigger_source || 'Source not specified'}</td></tr>)}</tbody></table></div> : <EmptyState icon={Droplets} title="No watering events recorded" text="Completed irrigation events appear after a client or device submits them." />}</Panel>
    <div className="info-banner"><ShieldCheck size={17} /><span><strong>Monitoring only.</strong> No pump commands are sent. Disease classifications do not start watering.</span></div>
  </>;
}
function Rover({ token, demoMode }) {
  const { data, loading, slow, error, reload } = useDataSource(token, demoMode, 'telemetry', (signal) => api.telemetry(token, signal));
  const robots = data || EMPTY_LIST;
  return <><PageIntro eyebrow="ROBOT TELEMETRY" title="Rover monitoring" description={demoMode ? "A consistent example rover scenario. Coordinates and readings are simulated." : "Latest telemetry received from registered devices; no heartbeat is inferred from silence."} />
    {demoMode && <RoverIllustration />}
    {loading && !data ? <LoadingState slow={slow} /> : error ? <ErrorState message={error} onRetry={reload} /> : robots.length ? <div className="robot-grid">{robots.map((robot) => <RobotCard key={robot.robot_id} robot={robot} simulated={demoMode} />)}</div> : <Panel title="Rover fleet" subtitle="Current telemetry reported by registered devices"><EmptyState icon={Tractor} title="No rover telemetry received" text="The rover state remains unavailable until a device submits telemetry." /></Panel>}
    <Panel title="Telemetry history" subtitle={demoMode ? "Fixed simulated state changes for demonstration" : "The backend currently returns the latest state per registered rover."}>{robots.length ? <div className="table-wrap"><table><thead><tr><th>Recorded</th><th>Robot</th><th>State</th><th>Movement</th><th>Battery</th><th>Coordinates</th></tr></thead><tbody>{robots.map((robot) => <tr key={robot.id || robot.recorded_at}><td>{timestamp(robot.recorded_at)}</td><td>{robot.robot_id}</td><td>{robot.robot_state || 'Unavailable'}</td><td>{robot.movement_status || 'Unavailable'}</td><td>{display(robot.battery_level, '%')}</td><td>{robot.latitude != null && robot.longitude != null ? robot.latitude.toFixed(5) + ', ' + robot.longitude.toFixed(5) : 'Unavailable'}</td></tr>)}</tbody></table></div> : <EmptyState icon={Radio} title="No telemetry history" text="Telemetry history will appear after records are submitted." />}</Panel>
    <Panel title="Connection interpretation" subtitle="API health does not establish a rover connection"><div className="rover-notes"><div><span className="note-icon"><Radio size={16} /></span><span><strong>Telemetry timestamp</strong><small>Shows when a record was captured; an old timestamp is not automatically called offline.</small></span></div><div><span className="note-icon"><Battery size={16} /></span><span><strong>Measurements</strong><small>Missing battery or location fields remain unavailable instead of showing zero.</small></span></div><div><span className="note-icon"><LockKeyhole size={16} /></span><span><strong>Controls</strong><small>Movement and pump command endpoints are not exposed.</small></span></div></div></Panel>
  </>;
}
function RoverIllustration() {
  const [failed, setFailed] = useState(false);
  return <div className="rover-illustration">{failed ? <div className="rover-image-fallback"><Tractor size={38} /><span>Rover illustration</span></div> : <img src="/rover-illustration.svg" alt="Illustration of a small agricultural rover, not a photograph of Flora-Bot hardware" onError={() => setFailed(true)} />}<small>Illustration only · not a live camera image</small></div>;
}
function RobotCard({ robot, simulated = false }) {
  const state = robot.robot_state;
  const stale = Date.now() - new Date(robot.recorded_at).getTime() > POLL_MS * 3;
  return <section className="robot-card"><div className="robot-card-head"><span className="robot-big-icon"><Tractor size={23} /></span><span><strong>{robot.robot_id}</strong><small>Last telemetry · {timestamp(robot.recorded_at)}</small></span><Badge kind={simulated ? 'badge-amber' : stale ? 'badge-amber' : state === 'ERROR' ? 'badge-red' : state ? 'badge-green' : 'badge-gray'}>{simulated ? 'SIMULATED ROVER' : stale ? 'Stale telemetry' : state || 'State unavailable'}</Badge></div><div className="robot-stats"><InfoCell label="Battery" value={display(robot.battery_level, '%')} icon={Battery} /><InfoCell label="Movement" value={robot.movement_status || 'Unavailable'} icon={ArrowRight} /><InfoCell label="Coordinates" value={robot.latitude != null && robot.longitude != null ? robot.latitude.toFixed(5) + ', ' + robot.longitude.toFixed(5) : 'Unavailable'} icon={MapPin} /></div></section>;
}
function Field({ token, demoMode }) {
  const plants = useDataSource(token, demoMode, 'plants', (signal) => api.plants(token, signal));
  const detections = useDataSource(token, demoMode, 'detections', (signal) => api.detections(token, signal));
  const telemetry = useDataSource(token, demoMode, 'telemetry', (signal) => api.telemetry(token, signal));
  const points = [ ...(plants.data || []).filter((x) => x.latitude != null && x.longitude != null).map((x) => ({ label: `${x.crop_type}${x.variety ? ` · ${x.variety}` : ''}`, source: 'Plant', lat: x.latitude, lng: x.longitude, at: x.updated_at })), ...(detections.data || []).filter((x) => x.latitude != null && x.longitude != null).map((x) => ({ label: x.class_name?.replaceAll('_', ' '), source: 'Detection', lat: x.latitude, lng: x.longitude, at: x.detected_at })), ...(telemetry.data || []).filter((x) => x.latitude != null && x.longitude != null).map((x) => ({ label: x.robot_id, source: 'Rover', lat: x.latitude, lng: x.longitude, at: x.recorded_at })) ];
  const loading = plants.loading || detections.loading || telemetry.loading;
  const error = plants.error || detections.error || telemetry.error;
  return <><PageIntro eyebrow="LOCATION RECORDS" title="GPS / field map" description={demoMode ? "Example coordinates from the demo workspace." : "Coordinates provided by crop, inference and rover records."} /><Panel title="Recorded locations" subtitle={demoMode ? "Example locations · not live GPS" : "Only submitted coordinates are shown"}>{loading && !points.length ? <LoadingState slow={plants.slow || detections.slow || telemetry.slow} /> : error ? <ErrorState message={error} onRetry={() => { plants.reload(); detections.reload(); telemetry.reload(); }} /> : points.length ? <><div className="map-coordinate-banner"><MapPin size={17} /><span>Map view requires map tiles. The coordinate list below remains available without external tile service.</span></div><div className="table-wrap"><table><thead><tr><th>Record</th><th>Source</th><th>Latitude</th><th>Longitude</th><th>Recorded</th><th>Map</th></tr></thead><tbody>{points.map((point, i) => <tr key={`${point.source}-${point.label}-${i}`}><td className="table-primary">{point.label || 'Location record'}</td><td><Badge kind={point.source === 'Rover' ? 'badge-green' : 'badge-gray'}>{demoMode ? 'DEMO ' : ''}{point.source}</Badge></td><td className="mono">{point.lat.toFixed(6)}</td><td className="mono">{point.lng.toFixed(6)}</td><td>{timestamp(point.at)}</td><td><a className="coordinate-link" target="_blank" rel="noreferrer" href={`https://www.openstreetmap.org/?mlat=${encodeURIComponent(point.lat)}&mlon=${encodeURIComponent(point.lng)}#map=17/${encodeURIComponent(point.lat)}/${encodeURIComponent(point.lng)}`}>Open map <ArrowUpRight size={13} /></a></td></tr>)}</tbody></table></div></> : <EmptyState icon={MapPin} title="No GPS coordinates available" text="Location markers are not fabricated. Coordinates will appear after a plant, detection or rover record includes them." />}</Panel></>;
}

function Alerts({ token, demoMode, alertState }) {
  const { data, loading, slow, error, reload } = alertState;
  const [filter, setFilter] = useState('all'), [busyId, setBusyId] = useState(null), [message, setMessage] = useState('');
  const rows = (data || EMPTY_LIST).filter((item) => filter === 'all' || (filter === 'unread' ? !item.is_read : item.is_read));
  async function markRead(id) { setBusyId(id); setMessage(''); try { if (demoMode) { markDemoAlertRead(id); await reload({ force: true }); setMessage('Demo alert marked as read in this browser.'); } else { await api.markAlertRead(token, id); await reload({ force: true }); setMessage('Alert marked as read.'); } } catch (e) { setMessage(e.message); } finally { setBusyId(null); } }
  return <><PageIntro eyebrow="EVENT CENTER" title="Alerts" description={demoMode ? "Review and update example notifications." : "Event notifications created from data received by the backend."} action={<div className="segmented"><button className={filter === 'all' ? 'selected' : ''} onClick={() => setFilter('all')}>All</button><button className={filter === 'unread' ? 'selected' : ''} onClick={() => setFilter('unread')}>Unread</button><button className={filter === 'read' ? 'selected' : ''} onClick={() => setFilter('read')}>Read</button></div>} />{message && <div className="notice"><CircleCheck size={16} />{message}<button className="notice-close" aria-label="Dismiss" onClick={() => setMessage('')}><X size={15} /></button></div>}<Panel title="Alert feed" subtitle={`${data?.length ?? '—'} ${demoMode ? 'example' : 'stored'} alerts`}>{loading && !data ? <LoadingState slow={slow} /> : error ? <ErrorState message={error} onRetry={reload} /> : rows.length ? <div className="alert-list">{rows.map((alert) => <AlertCard key={alert.id} alert={alert} busy={busyId === alert.id} onRead={() => markRead(alert.id)} />)}</div> : <EmptyState icon={Bell} title={filter === 'unread' ? 'No unread alerts' : 'No alerts received'} text="Alerts are created only in response to submitted device or inference events." />}</Panel></>;
}
function AlertCard({ alert, busy, onRead }) { const low = ['LOW_BATTERY', 'LOW_WATER', 'DRY_SOIL', 'SENSOR_FAILURE', 'ROBOT_OFFLINE', 'SYSTEM_ERROR'].includes(alert.alert_type); return <article className={`alert-card ${alert.is_read ? 'read' : ''}`}><span className={`alert-symbol ${low ? 'alert-warn' : 'alert-info'}`}>{low ? <AlertTriangle size={18} /> : <Bell size={18} />}</span><div className="alert-copy"><div className="alert-title-line"><strong>{alert.message}</strong>{!alert.is_read && <span className="unread-dot" title="Unread" />}</div><div className="alert-meta"><Badge kind={low ? 'badge-amber' : 'badge-gray'}>{alert.alert_type?.replaceAll('_', ' ')}</Badge>{alert.robot_id && <span>{alert.robot_id}</span>}{alert.plant_id && <span>Plant #{alert.plant_id}</span>}<span>{timestamp(alert.created_at)}</span></div>{alert.details && <small className="alert-detail">{Object.entries(alert.details).map(([key, value]) => `${key.replaceAll('_', ' ')}: ${value}`).join(' · ')}</small>}</div>{!alert.is_read && <button className="button button-secondary button-small" onClick={onRead} disabled={busy}>{busy ? <LoaderCircle size={14} className="spin" /> : <Check size={14} />} Mark read</button>}</article>; }

function History({ token, demoMode, alertState }) {
  const data = useLookups(token, demoMode);
  const [query, setQuery] = useState('');
  const allEvents = [ ...(data.detections.data || []).map((x) => ({ when: x.detected_at, kind: 'Detection', subject: x.class_name?.replaceAll('_', ' '), context: x.plant_id ? `Plant #${x.plant_id}` : 'Plant not linked', confidence: x.confidence_status })), ...(data.watering.data || []).map((x) => ({ when: x.started_at, kind: 'Watering', subject: `${x.robot_id} watering event`, context: x.trigger_source || 'Source not specified', confidence: '' })), ...(data.telemetry.data || []).map((x) => ({ when: x.recorded_at, kind: 'Telemetry', subject: `${x.robot_id} · ${x.robot_state || 'State unavailable'}`, context: x.latitude != null && x.longitude != null ? `${x.latitude}, ${x.longitude}` : 'Location unavailable', confidence: '' })), ...(alertState.data || []).map((x) => ({ when: x.created_at, kind: 'Alert', subject: x.message, context: x.alert_type?.replaceAll('_', ' '), confidence: x.is_read ? 'Read' : 'Unread' })) ].sort((a, b) => new Date(b.when) - new Date(a.when));
  const filtered = allEvents.filter((x) => `${x.kind} ${x.subject} ${x.context}`.toLowerCase().includes(query.toLowerCase()));
  const loading = Object.values(data).some((x) => x.loading && x.data === null) || (alertState.loading && !alertState.data);
  const error = Object.values(data).find((x) => x.error)?.error || alertState.error;
  function exportAll() { const events = allEvents.map(({ when, ...row }) => ({ recorded_at: when, ...(demoMode ? { data_mode: 'DEMO' } : {}), ...row })); if (!saveCsv(demoMode ? 'flora-bot-demo-event-history.csv' : 'flora-bot-event-history.csv', events)) window.alert('There are no records to export.'); }
  return <><PageIntro eyebrow="OPERATIONAL RECORDS" title="Reports & history" description={demoMode ? "Review and export the example event history." : "Review and export detections, watering, rover and alert history."} action={<button className="button button-secondary" onClick={exportAll} disabled={!allEvents.length}><Download size={16} /> Export CSV</button>} /><div className="history-summary"><HistoryCount label="Inference results" value={data.detections.data?.length} icon={ScanLine} /><HistoryCount label="Watering events" value={data.watering.data?.length} icon={Droplets} /><HistoryCount label="Alerts" value={alertState.data?.length} icon={Bell} /><HistoryCount label="Rover updates" value={data.telemetry.data?.length} icon={Tractor} /></div><Panel title="Event history" subtitle="Events are ordered by timestamp, newest first" action={<div className="table-search"><Search size={15} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search history" aria-label="Search history" /></div>}>{loading ? <LoadingState slow={alertState.slow || Object.values(data).some((x) => x.slow)} /> : error ? <ErrorState message={error} onRetry={() => { Object.values(data).forEach((item) => item.reload()); alertState.reload(); }} /> : filtered.length ? <div className="table-wrap"><table><thead><tr><th>Timestamp</th><th>Event</th><th>Record</th><th>Details</th><th>Status</th></tr></thead><tbody>{filtered.slice(0, 500).map((event, i) => <tr key={`${event.kind}-${event.when}-${i}`}><td>{timestamp(event.when)}</td><td><Badge kind={event.kind === 'Alert' ? 'badge-amber' : event.kind === 'Detection' ? 'badge-blue' : 'badge-green'}>{event.kind}</Badge></td><td className="table-primary">{event.subject}</td><td>{event.context}</td><td>{event.confidence || '—'}</td></tr>)}</tbody></table></div> : <EmptyState icon={FileClock} title="No history to display" text="Historical views populate from detections, alerts, watering and rover telemetry records." />}</Panel>{!demoMode && <div className="info-banner"><ShieldCheck size={17} /><span>Event records are retrieved from backend history endpoints.</span></div>}</>;
}
function HistoryCount({ label, value, icon: Icon }) { return <div className="history-count"><span><Icon size={17} /></span><small>{label}</small><strong>{value ?? '—'}</strong></div>; }

function Settings({ token, user, demoMode, onDemoModeChange }) {
  const [health, setHealth] = useState({ state: 'checking', value: null });
  const [baseUrl] = useState(import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000');
  const inference = useLoad((signal) => api.inferenceStatus(token, signal), [token]);
  useEffect(() => { const controller = new AbortController(); api.health(controller.signal).then((value) => setHealth({ state: 'connected', value })).catch((error) => setHealth({ state: 'unavailable', value: error.message })); return () => controller.abort(); }, []);
  const inferenceStatus = inference.error ? 'Unavailable' : inference.data?.available ? 'Available' : inference.data ? inference.data.reason || 'Unavailable' : 'Checking';
  return <><PageIntro eyebrow="WORKSPACE PREFERENCES" title="Settings" description="Review account, demo mode and frontend connection configuration." /><div className="settings-grid"><Panel title="Account" subtitle="Authenticated backend profile"><div className="account-card"><span className="account-avatar"><UserRound size={22} /></span><div><strong>{user?.full_name}</strong><small>{user?.email}</small></div><Badge kind="badge-green">{user?.role}</Badge></div><div className="settings-detail"><span>Authentication</span><strong>Bearer token · session storage</strong></div><div className="settings-detail"><span>Token management</span><strong>Token expires according to backend policy</strong></div></Panel><Panel title="Demo mode" subtitle="Try the interface with an isolated example workspace"><label className="demo-switch"><span><strong>Use demonstration data</strong><small>Example crops, alerts, rover telemetry and coordinates stay in this browser. Changes do not reach PostgreSQL.</small></span><input type="checkbox" checked={demoMode} onChange={(event) => onDemoModeChange(event.target.checked)} aria-label="Use demonstration data" /></label><p className="settings-help">Switch off to return to records from the authenticated backend. Demo edits reset when this page is reloaded.</p></Panel><Panel title="API connection" subtitle="Public API base URL and health response"><div className="connection-box"><span className={`connection-icon ${health.state}`}><Wifi size={18} /></span><span><strong>{health.state === 'connected' ? 'Backend responded' : health.state === 'unavailable' ? 'Backend unavailable' : 'Checking connection'}</strong><small>{health.state === 'connected' ? 'Health endpoint returned a response.' : health.state === 'unavailable' ? health.value : 'Checking /health'}</small></span><Badge kind={health.state === 'connected' ? 'badge-green' : health.state === 'unavailable' ? 'badge-red' : 'badge-gray'}>{health.state}</Badge></div><div className="settings-detail"><span>API base URL</span><strong className="mono">{baseUrl}</strong></div><div className="settings-detail"><span>Polling interval</span><strong>{Math.round(POLL_MS / 1000)} seconds while this tab is active</strong></div><p className="settings-help">Set <code>VITE_API_BASE_URL</code> in the frontend environment and restart Vite to change the API target. Health status confirms only that the API process responded; it does not verify PostgreSQL or hardware connectivity.</p></Panel></div><Panel title="Integration availability" subtitle="Current backend capabilities"><div className="integration-list"><IntegrationRow label="JWT authentication" status="Available" /><IntegrationRow label="REST data endpoints" status="Available" /><IntegrationRow label="Local disease inference" status={inferenceStatus} muted={!inference.data?.available} /><IntegrationRow label="WebSocket / SSE updates" status="Not exposed" muted /><IntegrationRow label="Manual pump control" status="Not exposed" muted /><IntegrationRow label="Hardware connection status" status="Not exposed" muted /></div></Panel></>;
}
function IntegrationRow({ label, status, muted }) { return <div className="integration-row"><span className={muted ? 'integration-muted' : 'integration-check'}>{muted ? <CircleHelp size={15} /> : <CircleCheck size={15} />}</span><span>{label}</span><small>{status}</small></div>; }
