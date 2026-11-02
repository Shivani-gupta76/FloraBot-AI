import { useCallback, useEffect, useState } from 'react';
import { NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import {
  AlertTriangle, ArrowRight, ArrowUpRight, Bell, Camera, ChevronDown,
  ChevronLeft, ChevronRight, CircleHelp, Cloud, FileClock,
  Leaf, LogOut, MapPin, Menu, Plus, Search, Settings as SettingsIcon, ShieldCheck,
  Sprout, Wifi, X, Check, LayoutDashboard,
  ScanLine, Download, Pencil, Trash2, RefreshCw,
  CircleCheck, CircleAlert, LoaderCircle, LockKeyhole, Mail, UserRound, MessageCircle,
} from 'lucide-react';
import { api, saveCsv, timestamp } from './api.js';
import { useLoad } from './useLoad.js';
const NAV = [
  { label: 'Overview', to: '/', icon: LayoutDashboard },
  { label: 'Crop management', to: '/crops', icon: Sprout },
  { label: 'Disease detection', to: '/detections', icon: ScanLine },
  { label: 'Plant care assistant', to: '/assistant', icon: MessageCircle },
  { label: 'Disease Alerts', to: '/alerts', icon: Bell },
  { label: 'Reports & history', to: '/history', icon: FileClock },
  { label: 'Settings', to: '/settings', icon: SettingsIcon },
];
const POLL_MS = Math.max(30_000, Number(import.meta.env.VITE_POLL_INTERVAL_MS) || 60_000);
const API_DOCS_URL = `${(import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')}/docs`;
const CHATBOT_URL = import.meta.env.VITE_CHATBOT_URL || 'http://127.0.0.1:8010/';
const EMPTY_LIST = [];

export default function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem('flora_token'));
  const [user, setUser] = useState(null);
  const [authChecking, setAuthChecking] = useState(Boolean(sessionStorage.getItem('flora_token')));
  const [authError, setAuthError] = useState('');
  const navigate = useNavigate();

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
  return <DashboardShell token={token} user={user} onSignOut={signOut} />;
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
      <div className="auth-aside"><div className="auth-aside-content"><div className="aside-icon"><Leaf size={20} /></div><p className="eyebrow">FIELD INTELLIGENCE, CONNECTED</p><h2>A clearer picture of every growing day.</h2><p>Bring crop records and disease observations into one considered workspace.</p><div className="aside-footer"><span><span className="pulse-dot" /> Live data appears when your backend receives it</span><span>Flora-Bot · Crop Care</span></div></div></div>
    </main>
  );
}

function BrandMark({ large = false }) {
  return <div className={`brand ${large ? 'brand-large' : ''}`}><span className="brand-icon"><Leaf size={large ? 23 : 20} strokeWidth={2.1} /></span><span><strong>Flora-Bot</strong><small>Crop Care Intelligence</small></span></div>;
}

