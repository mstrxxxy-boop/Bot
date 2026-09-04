import React, { useState, useEffect, createContext, useContext, useCallback } from "react";
import "./App.css";
import axios from "axios";
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import { Toaster, toast } from "sonner";
import {
  LayoutDashboard, ListTodo, ClipboardCheck, Wallet, Users, Radio, HelpCircle,
  LogOut, Plus, Edit2, Trash2, Check, X, Search, Send, Image as ImageIcon,
  TrendingUp, Clock, ShieldCheck, Loader2, Eye, Upload, Menu, ChevronLeft,
  Shield, Power, RefreshCw, MessageCircle, Copy, ExternalLink,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const AuthCtx = createContext(null);
function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem("bc_token"));
  const login = (t) => { localStorage.setItem("bc_token", t); setToken(t); };
  const logout = () => { localStorage.removeItem("bc_token"); setToken(null); };
  return <AuthCtx.Provider value={{ token, login, logout }}>{children}</AuthCtx.Provider>;
}
const useAuth = () => useContext(AuthCtx);

function useApi() {
  const { token, logout } = useAuth();
  return useCallback(async (method, path, data) => {
    try {
      const r = await axios({ method, url: `${API}${path}`, data, headers: token ? { Authorization: `Bearer ${token}` } : {} });
      return r.data;
    } catch (e) {
      if (e.response?.status === 401) { logout(); toast.error("Sesi berakhir"); }
      throw e;
    }
  }, [token, logout]);
}

const fmtIDR = (n) => `Rp ${(n || 0).toLocaleString("id-ID")}`;
const fmtDate = (iso) => new Date(iso).toLocaleString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
const methodClass = (m) => ({ DANA: "method-dana", GoPay: "method-gopay", ShopeePay: "method-shopeepay" }[m] || "method-dana");

async function fileToBase64(file) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(r.result);
    r.onerror = rej;
    r.readAsDataURL(file);
  });
}

// ---------- Login ----------
function Login() {
  const [u, setU] = useState("admin");
  const [p, setP] = useState("");
  const [loading, setLoading] = useState(false);
  const { login, token } = useAuth();
  const nav = useNavigate();
  useEffect(() => { if (token) nav("/"); }, [token, nav]);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await axios.post(`${API}/auth/login`, { username: u, password: p });
      login(res.data.token);
      toast.success("Login berhasil!");
      nav("/");
    } catch (e) { toast.error(e.response?.data?.detail || "Login gagal"); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center grain p-4" data-testid="login-page">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-500/10 border border-emerald-500/20 mb-6">
            <span className="pulse-dot"></span>
            <span className="text-xs font-semibold text-emerald-400 tracking-wider">BIGOCUAN ADMIN</span>
          </div>
          <h1 className="text-4xl font-extrabold heading text-white mb-2">Selamat Datang</h1>
          <p className="text-slate-400">Kelola task, verifikasi bukti, pantau payout</p>
        </div>
        <form onSubmit={submit} className="card-dark p-8 space-y-5">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Username</label>
            <input className="input-dark" data-testid="login-username-input" value={u} onChange={(e) => setU(e.target.value)} required />
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Password</label>
            <input className="input-dark" data-testid="login-password-input" type="password" value={p} onChange={(e) => setP(e.target.value)} required />
          </div>
          <button className="btn-primary w-full flex items-center justify-center gap-2" data-testid="login-submit-button" disabled={loading}>
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
            Masuk Dashboard
          </button>
        </form>
      </div>
    </div>
  );
}

// ---------- Layout with responsive sidebar ----------
function Layout({ children }) {
  const { logout } = useAuth();
  const loc = useLocation();
  const nav = useNavigate();
  const [stats, setStats] = useState({});
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("bc_sb") === "1");
  const [mobileOpen, setMobileOpen] = useState(false);
  const api = useApi();

  useEffect(() => {
    const load = () => api("GET", "/stats/overview").then(setStats).catch(() => {});
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [api]);

  useEffect(() => { setMobileOpen(false); }, [loc.pathname]);

  const toggleCollapse = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem("bc_sb", next ? "1" : "0");
  };

  const items = [
    { path: "/", label: "Overview", icon: LayoutDashboard, testid: "nav-overview" },
    { path: "/tasks", label: "Tasks", icon: ListTodo, testid: "nav-tasks" },
    { path: "/submissions", label: "Submissions", icon: ClipboardCheck, testid: "nav-submissions", badge: stats.pending_submissions },
    { path: "/withdrawals", label: "Withdrawals", icon: Wallet, testid: "nav-withdrawals", badge: stats.pending_withdrawals },
    { path: "/users", label: "Users", icon: Users, testid: "nav-users" },
    { path: "/mandatory", label: "Verifikasi", icon: Shield, testid: "nav-mandatory" },
    { path: "/broadcast", label: "Broadcast", icon: Radio, testid: "nav-broadcast" },
    { path: "/support", label: "FAQ & Support", icon: HelpCircle, testid: "nav-support" },
  ];

  const sidebarWidth = collapsed ? 76 : 256;

  const Sidebar = (
    <>
      <div className="p-4 flex items-center gap-3 border-b border-slate-800/60" style={{ height: 72 }}>
        <div className="w-9 h-9 flex-shrink-0 rounded-lg gradient-emerald border border-emerald-500/30 flex items-center justify-center">
          <span className="text-emerald-400 font-extrabold text-lg heading">B</span>
        </div>
        {!collapsed && (
          <div className="min-w-0 flex-1">
            <div className="text-white font-extrabold heading tracking-tight truncate">BigoCuan</div>
            <div className="text-[10px] text-slate-500 uppercase tracking-widest">Admin Panel</div>
          </div>
        )}
        <button className="hidden lg:flex text-slate-400 hover:text-white p-1 rounded" onClick={toggleCollapse} data-testid="sidebar-toggle" title={collapsed ? "Expand" : "Collapse"}>
          <ChevronLeft className={`w-4 h-4 transition-transform ${collapsed ? "rotate-180" : ""}`} />
        </button>
      </div>

      {!collapsed && (
        <div className="px-4 pt-3">
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-800/40 border border-slate-800">
            <span className={`pulse-dot ${stats.bot_running ? '' : 'opacity-30'}`}></span>
            <div className="text-xs text-slate-300">{stats.bot_running ? "Bot Online" : "Bot Offline"}</div>
          </div>
        </div>
      )}

      <nav className="flex-1 space-y-1 px-3 py-4 overflow-y-auto">
        {items.map((it) => {
          const Icon = it.icon;
          const active = loc.pathname === it.path;
          return (
            <div
              key={it.path}
              className={`nav-item ${active ? "active" : ""} ${collapsed ? "justify-center" : ""}`}
              data-testid={it.testid}
              onClick={() => nav(it.path)}
              title={collapsed ? it.label : ""}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {!collapsed && <span className="flex-1 truncate">{it.label}</span>}
              {!collapsed && it.badge ? <span className="badge-status badge-pending">{it.badge}</span> : null}
              {collapsed && it.badge ? <span className="absolute top-1 right-1 w-2 h-2 bg-amber-500 rounded-full"></span> : null}
            </div>
          );
        })}
      </nav>

      <div className="p-3 border-t border-slate-800 space-y-1">
        {!collapsed && (
          <div className="px-3 py-1 text-xs text-slate-500">
            Channel: <span className="text-emerald-400 mono">@BigoCuan</span>
          </div>
        )}
        <button
          className={`nav-item w-full ${collapsed ? "justify-center" : ""}`}
          data-testid="logout-button"
          onClick={() => { logout(); nav("/login"); toast.success("Keluar"); }}
          title={collapsed ? "Keluar" : ""}
        >
          <LogOut className="w-4 h-4 flex-shrink-0" />
          {!collapsed && <span>Keluar</span>}
        </button>
      </div>
    </>
  );

  return (
    <div className="min-h-screen grain">
      {/* Desktop Sidebar */}
      <aside
        className="fixed left-0 top-0 h-screen bg-[#080C13] border-r border-slate-800 flex-col z-30 hidden lg:flex transition-all duration-300"
        style={{ width: sidebarWidth }}
      >
        {Sidebar}
      </aside>

      {/* Mobile Sidebar Overlay */}
      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-50" data-testid="mobile-sidebar-overlay">
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm animate-fadein" onClick={() => setMobileOpen(false)}></div>
          <aside className="absolute left-0 top-0 h-full w-64 bg-[#080C13] border-r border-slate-800 flex flex-col animate-slidein">
            {Sidebar}
          </aside>
        </div>
      )}

      {/* Main content */}
      <main
        className="min-h-screen transition-all duration-300"
        style={{ marginLeft: window.innerWidth >= 1024 ? sidebarWidth : 0 }}
      >
        {/* Mobile top bar */}
        <div className="lg:hidden sticky top-0 z-20 bg-[#0B0F17]/95 backdrop-blur border-b border-slate-800 flex items-center justify-between px-4 py-3">
          <button className="text-slate-300 p-2" data-testid="mobile-menu-btn" onClick={() => setMobileOpen(true)}>
            <Menu className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg gradient-emerald border border-emerald-500/30 flex items-center justify-center">
              <span className="text-emerald-400 font-extrabold heading">B</span>
            </div>
            <span className="text-white heading font-bold">BigoCuan</span>
          </div>
          <div style={{ width: 32 }}></div>
        </div>
        <div className="p-4 sm:p-6 lg:p-8">{children}</div>
      </main>
    </div>
  );
}