function DashboardShell({ token, user, onSignOut }) {
  const [collapsed, setCollapsed] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [network, setNetwork] = useState('checking');
  const alertState = useLoad((signal) => api.alerts(token, signal), [token]);
  const alertCount = alertState.data?.filter((item) => isDiseaseAlert(item) && !item.is_read).length ?? null;
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
        <nav className="sidebar-nav" aria-label="Main navigation">{NAV.map(({ label, to, icon: Icon }) => <NavLink key={to} to={to} end={to === '/'} title={collapsed ? label : undefined} onClick={() => setDrawer(false)} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}><Icon size={18} strokeWidth={1.8} /><span>{label}</span>{label === 'Disease Alerts' && alertCount > 0 && <em className="nav-count">{alertCount}</em>}</NavLink>)}</nav>
        <div className="sidebar-bottom"><a className="help-card" href={API_DOCS_URL} target="_blank" rel="noopener noreferrer" aria-label="Open Flora-Bot API documentation in a new tab"><span className="help-icon"><CircleHelp size={17} /></span><div><strong>Need a hand?</strong><small>Explore the API guide</small></div><ArrowRight size={15} /></a><div className="sidebar-user"><span className="avatar">{user?.full_name?.slice(0, 1)?.toUpperCase() || 'F'}</span><div className="sidebar-user-text"><strong>{user?.full_name || 'Flora-Bot user'}</strong><small>{user?.role || 'Operator'}</small></div><button className="icon-button logout-button" aria-label="Sign out" title="Sign out" onClick={onSignOut}><LogOut size={16} /></button></div></div>
      </aside>
      <div className="main-area">
        <header className="topbar"><button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setDrawer(true)}><Menu size={20} /></button><div className="page-heading"><span className="breadcrumb">Workspace <ChevronRight size={13} /> {page.label}</span><h1>{page.label}</h1></div><div className="topbar-actions"><div className={`api-status ${network}`} title={network === 'connected' ? 'Backend health endpoint responded' : network === 'unavailable' ? 'Backend health endpoint is unavailable' : 'Checking backend'}><span className="status-dot" />{network === 'connected' ? 'API connected' : network === 'unavailable' ? 'API unavailable' : 'Checking API'}</div><NavLink className="icon-button notification-button" to="/alerts" aria-label="Disease Alerts"><Bell size={18} />{alertCount > 0 && <i>{alertCount > 9 ? '9+' : alertCount}</i>}</NavLink><div className="top-user"><span className="avatar small-avatar">{user?.full_name?.slice(0, 1)?.toUpperCase() || 'F'}</span><span>{user?.full_name?.split(' ')[0] || 'Account'}</span><ChevronDown size={14} /><button className="user-logout" onClick={onSignOut}>Sign out</button></div></div></header>
        <main className="content"><Routes><Route path="/" element={<Overview token={token} alertState={alertState} />} /><Route path="/crops" element={<Crops token={token} />} /><Route path="/detections" element={<Detections token={token} />} /><Route path="/assistant" element={<PlantCareAssistant />} /><Route path="/alerts" element={<Alerts token={token} alertState={alertState} />} /><Route path="/history" element={<History token={token} alertState={alertState} />} /><Route path="/settings" element={<Settings token={token} user={user} />} /><Route path="*" element={<Overview token={token} alertState={alertState} />} /></Routes><footer className="page-footer"><span>Flora-Bot · Crop Care Intelligence</span><span>Dashboard refreshes periodically when the page is active</span></footer></main>
      </div>
    </div>
  );
}

function PlantCareAssistant() {
  return (
    <section className="assistant-page" aria-label="Plant care assistant">
      <div className="assistant-heading">
        <div><p className="eyebrow">FLORABOT AI</p><h2>Plant care assistant</h2><p>Ask about a plant or share an image with the FloraBOT assistant.</p></div>
        <a className="button button-secondary" href={CHATBOT_URL} target="_blank" rel="noopener noreferrer">Open in new tab <ArrowUpRight size={15} /></a>
      </div>
      <div className="assistant-frame-wrap"><iframe className="assistant-frame" src={CHATBOT_URL} title="FloraBOT plant care chatbot" loading="lazy" referrerPolicy="strict-origin-when-cross-origin" /></div>
    </section>
  );
}