// ---------- Overview ----------
function Overview() {
  const api = useApi();
  const [s, setS] = useState({});
  useEffect(() => { api("GET", "/stats/overview").then(setS).catch(() => {}); }, [api]);

  const kpis = [
    { label: "Total Users", value: s.total_users || 0, icon: Users, color: "text-cyan-400", testid: "kpi-total-users" },
    { label: "Pending Task", value: s.pending_submissions || 0, icon: Clock, color: "text-amber-400", testid: "kpi-pending-submissions" },
    { label: "Pending Balance", value: fmtIDR(s.total_pending_balance || 0), icon: Wallet, color: "text-amber-400", testid: "kpi-pending-balance" },
    { label: "Total Payout", value: fmtIDR(s.total_payout || 0), icon: TrendingUp, color: "text-emerald-400", testid: "kpi-total-payout" },
  ];
  const maxDaily = Math.max(1, ...(s.daily || []).map(d => d.submissions));

  return (
    <div className="space-y-8 animate-fadein" data-testid="overview-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-3xl sm:text-4xl font-extrabold heading text-white">Dashboard Overview</h1>
          <p className="text-slate-400 mt-1">Ringkasan performa BigoCuan</p>
        </div>
        <div className="px-4 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center gap-2 text-emerald-400 w-fit">
          <Radio className="w-4 h-4" />
          <span className="text-sm font-semibold mono">@BigoCuan</span>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((k) => {
          const Icon = k.icon;
          return (
            <div key={k.label} className="card-dark p-5" data-testid={k.testid}>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">{k.label}</span>
                <Icon className={`w-5 h-5 ${k.color}`} />
              </div>
              <div className="mono text-xl sm:text-2xl font-bold text-white">{k.value}</div>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 card-dark p-6">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-xl font-bold heading text-white">Aktivitas 7 Hari</h3>
            <span className="badge-status badge-info">Submissions</span>
          </div>
          <div className="flex items-end gap-2 sm:gap-3 h-48">
            {(s.daily || []).map((d) => (
              <div key={d.date} className="flex-1 flex flex-col items-center gap-2">
                <div className="text-xs mono text-slate-400">{d.submissions}</div>
                <div className="w-full bg-gradient-to-t from-emerald-500 to-emerald-300 rounded-t-md transition-all"
                     style={{ height: `${(d.submissions / maxDaily) * 100}%`, minHeight: 4 }}></div>
                <div className="text-[10px] text-slate-500 mono">{d.date.slice(5)}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="card-dark p-6">
          <h3 className="text-xl font-bold heading text-white mb-6">E-Wallet</h3>
          {(s.wallet_distribution || []).length === 0 ? (
            <p className="text-slate-500 text-sm">Belum ada payout.</p>
          ) : (
            <div className="space-y-4">
              {s.wallet_distribution.map((w) => (
                <div key={w._id} className="flex items-center justify-between">
                  <span className={`chip-method ${methodClass(w._id)}`}>{w._id}</span>
                  <span className="text-xs text-slate-400 mono">{w.count}x · {fmtIDR(w.total)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <QuickApprovalWidget />
    </div>
  );
}

function QuickApprovalWidget() {
  const api = useApi();
  const [subs, setSubs] = useState([]);
  useEffect(() => { api("GET", "/submissions?status_filter=pending").then((d) => setSubs(d.slice(0, 5))).catch(() => {}); }, [api]);

  return (
    <div className="card-dark p-6" data-testid="quick-approval-widget">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xl font-bold heading text-white">Task Menunggu</h3>
        <span className="badge-status badge-pending">{subs.length} pending</span>
      </div>
      {subs.length === 0 ? (
        <p className="text-slate-500 text-sm">Tidak ada task menunggu. 🎉</p>
      ) : (
        <div className="space-y-3">
          {subs.map((s) => (
            <div key={s.id} className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/40 border border-slate-800">
              <div className="w-10 h-10 rounded-lg bg-emerald-500/20 flex items-center justify-center text-emerald-400">
                <ClipboardCheck className="w-5 h-5" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold text-white truncate">{s.task?.title || "Task"}</div>
                <div className="text-xs text-slate-400">@{s.user?.username || s.telegram_id} · {fmtDate(s.created_at)}</div>
              </div>
              <div className="text-emerald-400 font-bold mono text-sm">{fmtIDR(s.task?.reward || 0)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------- Tasks ----------
function TasksPage() {
  const api = useApi();
  const [tasks, setTasks] = useState([]);
  const [categories, setCategories] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [catFilter, setCatFilter] = useState("all");

  const load = () => api("GET", "/tasks").then(setTasks).catch(() => {});
  useEffect(() => {
    load();
    api("GET", "/task-categories").then(setCategories).catch(() => {});
  }, []);

  const del = async (id) => {
    if (!window.confirm("Hapus task ini?")) return;
    await api("DELETE", `/tasks/${id}`);
    toast.success("Task dihapus");
    load();
  };
  const toggle = async (t) => {
    await api("PATCH", `/tasks/${t.id}`, { active: !t.active });
    toast.success(t.active ? "Task dijeda" : "Task diaktifkan");
    load();
  };

  const filtered = catFilter === "all" ? tasks : tasks.filter(t => (t.category || "Other") === catFilter);

  return (
    <div className="space-y-6 animate-fadein" data-testid="tasks-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-3xl sm:text-4xl font-extrabold heading text-white">Task Management</h1>
          <p className="text-slate-400 mt-1">Buat dan kelola task</p>
        </div>
        <button className="btn-primary flex items-center gap-2 w-fit" data-testid="create-task-button" onClick={() => { setEditing(null); setShowModal(true); }}>
          <Plus className="w-4 h-4" /> Buat Task
        </button>
      </div>

      <div className="flex gap-2 flex-wrap">
        <button className={catFilter === "all" ? "btn-primary" : "btn-ghost"} onClick={() => setCatFilter("all")}>Semua</button>
        {categories.map((c) => (
          <button key={c} className={catFilter === c ? "btn-primary" : "btn-ghost"} onClick={() => setCatFilter(c)} data-testid={`filter-cat-${c}`}>{c}</button>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.length === 0 ? (
          <div className="card-dark p-12 text-center col-span-full">
            <ListTodo className="w-12 h-12 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">Belum ada task.</p>
          </div>
        ) : filtered.map((t) => (
          <div key={t.id} className="card-dark p-5" data-testid={`task-card-${t.id}`}>
            <div className="flex items-start justify-between mb-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <span className={`badge-status ${t.active ? "badge-approved" : "badge-rejected"}`}>{t.active ? "AKTIF" : "PAUSE"}</span>
                  <span className="badge-status badge-info">{t.category || "Other"}</span>
                </div>
                <h3 className="text-lg font-bold text-white truncate">{t.title}</h3>
              </div>
              <div className="text-emerald-400 mono font-bold text-lg text-right">{fmtIDR(t.reward)}</div>
            </div>
            <p className="text-sm text-slate-400 line-clamp-2 mb-4">{t.description}</p>
            <div className="flex items-center justify-between text-xs text-slate-500 mb-4 pb-4 border-b border-slate-800">
              <span>✅ {t.approved_count}</span>
              <span>⏳ {t.pending_count}</span>
              <span>{t.max_slots > 0 ? `${t.slots_used}/${t.max_slots}` : "∞"}</span>
            </div>
            <div className="flex gap-2">
              <button className="btn-ghost flex-1 flex items-center justify-center gap-1" data-testid={`edit-task-${t.id}`} onClick={() => { setEditing(t); setShowModal(true); }}>
                <Edit2 className="w-3 h-3" /> Edit
              </button>
              <button className="btn-ghost flex-1" data-testid={`toggle-task-${t.id}`} onClick={() => toggle(t)}>{t.active ? "Pause" : "On"}</button>
              <button className="btn-danger" data-testid={`delete-task-${t.id}`} onClick={() => del(t.id)}><Trash2 className="w-3 h-3" /></button>
            </div>
          </div>
        ))}
      </div>

      {showModal && <TaskModal task={editing} categories={categories} onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); load(); }} />}
    </div>
  );
}

function TaskModal({ task, categories, onClose, onSaved }) {
  const api = useApi();
  const [form, setForm] = useState(task || { title: "", description: "", reward: 5000, instructions: "", link: "", max_slots: 0, category: categories[0] || "Other" });
  const [loading, setLoading] = useState(false);

  const save = async () => {
    if (!form.title || !form.description || !form.reward) { toast.error("Isi field wajib"); return; }
    setLoading(true);
    try {
      if (task) await api("PATCH", `/tasks/${task.id}`, form);
      else await api("POST", "/tasks", form);
      toast.success(task ? "Task diperbarui" : "Task dibuat");
      onSaved();
    } catch (e) { toast.error("Gagal simpan"); }
    finally { setLoading(false); }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} data-testid="task-modal">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold heading text-white">{task ? "Edit Task" : "Task Baru"}</h2>
          <button onClick={onClose}><X className="w-5 h-5 text-slate-400" /></button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Judul *</label>
            <input className="input-dark mt-2" data-testid="task-title-input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          </div>
          <div>
            <label className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Deskripsi *</label>
            <textarea className="textarea-dark mt-2" data-testid="task-description-input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <div>
            <label className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Instruksi</label>
            <textarea className="textarea-dark mt-2" value={form.instructions || ""} onChange={(e) => setForm({ ...form, instructions: e.target.value })} />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Reward *</label>
              <input className="input-dark mono mt-2" data-testid="task-reward-input" type="number" value={form.reward} onChange={(e) => setForm({ ...form, reward: Number(e.target.value) })} />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Max Slot</label>
              <input className="input-dark mono mt-2" type="number" value={form.max_slots} onChange={(e) => setForm({ ...form, max_slots: Number(e.target.value) })} />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Kategori</label>
              <select className="input-dark mt-2" data-testid="task-category-input" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                {categories.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Link</label>
            <input className="input-dark mt-2" value={form.link || ""} onChange={(e) => setForm({ ...form, link: e.target.value })} placeholder="https://..." />
          </div>
        </div>
        <div className="flex gap-3 mt-6">
          <button className="btn-ghost flex-1" onClick={onClose}>Batal</button>
          <button className="btn-primary flex-1 flex items-center justify-center gap-2" onClick={save} disabled={loading} data-testid="task-modal-save">
            {loading && <Loader2 className="w-4 h-4 animate-spin" />} Simpan
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------- Submissions ----------
function SubmissionsPage() {
  const api = useApi();
  const [subs, setSubs] = useState([]);
  const [filter, setFilter] = useState("pending");
  const [preview, setPreview] = useState(null);

  const load = () => api("GET", `/submissions?status_filter=${filter}`).then(setSubs).catch(() => {});
  useEffect(() => { load(); }, [filter]);

  const approve = async (s) => {
    await api("POST", `/submissions/${s.id}/approve`);
    toast.success(`Disetujui! ${fmtIDR(s.task?.reward)} → saldo aktif`);
    load();
  };
  const reject = async (s, reason) => {
    await api("POST", `/submissions/${s.id}/reject`, { reason });
    toast.success("Task ditolak");
    load();
  };

  return (
    <div className="space-y-6 animate-fadein" data-testid="submissions-page">
      <div>
        <h1 className="text-3xl sm:text-4xl font-extrabold heading text-white">Task Submissions</h1>
        <p className="text-slate-400 mt-1">Verifikasi bukti pengerjaan task</p>
      </div>
      <div className="flex gap-2 flex-wrap">
        {["pending", "approved", "rejected", "all"].map((f) => (
          <button key={f} className={filter === f ? "btn-primary" : "btn-ghost"} data-testid={`filter-${f}`} onClick={() => setFilter(f)}>
            {f.toUpperCase()}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {subs.length === 0 ? (
          <div className="card-dark p-12 text-center">
            <ClipboardCheck className="w-12 h-12 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">Tidak ada submission.</p>
          </div>
        ) : subs.map((s) => (
          <div key={s.id} className="card-dark p-5" data-testid={`submission-${s.id}`}>
            <div className="flex flex-col md:flex-row gap-4">
              {s.proof_image && (
                <img src={s.proof_image} alt="proof" className="w-full md:w-32 h-32 object-cover rounded-lg border border-slate-800 cursor-pointer" onClick={() => setPreview(s.proof_image)} />
              )}
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-4 mb-2 flex-wrap">
                  <div>
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className={`badge-status badge-${s.status}`}>{s.status.toUpperCase()}</span>
                      <span className="text-xs text-slate-500">{fmtDate(s.created_at)}</span>
                    </div>
                    <h3 className="text-lg font-bold text-white">{s.task?.title || "Task"}</h3>
                    <div className="text-sm text-slate-400 mt-1">@{s.user?.username || "no_username"} · <span className="mono">{s.telegram_id}</span></div>
                  </div>
                  <div className="text-emerald-400 mono font-bold text-lg text-right">{fmtIDR(s.task?.reward || 0)}</div>
                </div>
                {s.proof_text && <p className="text-sm text-slate-300 bg-slate-800/50 p-3 rounded-lg mt-2">&ldquo;{s.proof_text}&rdquo;</p>}
                {s.reject_reason && <p className="text-sm text-red-400 mt-2">Tolak: {s.reject_reason}</p>}
                {s.status === "pending" && (
                  <div className="flex gap-2 mt-4">
                    <button className="btn-primary flex items-center gap-2" data-testid={`approve-submission-${s.id}`} onClick={() => approve(s)}>
                      <Check className="w-4 h-4" /> Setujui
                    </button>
                    <button className="btn-danger flex items-center gap-2" data-testid={`reject-submission-${s.id}`} onClick={() => {
                      const reason = window.prompt("Alasan tolak:", "Bukti tidak valid");
                      if (reason) reject(s, reason);
                    }}>
                      <X className="w-4 h-4" /> Tolak
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {preview && (
        <div className="modal-backdrop" onClick={() => setPreview(null)}>
          <img src={preview} alt="preview" className="max-w-full max-h-full rounded-lg" onClick={(e) => e.stopPropagation()} />
        </div>
      )}
    </div>
  );
}

// ---------- Withdrawals ----------
function WithdrawalsPage() {
  const api = useApi();
  const [wds, setWds] = useState([]);
  const [filter, setFilter] = useState("pending");
  const [approving, setApproving] = useState(null);

  const load = () => api("GET", `/withdrawals?status_filter=${filter}`).then(setWds).catch(() => {});
  useEffect(() => { load(); }, [filter]);

  const reject = async (w) => {
    const reason = window.prompt("Alasan tolak:", "Data tidak sesuai");
    if (!reason) return;
    await api("POST", `/withdrawals/${w.id}/reject`, { reason });
    toast.success("Withdraw ditolak, saldo direfund.");
    load();
  };

  return (
    <div className="space-y-6 animate-fadein" data-testid="withdrawals-page">
      <div>
        <h1 className="text-3xl sm:text-4xl font-extrabold heading text-white">Withdrawal Requests</h1>
        <p className="text-slate-400 mt-1">Proses pembayaran & broadcast bukti</p>
      </div>
      <div className="flex gap-2 flex-wrap">
        {["pending", "approved", "rejected", "all"].map((f) => (
          <button key={f} className={filter === f ? "btn-primary" : "btn-ghost"} data-testid={`wd-filter-${f}`} onClick={() => setFilter(f)}>{f.toUpperCase()}</button>
        ))}
      </div>

      <div className="space-y-3">
        {wds.length === 0 ? (
          <div className="card-dark p-12 text-center">
            <Wallet className="w-12 h-12 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">Tidak ada withdraw.</p>
          </div>
        ) : wds.map((w) => (
          <div key={w.id} className="card-dark p-5" data-testid={`withdrawal-${w.id}`}>
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <span className={`badge-status badge-${w.status}`}>{w.status.toUpperCase()}</span>
                  <span className={`chip-method ${methodClass(w.method)}`}>{w.method}</span>
                  <span className="text-xs text-slate-500">{fmtDate(w.created_at)}</span>
                </div>
                <div className="mono text-2xl font-bold text-white">{fmtIDR(w.amount)}</div>
                <div className="text-sm text-slate-400 mt-1"><span className="mono">{w.account_number}</span> · {w.account_name}</div>
                <div className="text-xs text-slate-500 mt-1">@{w.user?.username || "no_username"} · <span className="mono">{w.telegram_id}</span></div>
                {w.admin_note && <p className="text-sm text-slate-300 mt-2">📝 {w.admin_note}</p>}
                {w.reject_reason && <p className="text-sm text-red-400 mt-2">❌ {w.reject_reason}</p>}
              </div>
              {w.status === "pending" ? (
                <div className="flex gap-2 flex-shrink-0">
                  <button className="btn-primary flex items-center gap-2" data-testid={`approve-wd-${w.id}`} onClick={() => setApproving(w)}>
                    <Send className="w-4 h-4" /> Proses & Broadcast
                  </button>
                  <button className="btn-danger" data-testid={`reject-wd-${w.id}`} onClick={() => reject(w)}><X className="w-4 h-4" /></button>
                </div>
              ) : w.proof_image ? (
                <img src={w.proof_image} alt="proof" className="w-24 h-24 object-cover rounded-lg border border-slate-800" />
              ) : null}
            </div>
          </div>
        ))}
      </div>

      {approving && <WithdrawApproveModal wd={approving} onClose={() => setApproving(null)} onDone={() => { setApproving(null); load(); }} />}
    </div>
  );
}

function WithdrawApproveModal({ wd, onClose, onDone }) {
  const api = useApi();
  const [note, setNote] = useState(`Pembayaran berhasil dikirim ke ${wd.method} ${wd.account_number}`);
  const [image, setImage] = useState(null);
  const [loading, setLoading] = useState(false);

  const onFile = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    setImage(await fileToBase64(f));
  };

  const submit = async () => {
    if (!image) { toast.error("Upload bukti dulu"); return; }
    setLoading(true);
    try {
      const res = await api("POST", `/withdrawals/${wd.id}/approve`, { note, image_base64: image });
      const ok = res.broadcast?.channels?.some(c => c.ok);
      if (ok) toast.success("Bukti dikirim & broadcast berhasil!");
      else toast.warning("Bukti disimpan tapi broadcast gagal. Cek log.");
      onDone();
    } catch (e) { toast.error("Gagal memproses"); }
    finally { setLoading(false); }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} data-testid="wd-approve-modal">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold heading text-white">Proses Withdraw</h2>
          <button onClick={onClose}><X className="w-5 h-5 text-slate-400" /></button>
        </div>
        <div className="p-4 rounded-lg bg-slate-800/40 border border-slate-800 mb-4">
          <div className="mono text-2xl font-bold text-emerald-400 mb-2">{fmtIDR(wd.amount)}</div>
          <div className="text-sm flex items-center gap-2 flex-wrap">
            <span className={`chip-method ${methodClass(wd.method)}`}>{wd.method}</span>
            <span className="mono text-slate-300">{wd.account_number}</span>
            <span className="text-white font-semibold">{wd.account_name}</span>
          </div>
          <div className="text-xs text-slate-500 mt-2">@{wd.user?.username || wd.telegram_id}</div>
        </div>
        <div className="space-y-4">
          <div>
            <label className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Bukti Pembayaran *</label>
            <label className="block cursor-pointer mt-2">
              <input type="file" accept="image/*" onChange={onFile} className="hidden" data-testid="wd-image-upload" />
              <div className="input-dark flex items-center gap-3 py-6 border-dashed">
                {image ? <img src={image} alt="preview" className="w-16 h-16 rounded object-cover" /> : <Upload className="w-8 h-8 text-slate-500" />}
                <div className="text-sm">{image ? <span className="text-emerald-400">Uploaded ✓</span> : <span className="text-slate-400">Klik untuk upload foto</span>}</div>
              </div>
            </label>
          </div>
          <div>
            <label className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Keterangan</label>
            <textarea className="textarea-dark mt-2" value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
        </div>
        <div className="flex gap-3 mt-6">
          <button className="btn-ghost flex-1" onClick={onClose}>Batal</button>
          <button className="btn-primary flex-1 flex items-center justify-center gap-2" onClick={submit} disabled={loading} data-testid="wd-approve-submit">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            Approve & Broadcast
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------- Users ----------
function UsersPage() {
  const api = useApi();
  const [users, setUsers] = useState([]);
  const [q, setQ] = useState("");
  const [detail, setDetail] = useState(null);

  useEffect(() => { api("GET", "/users").then(setUsers).catch(() => {}); }, [api]);
  const filtered = users.filter((u) => !q ||
    (u.username || "").toLowerCase().includes(q.toLowerCase()) ||
    (u.first_name || "").toLowerCase().includes(q.toLowerCase()) ||
    String(u.telegram_id).includes(q));

  return (
    <div className="space-y-6 animate-fadein" data-testid="users-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-3xl sm:text-4xl font-extrabold heading text-white">Users</h1>
          <p className="text-slate-400 mt-1">{users.length} pengguna terdaftar</p>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input className="input-dark pl-10 w-full sm:w-72" placeholder="Cari..." value={q} onChange={(e) => setQ(e.target.value)} data-testid="user-search" />
        </div>
      </div>

      <div className="card-dark overflow-x-auto">
        <table className="w-full min-w-[720px]">
          <thead className="bg-slate-800/40 text-xs uppercase tracking-wider text-slate-400">
            <tr>
              <th className="text-left p-4">User</th>
              <th className="text-right p-4">Aktif</th>
              <th className="text-right p-4">Pending</th>
              <th className="text-right p-4">Ditolak</th>
              <th className="text-center p-4">Selesai/Tolak</th>
              <th className="text-center p-4">Ref</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr><td colSpan="7" className="p-12 text-center text-slate-500">Belum ada user.</td></tr>
            ) : filtered.map((u) => (
              <tr key={u.telegram_id} className="border-t border-slate-800 hover:bg-slate-800/20" data-testid={`user-row-${u.telegram_id}`}>
                <td className="p-4">
                  <div className="font-semibold text-white">{u.first_name || "-"}</div>
                  <div className="text-xs text-slate-400">@{u.username || "no_username"} · <span className="mono">{u.telegram_id}</span></div>
                </td>
                <td className="p-4 mono font-bold text-emerald-400 text-right">{fmtIDR(u.balance)}</td>
                <td className="p-4 mono text-amber-400 text-right">{fmtIDR(u.pending_balance || 0)}</td>
                <td className="p-4 mono text-red-400 text-right">{fmtIDR(u.rejected_total || 0)}</td>
                <td className="p-4 text-center text-slate-300">{u.tasks_completed || 0} / {u.tasks_rejected || 0}</td>
                <td className="p-4 text-center text-slate-300">{u.referral_count || 0}</td>
                <td className="p-4">
                  <button className="btn-ghost flex items-center gap-1" data-testid={`view-user-${u.telegram_id}`} onClick={() => setDetail(u.telegram_id)}>
                    <Eye className="w-3 h-3" /> Detail
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {detail && <UserDetailModal telegramId={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

function UserDetailModal({ telegramId, onClose }) {
  const api = useApi();
  const [data, setData] = useState(null);
  const [adjustAmt, setAdjustAmt] = useState(0);
  const [adjustNote, setAdjustNote] = useState("");
  const load = () => api("GET", `/users/${telegramId}`).then(setData).catch(() => {});
  useEffect(() => { load(); }, [telegramId]);

  const adjust = async () => {
    if (!adjustAmt) return;
    try {
      await api("POST", `/users/${telegramId}/adjust`, { amount: Number(adjustAmt), note: adjustNote });
      toast.success("Saldo disesuaikan");
      setAdjustAmt(0); setAdjustNote("");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal"); }
  };

  if (!data) return null;
  const u = data.user;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 720 }} data-testid="user-detail-modal">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-2xl font-bold heading text-white">{u.first_name || "User"}</h2>
            <div className="text-slate-400 text-sm">@{u.username} · <span className="mono">{u.telegram_id}</span></div>
          </div>
          <button onClick={onClose}><X className="w-5 h-5 text-slate-400" /></button>
        </div>

        <div className="grid grid-cols-3 gap-3 mb-6">
          <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
            <div className="text-xs text-slate-400">Aktif</div>
            <div className="mono font-bold text-emerald-400 text-sm">{fmtIDR(u.balance)}</div>
          </div>
          <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
            <div className="text-xs text-slate-400">Pending</div>
            <div className="mono font-bold text-amber-400 text-sm">{fmtIDR(u.pending_balance || 0)}</div>
          </div>
          <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20">
            <div className="text-xs text-slate-400">Ditolak</div>
            <div className="mono font-bold text-red-400 text-sm">{fmtIDR(u.rejected_total || 0)}</div>
          </div>
        </div>

        {u.bank && (
          <div className="mb-4 p-4 rounded-lg bg-slate-800/40">
            <div className="text-xs uppercase tracking-wider text-slate-400 mb-2">Bank</div>
            <div className="flex items-center gap-3 flex-wrap">
              <span className={`chip-method ${methodClass(u.bank.method)}`}>{u.bank.method}</span>
              <span className="mono">{u.bank.account_number}</span>
              <span className="font-semibold">{u.bank.account_name}</span>
            </div>
          </div>
        )}

        <div className="mb-6 p-4 rounded-lg bg-amber-500/5 border border-amber-500/20">
          <div className="text-xs uppercase tracking-wider text-amber-400 mb-2 font-semibold">Penyesuaian Saldo Aktif</div>
          <div className="flex gap-2 flex-wrap">
            <input type="number" className="input-dark mono w-32" placeholder="Nominal" value={adjustAmt} onChange={(e) => setAdjustAmt(e.target.value)} data-testid="adjust-amount" />
            <input className="input-dark flex-1 min-w-[150px]" placeholder="Keterangan" value={adjustNote} onChange={(e) => setAdjustNote(e.target.value)} />
            <button className="btn-primary" onClick={adjust} data-testid="adjust-submit">Terapkan</button>
          </div>
        </div>

        {data.referrals?.length > 0 && (
          <div className="mb-4">
            <h3 className="text-lg font-bold heading text-white mb-2">Referral ({data.referrals.length})</h3>
            <div className="space-y-1 max-h-32 overflow-y-auto">
              {data.referrals.map((r) => (
                <div key={r.telegram_id} className="text-sm p-2 bg-slate-800/30 rounded flex justify-between">
                  <span>{r.first_name || "-"} <span className="text-slate-500">@{r.username}</span></span>
                  <span className="text-xs text-slate-500">{fmtDate(r.created_at)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div>
          <h3 className="text-lg font-bold heading text-white mb-3">Riwayat Saldo</h3>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {data.balance_history.length === 0 ? <p className="text-slate-500 text-sm">Kosong.</p> :
              data.balance_history.map((h) => (
                <div key={h.id} className="flex items-center justify-between p-2 rounded bg-slate-800/30 text-sm">
                  <div>
                    <span className={`mono font-bold ${h.type === "credit" || h.type === "refund" ? "text-emerald-400" : "text-red-400"}`}>
                      {h.type === "credit" || h.type === "refund" ? "+" : "-"}{fmtIDR(h.amount)}
                    </span>
                    <span className="text-xs text-slate-400 ml-2">{h.note}</span>
                  </div>
                  <span className="text-xs text-slate-500">{fmtDate(h.created_at)}</span>
                </div>
              ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------- Mandatory Channels ----------
function MandatoryPage() {
  const api = useApi();
  const [channels, setChannels] = useState([]);
  const [form, setForm] = useState({ username: "", title: "" });

  const load = () => api("GET", "/channels?kind=mandatory").then(setChannels).catch(() => {});
  useEffect(() => { load(); }, []);

  const add = async () => {
    if (!form.username) { toast.error("Isi username"); return; }
    try {
      await api("POST", "/channels", { ...form, kind: "mandatory", active: true });
      setForm({ username: "", title: "" });
      toast.success("Channel wajib ditambahkan");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal"); }
  };
  const toggle = async (c) => {
    await api("PATCH", `/channels/${c.id}`, { active: !c.active });
    load();
  };
  const del = async (c) => {
    if (!window.confirm("Hapus channel ini?")) return;
    await api("DELETE", `/channels/${c.id}`);
    toast.success("Dihapus");
    load();
  };

  return (
    <div className="space-y-6 animate-fadein" data-testid="mandatory-page">
      <div>
        <h1 className="text-3xl sm:text-4xl font-extrabold heading text-white">Verifikasi Channel Wajib</h1>
        <p className="text-slate-400 mt-1">User wajib join channel/grup ini sebelum bisa akses bot</p>
      </div>

      <div className="card-dark p-6">
        <h3 className="text-lg font-bold heading text-white mb-4">Tambah Channel Wajib</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input className="input-dark" placeholder="@channelname atau -100..." value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} data-testid="mandatory-username" />
          <input className="input-dark" placeholder="Nama tampilan (opsional)" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <button className="btn-primary flex items-center justify-center gap-2" onClick={add} data-testid="mandatory-add"><Plus className="w-4 h-4" /> Tambah</button>
        </div>
        <p className="text-xs text-slate-500 mt-3">💡 Pastikan bot @BigoCuan_bot sudah menjadi admin di channel/grup tersebut agar bisa cek membership.</p>
      </div>

      <div className="space-y-3">
        {channels.length === 0 ? (
          <div className="card-dark p-12 text-center">
            <Shield className="w-12 h-12 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">Belum ada channel wajib. User bisa langsung akses bot.</p>
          </div>
        ) : channels.map((c) => (
          <div key={c.id} className="card-dark p-4 flex items-center justify-between gap-3 flex-wrap" data-testid={`mandatory-${c.id}`}>
            <div className="flex items-center gap-3">
              <Shield className={`w-5 h-5 ${c.active ? "text-emerald-400" : "text-slate-600"}`} />
              <div>
                <div className="text-white font-semibold">{c.title || c.username}</div>
                <div className="text-xs text-slate-400 mono">{c.username}</div>
              </div>
              <span className={`badge-status ${c.active ? "badge-approved" : "badge-rejected"}`}>{c.active ? "AKTIF" : "OFF"}</span>
            </div>
            <div className="flex gap-2">
              <button className="btn-ghost" onClick={() => toggle(c)}>{c.active ? "Nonaktifkan" : "Aktifkan"}</button>
              <button className="btn-danger" onClick={() => del(c)}><Trash2 className="w-3 h-3" /></button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------- Broadcast Page ----------
function BroadcastPage() {
  const api = useApi();
  const [logs, setLogs] = useState([]);
  const [channels, setChannels] = useState([]);
  const [settings, setSettings] = useState({ enabled: true });
  const [text, setText] = useState("");
  const [image, setImage] = useState(null);
  const [sending, setSending] = useState(false);
  const [chForm, setChForm] = useState({ username: "", title: "" });
  const [selectedChs, setSelectedChs] = useState([]);

  const load = async () => {
    const [l, c, s] = await Promise.all([
      api("GET", "/broadcast/logs"),
      api("GET", "/channels?kind=broadcast"),
      api("GET", "/broadcast/settings"),
    ]);
    setLogs(l); setChannels(c); setSettings(s);
  };
  useEffect(() => { load().catch(() => {}); }, []);

  const toggleMaster = async () => {
    await api("PUT", "/broadcast/settings", { enabled: !settings.enabled });
    toast.success(settings.enabled ? "Broadcast dinonaktifkan" : "Broadcast diaktifkan");
    load();
  };
  const addCh = async () => {
    if (!chForm.username) return toast.error("Isi username");
    try {
      await api("POST", "/channels", { ...chForm, kind: "broadcast", active: true });
      setChForm({ username: "", title: "" });
      toast.success("Channel ditambahkan");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal"); }
  };
  const toggleCh = async (c) => {
    await api("PATCH", `/channels/${c.id}`, { active: !c.active });
    load();
  };
  const delCh = async (c) => {
    if (!window.confirm("Hapus channel?")) return;
    await api("DELETE", `/channels/${c.id}`);
    load();
  };
  const send = async () => {
    if (!text) return toast.error("Isi teks");
    setSending(true);
    try {
      await api("POST", "/broadcast/manual", { text, image_base64: image, channel_ids: selectedChs.length ? selectedChs : null });
      toast.success("Broadcast terkirim");
      setText(""); setImage(null); setSelectedChs([]);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal"); }
    finally { setSending(false); }
  };
  const resend = async (log) => {
    try {
      await api("POST", `/broadcast/logs/${log.id}/resend`);
      toast.success("Broadcast dikirim ulang");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal"); }
  };
  const onFile = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    setImage(await fileToBase64(f));
  };

  return (
    <div className="space-y-6 animate-fadein" data-testid="broadcast-page">
      <div>
        <h1 className="text-3xl sm:text-4xl font-extrabold heading text-white">Broadcast Management</h1>
        <p className="text-slate-400 mt-1">Kelola channel & broadcast pesan otomatis/manual</p>
      </div>

      {/* Master toggle */}
      <div className="card-dark p-5 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className={`w-12 h-12 rounded-lg flex items-center justify-center ${settings.enabled ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/20 text-red-400"}`}>
            <Power className="w-5 h-5" />
          </div>
          <div>
            <div className="text-white font-bold heading">Master Toggle Broadcast</div>
            <div className="text-xs text-slate-400">
              Status: <span className={settings.enabled ? "text-emerald-400" : "text-red-400"}>{settings.enabled ? "AKTIF" : "NONAKTIF"}</span>
            </div>
          </div>
        </div>
        <button
          className={settings.enabled ? "btn-danger" : "btn-primary"}
          onClick={toggleMaster}
          data-testid="broadcast-master-toggle"
        >
          {settings.enabled ? "Nonaktifkan" : "Aktifkan"}
        </button>
      </div>

      {/* Manage broadcast channels */}
      <div className="card-dark p-6">
        <h3 className="text-lg font-bold heading text-white mb-4">Channel Broadcast Target</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
          <input className="input-dark" placeholder="@channelname atau -100..." value={chForm.username} onChange={(e) => setChForm({ ...chForm, username: e.target.value })} data-testid="bc-ch-username" />
          <input className="input-dark" placeholder="Nama (opsional)" value={chForm.title} onChange={(e) => setChForm({ ...chForm, title: e.target.value })} />
          <button className="btn-primary flex items-center justify-center gap-2" onClick={addCh} data-testid="bc-ch-add"><Plus className="w-4 h-4" /> Tambah</button>
        </div>
        <div className="space-y-2">
          {channels.length === 0 ? (
            <p className="text-sm text-slate-500">Belum ada channel. Broadcast akan ke default @BigoCuan.</p>
          ) : channels.map((c) => (
            <div key={c.id} className="flex items-center justify-between p-3 rounded-lg bg-slate-800/40 gap-3 flex-wrap" data-testid={`bc-ch-${c.id}`}>
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={selectedChs.includes(c.id)} onChange={(e) => setSelectedChs(e.target.checked ? [...selectedChs, c.id] : selectedChs.filter(x => x !== c.id))} />
                  <div>
                    <div className="text-white font-semibold">{c.title || c.username}</div>
                    <div className="text-xs text-slate-400 mono">{c.username}</div>
                  </div>
                </label>
                <span className={`badge-status ${c.active ? "badge-approved" : "badge-rejected"}`}>{c.active ? "AKTIF" : "OFF"}</span>
              </div>
              <div className="flex gap-2">
                <button className="btn-ghost" onClick={() => toggleCh(c)}>{c.active ? "Off" : "On"}</button>
                <button className="btn-danger" onClick={() => delCh(c)}><Trash2 className="w-3 h-3" /></button>
              </div>
            </div>
          ))}
        </div>
        {channels.length > 0 && <p className="text-xs text-slate-500 mt-3">Centang channel target di atas. Kosong = broadcast ke semua channel aktif.</p>}
      </div>

      {/* Manual send */}
      <div className="card-dark p-6">
        <h3 className="text-lg font-bold heading text-white mb-4">Kirim Broadcast Manual</h3>
        <div className="space-y-4">
          <textarea className="textarea-dark" placeholder="Tulis pesan..." value={text} onChange={(e) => setText(e.target.value)} data-testid="broadcast-text-input" />
          <label className="block cursor-pointer">
            <input type="file" accept="image/*" className="hidden" onChange={onFile} data-testid="broadcast-image-upload" />
            <div className="input-dark flex items-center gap-3 py-4 border-dashed cursor-pointer">
              {image ? <img src={image} alt="preview" className="w-12 h-12 rounded object-cover" /> : <ImageIcon className="w-6 h-6 text-slate-500" />}
              <span className="text-sm text-slate-400">{image ? "Gambar terupload ✓" : "Upload gambar (opsional)"}</span>
            </div>
          </label>
          <button className="btn-primary w-full flex items-center justify-center gap-2" onClick={send} disabled={sending || !settings.enabled} data-testid="broadcast-send">
            {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            Broadcast {selectedChs.length ? `ke ${selectedChs.length} channel` : "ke semua aktif"}
          </button>
        </div>
      </div>

      {/* Log */}
      <div className="card-dark p-6">
        <h3 className="text-lg font-bold heading text-white mb-4">Broadcast Log ({logs.length})</h3>
        <div className="space-y-3 max-h-96 overflow-y-auto">
          {logs.length === 0 ? (
            <p className="text-slate-500 text-sm">Belum ada broadcast.</p>
          ) : logs.map((l) => {
            const anyOk = (l.results || []).some(r => r.ok);
            return (
              <div key={l.id} className="flex gap-3 p-4 rounded-lg bg-slate-800/30 border border-slate-800" data-testid={`broadcast-log-${l.id}`}>
                {l.image_base64 && <img src={l.image_base64} alt="" className="w-20 h-20 object-cover rounded" />}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className={`badge-status ${anyOk ? "badge-approved" : "badge-rejected"}`}>{(l.status || "").toUpperCase()}</span>
                    <span className="badge-status badge-info">{(l.type || "").toUpperCase()}</span>
                    <span className="text-xs text-slate-500">{fmtDate(l.created_at)}</span>
                  </div>
                  <p className="text-sm text-slate-300 whitespace-pre-line line-clamp-3">{l.text}</p>
                  {(l.results || []).length > 0 && (
                    <div className="mt-2 text-xs text-slate-500">
                      {l.results.map((r, i) => (
                        <span key={i} className={r.ok ? "text-emerald-400 mr-2" : "text-red-400 mr-2"}>
                          {r.ok ? "✓" : "✗"} {r.channel}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                {!anyOk && (
                  <button className="btn-ghost h-fit flex items-center gap-1" onClick={() => resend(l)} data-testid={`resend-${l.id}`}>
                    <RefreshCw className="w-3 h-3" /> Kirim Ulang
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ---------- FAQ & Support ----------
function SupportPage() {
  const api = useApi();
  const [faqs, setFaqs] = useState([]);
  const [support, setSupport] = useState({ whatsapp: "", telegram_username: "", extra_text: "" });
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ question: "", answer: "", order: 0 });

  const load = async () => {
    const [f, s] = await Promise.all([api("GET", "/faqs"), api("GET", "/support")]);
    setFaqs(f); setSupport(s);
  };
  useEffect(() => { load().catch(() => {}); }, []);

  const saveFaq = async () => {
    if (!form.question || !form.answer) return toast.error("Isi Q & A");
    try {
      if (editing) await api("PATCH", `/faqs/${editing}`, form);
      else await api("POST", "/faqs", form);
      toast.success("Tersimpan");
      setForm({ question: "", answer: "", order: 0 }); setEditing(null);
      load();
    } catch (e) { toast.error("Gagal"); }
  };
  const del = async (f) => {
    if (!window.confirm("Hapus FAQ?")) return;
    await api("DELETE", `/faqs/${f.id}`);
    load();
  };
  const saveSupport = async () => {
    try {
      await api("PUT", "/support", support);
      toast.success("Info support diperbarui");
    } catch (e) { toast.error("Gagal"); }
  };

  return (
    <div className="space-y-6 animate-fadein" data-testid="support-page">
      <div>
        <h1 className="text-3xl sm:text-4xl font-extrabold heading text-white">FAQ & Support</h1>
        <p className="text-slate-400 mt-1">Kelola pertanyaan umum & kontak admin</p>
      </div>

      {/* Support Contact Config */}
      <div className="card-dark p-6">
        <h3 className="text-lg font-bold heading text-white mb-4 flex items-center gap-2">
          <MessageCircle className="w-5 h-5 text-emerald-400" /> Kontak Admin
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="text-xs uppercase tracking-wider text-slate-400 font-semibold">WhatsApp</label>
            <input className="input-dark mt-2" placeholder="+6281234567890" value={support.whatsapp || ""} onChange={(e) => setSupport({ ...support, whatsapp: e.target.value })} data-testid="support-whatsapp" />
          </div>
          <div>
            <label className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Telegram Username</label>
            <input className="input-dark mt-2" placeholder="@BangJarr" value={support.telegram_username || ""} onChange={(e) => setSupport({ ...support, telegram_username: e.target.value })} data-testid="support-telegram" />
          </div>
        </div>
        <div className="mt-4">
          <label className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Teks Tambahan</label>
          <textarea className="textarea-dark mt-2" placeholder="Info tambahan..." value={support.extra_text || ""} onChange={(e) => setSupport({ ...support, extra_text: e.target.value })} />
        </div>
        <button className="btn-primary mt-4" onClick={saveSupport} data-testid="support-save">Simpan Kontak</button>
      </div>

      {/* FAQ Editor */}
      <div className="card-dark p-6">
        <h3 className="text-lg font-bold heading text-white mb-4">{editing ? "Edit FAQ" : "Tambah FAQ"}</h3>
        <div className="space-y-3">
          <input className="input-dark" placeholder="Pertanyaan" value={form.question} onChange={(e) => setForm({ ...form, question: e.target.value })} data-testid="faq-question" />
          <textarea className="textarea-dark" placeholder="Jawaban" value={form.answer} onChange={(e) => setForm({ ...form, answer: e.target.value })} data-testid="faq-answer" />
          <div className="flex gap-2">
            <input type="number" className="input-dark mono w-32" placeholder="Urutan" value={form.order} onChange={(e) => setForm({ ...form, order: Number(e.target.value) })} />
            <button className="btn-primary flex-1" onClick={saveFaq} data-testid="faq-save">{editing ? "Update" : "Tambah"}</button>
            {editing && <button className="btn-ghost" onClick={() => { setEditing(null); setForm({ question: "", answer: "", order: 0 }); }}>Batal</button>}
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <h3 className="text-lg font-bold heading text-white">Daftar FAQ ({faqs.length})</h3>
        {faqs.length === 0 ? (
          <p className="text-slate-500 text-sm">Belum ada FAQ.</p>
        ) : faqs.map((f) => (
          <div key={f.id} className="card-dark p-4 flex items-start justify-between gap-3" data-testid={`faq-${f.id}`}>
            <div className="flex-1 min-w-0">
              <div className="text-white font-semibold">{f.question}</div>
              <div className="text-sm text-slate-400 mt-1 line-clamp-2">{f.answer}</div>
              <div className="text-xs text-slate-500 mt-1">Urutan: {f.order}</div>
            </div>
            <div className="flex gap-2">
              <button className="btn-ghost" onClick={() => { setEditing(f.id); setForm({ question: f.question, answer: f.answer, order: f.order }); }}>
                <Edit2 className="w-3 h-3" />
              </button>
              <button className="btn-danger" onClick={() => del(f)}><Trash2 className="w-3 h-3" /></button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Protected({ children }) {
  const { token } = useAuth();
  if (!token) return <Navigate to="/login" />;
  return <Layout>{children}</Layout>;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster position="top-right" theme="dark" richColors />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<Protected><Overview /></Protected>} />
          <Route path="/tasks" element={<Protected><TasksPage /></Protected>} />
          <Route path="/submissions" element={<Protected><SubmissionsPage /></Protected>} />
          <Route path="/withdrawals" element={<Protected><WithdrawalsPage /></Protected>} />
          <Route path="/users" element={<Protected><UsersPage /></Protected>} />
          <Route path="/mandatory" element={<Protected><MandatoryPage /></Protected>} />
          <Route path="/broadcast" element={<Protected><BroadcastPage /></Protected>} />
          <Route path="/support" element={<Protected><SupportPage /></Protected>} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