function PageIntro({ eyebrow, title, description, action }) { return <div className="page-intro"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2><p>{description}</p></div>{action}</div>; }
function Panel({ title, subtitle, action, children, className = '' }) { return <section className={`panel ${className}`}><div className="panel-head"><div><h3>{title}</h3>{subtitle && <p>{subtitle}</p>}</div>{action}</div>{children}</section>; }
function EmptyState({ icon: Icon = Cloud, title = 'No data available', text = 'No records have been received yet. Data will appear here after the backend receives it.' }) { return <div className="empty-state"><span className="empty-icon"><Icon size={20} /></span><strong>{title}</strong><p>{text}</p></div>; }
function LoadingState({ slow = false }) { return <div className="loading-state"><LoaderCircle size={19} className="spin" /><span>{slow ? 'This is taking longer than usual…' : 'Loading records…'}</span></div>; }
function ErrorState({ message, onRetry }) { return <div className="error-state"><CircleAlert size={18} /><span>{message}</span>{onRetry && <button className="text-button" onClick={() => onRetry()}>Retry</button>}</div>; }
function Badge({ children, kind = '' }) { return <span className={`badge ${kind}`}>{children}</span>; }
function useLookups(token) {
  const plants = useLoad((signal) => api.plants(token, signal), [token]);
  const detections = useLoad((signal) => api.detections(token, signal), [token]);
  return { plants, detections };
}
function isDiseaseAlert(alert) { return ['DISEASE_DETECTED', 'LOW_CONFIDENCE_DETECTION'].includes(alert?.alert_type); }
function diseaseAlertDetails(alert, detections, plants) {
  const detection = detections.find((row) => row.id === alert.details?.detection_id);
  const plant = plants.find((row) => row.id === alert.plant_id);
  const className = detection?.class_name || alert.details?.class_name;
  return {
    name: className ? className.replaceAll('_', ' ') : 'Unavailable',
    crop: plant?.crop_type || (alert.plant_id ? `Crop #${alert.plant_id}` : 'Not linked'),
    confidence: Number.isFinite(detection?.confidence) ? `${(detection.confidence * 100).toFixed(1)}%` : 'Unavailable',
  };
}
function Overview({ token, alertState }) {
  const data = useLookups(token);
  const plants = data.plants.data || EMPTY_LIST;
  const detections = data.detections.data || EMPTY_LIST;
  const diseaseAlerts = (alertState.data || EMPTY_LIST).filter(isDiseaseAlert);
  const recentDetections = [...detections].sort((a, b) => new Date(b.detected_at) - new Date(a.detected_at)).slice(0, 5);
  const recentAlerts = [...diseaseAlerts].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 5);
  return <>
    <div className="welcome-row"><div><p className="eyebrow">FIELD OVERVIEW</p><h2>Your crops, at a glance.</h2><p>Live operational data from your Flora-Bot workspace.</p></div><div className="last-refresh"><span className="refresh-mark"><RefreshCw size={14} /></span><span>Updates every {Math.round(POLL_MS / 1000)} seconds</span></div></div>
    {(Object.values(data).some((item) => item.error) || alertState.error) && <ErrorState message="Some dashboard data could not be loaded. Values shown are limited to the data received." />}
    <section className="metric-grid">
      <Metric title="Registered crops" value={data.plants.data === null ? '—' : plants.length} note="Plant records" icon={Sprout} tint="green" href="/crops" />
      <Metric title="Disease detections" value={data.detections.data === null ? '—' : detections.length} note="Inference results received" icon={ScanLine} tint="amber" href="/detections" />
      <Metric title="Disease Alerts" value={alertState.data === null ? '—' : diseaseAlerts.length} note="Disease notifications" icon={Bell} tint="blue" href="/alerts" />
      <Metric title="Camera connection" value="Unavailable" note="Awaiting hardware integration" icon={Camera} tint="olive" href="/detections" compact />
    </section>
    <section className="overview-grid">
      <Panel className="detections-panel" title="Recent Disease Detections" subtitle="Latest results received from the inference service" action={<NavLink className="panel-link" to="/detections">View all <ArrowRight size={14} /></NavLink>}>
        {data.detections.loading && !data.detections.data ? <LoadingState slow={data.detections.slow} /> : data.detections.error ? <ErrorState message={data.detections.error} onRetry={data.detections.reload} /> : recentDetections.length ? <DetectionList rows={recentDetections} plants={plants} /> : <EmptyState icon={ScanLine} title="Waiting for images from ESP32-CAM." text="Disease detection results will appear after images are sent to the backend." />}
      </Panel>
      <Panel title="Recent Disease Alerts" subtitle="Latest disease notifications" action={<NavLink className="panel-link" to="/alerts">View all <ArrowRight size={14} /></NavLink>}>
        {alertState.loading && !alertState.data ? <LoadingState slow={alertState.slow} /> : alertState.error ? <ErrorState message={alertState.error} onRetry={alertState.reload} /> : recentAlerts.length ? <DiseaseAlertList rows={recentAlerts} detections={detections} plants={plants} /> : <EmptyState icon={Bell} title="No disease alerts" text="Disease alerts will appear here when the backend records them." />}
      </Panel>
    </section>
  </>;
}

function Metric({ title, value, note, icon: Icon, tint, href, compact }) { return <NavLink to={href} className="metric-card"><div className={`metric-icon ${tint}`}><Icon size={19} /></div><span className="metric-title">{title}</span><strong className={compact ? 'metric-value compact-value' : 'metric-value'}>{value}</strong><span className="metric-note">{note}</span><ArrowUpRight className="metric-arrow" size={15} /></NavLink>; }
function DetectionList({ rows, plants = [] }) { const plantMap = new Map(plants.map((item) => [item.id, item])); return <div className="detection-list">{rows.map((row) => { const isHealthy = row.class_name?.endsWith('_Healthy'); return <div className="detection-row" key={row.id}><span className={`detection-symbol ${isHealthy ? 'healthy' : 'flagged'}`}>{isHealthy ? <Leaf size={17} /> : <AlertTriangle size={17} />}</span><div className="detection-main"><strong>{row.class_name?.replaceAll('_', ' ') || 'Unknown class'}</strong><span>{row.plant_id ? plantMap.get(row.plant_id)?.crop_type || `Crop #${row.plant_id}` : 'Not linked'} · {timestamp(row.detected_at)}</span></div><div className="detection-meta"><Badge kind={confidenceKind(row.confidence_status)}>{row.confidence_status?.replaceAll('_', ' ') || 'Status unavailable'}</Badge><span>{Number.isFinite(row.confidence) ? `${(row.confidence * 100).toFixed(1)}%` : 'Confidence unavailable'}</span></div></div>; })}</div>; }
function DiseaseAlertList({ rows, detections, plants }) {
  return <div className="detection-list">{rows.map((alert) => {
    const detail = diseaseAlertDetails(alert, detections, plants);
    return <div className="detection-row" key={alert.id}><span className="detection-symbol flagged"><AlertTriangle size={17} /></span><div className="detection-main"><strong>{detail.name}</strong><span>{detail.crop} · {timestamp(alert.created_at)}</span></div><div className="detection-meta"><Badge kind={alert.is_read ? 'badge-gray' : 'badge-amber'}>{alert.is_read ? 'Read' : 'Unread'}</Badge><span>{detail.confidence}</span></div></div>;
  })}</div>;
}
function confidenceKind(value) { return value === 'HIGH_CONFIDENCE' ? 'badge-green' : value === 'REVIEW_RECOMMENDED' ? 'badge-amber' : value === 'UNCERTAIN' ? 'badge-gray' : ''; }

function Crops({ token }) {
  const { data, loading, slow, error, reload } = useLoad((signal) => api.plants(token, signal), [token]);
  const [query, setQuery] = useState(''), [modal, setModal] = useState(null), [feedback, setFeedback] = useState('');
  const [busy, setBusy] = useState(false);
  const rows = (data || EMPTY_LIST).filter((plant) => `${plant.crop_type} ${plant.variety || ''} ${plant.field_area || ''} ${plant.health_status || ''}`.toLowerCase().includes(query.toLowerCase()));
  async function save(event) {
    event.preventDefault(); setBusy(true); setFeedback(''); const fd = new FormData(event.currentTarget);
    const nullableNumber = (value) => value === '' ? null : Number(value);
    const body = { crop_type: String(fd.get('crop_type')).trim(), variety: String(fd.get('variety')).trim() || null, field_area: String(fd.get('field_area')).trim() || null, latitude: nullableNumber(fd.get('latitude')), longitude: nullableNumber(fd.get('longitude')), health_status: String(fd.get('health_status')).trim() || null };
    try {
      if (modal?.id) await api.updatePlant(token, modal.id, body); else await api.createPlant(token, body);
      setModal(null); setFeedback(modal?.id ? 'Crop record updated.' : 'Crop record added.'); await reload({ force: true });
    }
    catch (e) { setFeedback(e.message); } finally { setBusy(false); }
  }
  async function remove(plant) { if (!window.confirm(`Delete crop record #${plant.id}? This action cannot be undone.`)) return; setFeedback(''); try { await api.deletePlant(token, plant.id); setFeedback('Crop record deleted.'); await reload({ force: true }); } catch (e) { setFeedback(e.message); } }
  return <>
    <PageIntro eyebrow="CROP REGISTRY" title="Crop management" description="Manage crop and plant records registered in your workspace." action={<button className="button button-primary" onClick={() => setModal({})}><Plus size={17} /> Add crop</button>} />
    {feedback && <div className="notice"><CircleCheck size={16} />{feedback}<button className="notice-close" aria-label="Dismiss" onClick={() => setFeedback('')}><X size={15} /></button></div>}
    <Panel title="Registered crops" subtitle={`${data?.length ?? '—'} records in the workspace`} action={<div className="table-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search crops" aria-label="Search crops" /></div>}>
      {loading && !data ? <LoadingState slow={slow} /> : error ? <ErrorState message={error} onRetry={reload} /> : rows.length ? <div className="table-wrap"><table><thead><tr><th>Crop / variety</th><th>Field / area</th><th>Location</th><th>Health status</th><th>Last scanned</th><th>Last watered</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{rows.map((plant) => <tr key={plant.id}><td><span className="table-primary">{plant.crop_type}</span><small>{plant.variety || 'Variety not specified'} · #{plant.id}</small></td><td>{plant.field_area || 'Not specified'}</td><td>{plant.latitude != null && plant.longitude != null ? <span className="coordinate"><MapPin size={13} />{plant.latitude.toFixed(4)}, {plant.longitude.toFixed(4)}</span> : <span className="muted">Unavailable</span>}</td><td>{plant.health_status ? <Badge kind="badge-gray">{plant.health_status}</Badge> : <span className="muted">Not reported</span>}</td><td>{plant.last_scanned_at ? timestamp(plant.last_scanned_at) : <span className="muted">Not scanned</span>}</td><td>{plant.last_watered_at ? timestamp(plant.last_watered_at) : <span className="muted">Not recorded</span>}</td><td><div className="row-actions"><button className="icon-button" title="Edit crop" aria-label={`Edit ${plant.crop_type}`} onClick={() => setModal(plant)}><Pencil size={15} /></button><button className="icon-button danger-icon" title="Delete crop (Admin only)" aria-label={`Delete ${plant.crop_type}`} onClick={() => remove(plant)}><Trash2 size={15} /></button></div></td></tr>)}</tbody></table></div> : <EmptyState icon={Sprout} title={query ? 'No matching crops' : 'No crop records yet'} text={query ? 'Try another crop, variety or area.' : 'Register a crop to start building your field record. No crops are added automatically.'} />}
    </Panel>
    {modal && <Modal title={modal.id ? 'Edit crop record' : 'Register a crop'} close={() => setModal(null)}><form className="form-grid" onSubmit={save}><label>Crop type <input name="crop_type" required maxLength="100" defaultValue={modal.crop_type || ''} placeholder="e.g. Tomato" /></label><label>Variety <input name="variety" defaultValue={modal.variety || ''} placeholder="Optional variety" /></label><label className="field-span">Field / area <input name="field_area" defaultValue={modal.field_area || ''} placeholder="Field or growing area name" /></label><label>Latitude <input name="latitude" type="number" step="any" min="-90" max="90" defaultValue={modal.latitude ?? ''} placeholder="Optional GPS latitude" /></label><label>Longitude <input name="longitude" type="number" step="any" min="-180" max="180" defaultValue={modal.longitude ?? ''} placeholder="Optional GPS longitude" /></label><label className="field-span">Health status <input name="health_status" defaultValue={modal.health_status || ''} placeholder="Optional observed status" /></label><div className="form-actions field-span"><button type="button" className="button button-secondary" onClick={() => setModal(null)}>Cancel</button><button className="button button-primary" disabled={busy}>{busy ? <LoaderCircle size={16} className="spin" /> : <Check size={16} />}{modal.id ? 'Save changes' : 'Create crop'}</button></div>{feedback && <div className="inline-error field-span">{feedback}</div>}</form></Modal>}
  </>;
}

function Modal({ title, children, close }) { useEffect(() => { const onKey = (event) => { if (event.key === 'Escape') close(); }; window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey); }, [close]); return <div className="modal-scrim" onMouseDown={(event) => { if (event.target === event.currentTarget) close(); }}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div className="modal-head"><div><p className="eyebrow">CROP REGISTRY</p><h3 id="modal-title">{title}</h3></div><button className="icon-button" aria-label="Close dialog" onClick={close}><X size={18} /></button></div>{children}</section></div>; }

function Detections({ token }) {
  const { data, loading, slow, error, reload } = useLoad((signal) => api.detections(token, signal), [token]);
  const plantsQuery = useLoad((signal) => api.plants(token, signal), [token]);
  const [query, setQuery] = useState(''), [confidence, setConfidence] = useState('all');
  const rows = (data || EMPTY_LIST).filter((item) => (confidence === 'all' || item.confidence_status === confidence) && `${item.class_name} ${item.model_version || ''} ${item.plant_id || ''}`.toLowerCase().includes(query.toLowerCase())).sort((a, b) => new Date(b.detected_at) - new Date(a.detected_at));
  const plants = plantsQuery.data || EMPTY_LIST;
  return <><PageIntro eyebrow="INFERENCE RECORDS" title="Disease detection" description="Detection results received from the backend." /><Panel title="Disease detection history" subtitle={`${data?.length ?? '—'} results received`} action={<div className="table-tools"><div className="table-search"><Search size={15} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search class or plant" aria-label="Search detections" /></div><select aria-label="Filter by confidence status" value={confidence} onChange={(e) => setConfidence(e.target.value)}><option value="all">All confidence states</option><option value="HIGH_CONFIDENCE">High confidence</option><option value="REVIEW_RECOMMENDED">Review recommended</option><option value="UNCERTAIN">Uncertain</option></select></div>}>
    {loading && !data ? <LoadingState slow={slow} /> : error ? <ErrorState message={error} onRetry={reload} /> : rows.length ? <div className="table-wrap"><table><thead><tr><th>Predicted class</th><th>Crop</th><th>Confidence</th><th>Date and time</th><th>Model</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td><span className="table-primary">{row.class_name.replaceAll('_', ' ')}</span><small>Prediction · #{row.id}</small></td><td>{row.plant_id ? plants.find((plant) => plant.id === row.plant_id)?.crop_type || `Crop #${row.plant_id}` : 'Not linked'}</td><td><div className="confidence-cell"><Badge kind={confidenceKind(row.confidence_status)}>{row.confidence_status?.replaceAll('_', ' ') || 'Unavailable'}</Badge><strong>{Number.isFinite(row.confidence) ? `${(row.confidence * 100).toFixed(1)}%` : 'Unavailable'}</strong></div></td><td>{timestamp(row.detected_at)}</td><td>{row.model_version || 'Not provided'}</td></tr>)}</tbody></table></div> : <EmptyState icon={ScanLine} title={query || confidence !== 'all' ? 'No matching detections' : 'Waiting for images from ESP32-CAM.'} text={query || confidence !== 'all' ? 'Change your search or status filter.' : 'New detection results will appear here after images are sent to FastAPI.'} />}
  </Panel><div className="info-banner"><ShieldCheck size={17} /><span><strong>Inference records are not diagnoses.</strong> Confidence labels reflect submitted classifier output; agronomic review may still be appropriate.</span></div></>;
}
function Alerts({ token, alertState }) {
  const lookups = useLookups(token);
  const detections = lookups.detections.data || EMPTY_LIST;
  const plants = lookups.plants.data || EMPTY_LIST;
  const { data, loading, slow, error, reload } = alertState;
  const [filter, setFilter] = useState('all'), [busyId, setBusyId] = useState(null), [message, setMessage] = useState('');
  const rows = (data || EMPTY_LIST).filter(isDiseaseAlert).filter((item) => filter === 'all' || (filter === 'unread' ? !item.is_read : item.is_read));
  async function markRead(id) {
    setBusyId(id); setMessage('');
    try { await api.markAlertRead(token, id); await reload({ force: true }); setMessage('Disease alert marked as read.'); }
    catch (failure) { setMessage(failure.message); }
    finally { setBusyId(null); }
  }
  const lookupError = lookups.plants.error || lookups.detections.error;
  return <><PageIntro eyebrow="DISEASE NOTIFICATIONS" title="Disease Alerts" description="Review disease notifications recorded by the backend." action={<div className="segmented"><button className={filter === 'all' ? 'selected' : ''} onClick={() => setFilter('all')}>All</button><button className={filter === 'unread' ? 'selected' : ''} onClick={() => setFilter('unread')}>Unread</button><button className={filter === 'read' ? 'selected' : ''} onClick={() => setFilter('read')}>Read</button></div>} />
    {message && <div className="notice"><CircleCheck size={16} />{message}<button className="notice-close" aria-label="Dismiss" onClick={() => setMessage('')}><X size={15} /></button></div>}
    <Panel title="Disease alert feed" subtitle={`${rows.length} ${filter === 'all' ? 'disease' : filter} alerts`}>
      {loading && !data ? <LoadingState slow={slow} /> : error ? <ErrorState message={error} onRetry={reload} /> : lookupError ? <ErrorState message={lookupError} onRetry={() => { lookups.plants.reload(); lookups.detections.reload(); }} /> : rows.length ? <div className="table-wrap"><table><thead><tr><th>Disease detected</th><th>Disease name</th><th>Crop name</th><th>Confidence</th><th>Date and time</th><th>Alert status</th></tr></thead><tbody>{rows.map((alert) => { const detail = diseaseAlertDetails(alert, detections, plants); return <tr key={alert.id}><td>Disease detected</td><td className="table-primary">{detail.name}</td><td>{detail.crop}</td><td>{detail.confidence}</td><td>{timestamp(alert.created_at)}</td><td><div className="alert-status-cell"><Badge kind={alert.is_read ? 'badge-gray' : 'badge-amber'}>{alert.is_read ? 'Read' : 'Unread'}</Badge>{!alert.is_read && <button className="button button-secondary button-small" onClick={() => markRead(alert.id)} disabled={busyId === alert.id}>{busyId === alert.id ? <LoaderCircle size={14} className="spin" /> : <Check size={14} />} Mark read</button>}</div></td></tr>; })}</tbody></table></div> : <EmptyState icon={Bell} title={filter === 'unread' ? 'No unread disease alerts' : filter === 'read' ? 'No read disease alerts' : 'No disease alerts'} text="Disease alerts will appear when the backend records a disease detection." />}
    </Panel>
  </>;
}

function History({ token, alertState }) {
  const data = useLookups(token);
  const [query, setQuery] = useState('');
  const detections = data.detections.data || EMPTY_LIST;
  const plants = data.plants.data || EMPTY_LIST;
  const diseaseAlerts = (alertState.data || EMPTY_LIST).filter(isDiseaseAlert);
  const allEvents = [
    ...detections.map((row) => ({ when: row.detected_at, kind: 'Disease detection', subject: row.class_name?.replaceAll('_', ' ') || 'Unavailable', context: plants.find((plant) => plant.id === row.plant_id)?.crop_type || (row.plant_id ? `Crop #${row.plant_id}` : 'Crop not linked'), confidence: Number.isFinite(row.confidence) ? `${(row.confidence * 100).toFixed(1)}%` : 'Unavailable', status: row.confidence_status || 'Unavailable' })),
    ...diseaseAlerts.map((alert) => { const detail = diseaseAlertDetails(alert, detections, plants); return { when: alert.created_at, kind: 'Disease alert', subject: detail.name, context: detail.crop, confidence: detail.confidence, status: alert.is_read ? 'Read' : 'Unread' }; }),
  ].sort((a, b) => new Date(b.when) - new Date(a.when));
  const filtered = allEvents.filter((event) => `${event.kind} ${event.subject} ${event.context} ${event.status}`.toLowerCase().includes(query.toLowerCase()));
  const loading = Object.values(data).some((item) => item.loading && item.data === null) || (alertState.loading && !alertState.data);
  const error = Object.values(data).find((item) => item.error)?.error || alertState.error;
  function exportAll() { const events = allEvents.map(({ when, ...row }) => ({ recorded_at: when, ...row })); if (!saveCsv('flora-bot-disease-history.csv', events)) window.alert('There are no disease records to export.'); }
  return <><PageIntro eyebrow="OPERATIONAL RECORDS" title="Reports & history" description="Review and export disease detection and alert history." action={<button className="button button-secondary" onClick={exportAll} disabled={!allEvents.length}><Download size={16} /> Export CSV</button>} />
    <div className="history-summary"><HistoryCount label="Disease detections" value={data.detections.data?.length} icon={ScanLine} /><HistoryCount label="Disease alerts" value={alertState.data?.filter(isDiseaseAlert).length} icon={Bell} /><HistoryCount label="Crops" value={data.plants.data?.length} icon={Sprout} /><HistoryCount label="Unread alerts" value={alertState.data?.filter((alert) => isDiseaseAlert(alert) && !alert.is_read).length} icon={Bell} /></div>
    <Panel title="Disease history" subtitle="Detection and disease alert records, newest first" action={<div className="table-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search history" aria-label="Search history" /></div>}>
      {loading ? <LoadingState slow={alertState.slow || Object.values(data).some((item) => item.slow)} /> : error ? <ErrorState message={error} onRetry={() => { Object.values(data).forEach((item) => item.reload()); alertState.reload(); }} /> : filtered.length ? <div className="table-wrap"><table><thead><tr><th>Date and time</th><th>Record</th><th>Disease / crop</th><th>Confidence</th><th>Status</th></tr></thead><tbody>{filtered.slice(0, 500).map((event, index) => <tr key={`${event.kind}-${event.when}-${index}`}><td>{timestamp(event.when)}</td><td><Badge kind={event.kind === 'Disease alert' ? 'badge-amber' : 'badge-blue'}>{event.kind}</Badge></td><td><span className="table-primary">{event.subject}</span><small>{event.context}</small></td><td>{event.confidence}</td><td>{event.status}</td></tr>)}</tbody></table></div> : <EmptyState icon={FileClock} title="No disease history to display" text="Disease detection and alert history will appear here when records are received." />}
    </Panel>
    <div className="info-banner"><ShieldCheck size={17} /><span>Disease detection and alert records are retrieved from backend history endpoints.</span></div>
  </>;
}
function HistoryCount({ label, value, icon: Icon }) { return <div className="history-count"><span><Icon size={17} /></span><small>{label}</small><strong>{value ?? '—'}</strong></div>; }
function Settings({ token, user }) {
  const [health, setHealth] = useState({ state: 'checking', value: null });
  const [baseUrl] = useState(import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000');
  const inference = useLoad((signal) => api.inferenceStatus(token, signal), [token]);
  useEffect(() => { const controller = new AbortController(); api.health(controller.signal).then((value) => setHealth({ state: 'connected', value })).catch((error) => setHealth({ state: 'unavailable', value: error.message })); return () => controller.abort(); }, []);
  const inferenceStatus = inference.error ? 'Unavailable' : inference.data?.available ? 'Available' : inference.data ? inference.data.reason || 'Unavailable' : 'Checking';
  return <><PageIntro eyebrow="WORKSPACE PREFERENCES" title="Settings" description="Review account and frontend connection configuration." /><div className="settings-grid"><Panel title="Account" subtitle="Authenticated backend profile"><div className="account-card"><span className="account-avatar"><UserRound size={22} /></span><div><strong>{user?.full_name}</strong><small>{user?.email}</small></div><Badge kind="badge-green">{user?.role}</Badge></div><div className="settings-detail"><span>Authentication</span><strong>Bearer token · session storage</strong></div><div className="settings-detail"><span>Token management</span><strong>Token expires according to backend policy</strong></div></Panel><Panel title="API connection" subtitle="Public API base URL and health response"><div className="connection-box"><span className={`connection-icon ${health.state}`}><Wifi size={18} /></span><span><strong>{health.state === 'connected' ? 'Backend responded' : health.state === 'unavailable' ? 'Backend unavailable' : 'Checking connection'}</strong><small>{health.state === 'connected' ? 'Health endpoint returned a response.' : health.state === 'unavailable' ? health.value : 'Checking /health'}</small></span><Badge kind={health.state === 'connected' ? 'badge-green' : health.state === 'unavailable' ? 'badge-red' : 'badge-gray'}>{health.state}</Badge></div><div className="settings-detail"><span>API base URL</span><strong className="mono">{baseUrl}</strong></div><div className="settings-detail"><span>Polling interval</span><strong>{Math.round(POLL_MS / 1000)} seconds while this tab is active</strong></div><p className="settings-help">Set <code>VITE_API_BASE_URL</code> in the frontend environment and restart Vite to change the API target. Health status confirms only that the API process responded; it does not verify PostgreSQL or hardware connectivity.</p></Panel></div><Panel title="Integration availability" subtitle="Current backend capabilities"><div className="integration-list"><IntegrationRow label="JWT authentication" status="Available" /><IntegrationRow label="REST data endpoints" status="Available" /><IntegrationRow label="Local disease inference" status={inferenceStatus} muted={!inference.data?.available} /><IntegrationRow label="WebSocket / SSE updates" status="Not exposed" muted /><IntegrationRow label="Manual pump control" status="Not exposed" muted /><IntegrationRow label="Hardware connection status" status="Not exposed" muted /></div></Panel></>;
}
function IntegrationRow({ label, status, muted }) { return <div className="integration-row"><span className={muted ? 'integration-muted' : 'integration-check'}>{muted ? <CircleHelp size={15} /> : <CircleCheck size={15} />}</span><span>{label}</span><small>{status}</small></div>; }
