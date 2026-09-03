import React, { useState, useEffect, createContext, useContext, useCallback } from "react";
import "./App.css";
import axios from "axios";
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import { Toaster, toast } from "sonner";
import {
  LayoutDashboard, ListTodo, ClipboardCheck, Wallet, Users, Radio,
  LogOut, Plus, Edit2, Trash2, Check, X, Search, Copy, Send, Image as ImageIcon,
  TrendingUp, Clock, ShieldCheck, Bell, Loader2, Eye, Upload,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// ---------- Auth Context ----------
const AuthCtx = createContext(null);

function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem("bc_token"));
  const login = (t) => { localStorage.setItem("bc_token", t); setToken(t); };
  const logout = () => { localStorage.removeItem("bc_token"); setToken(null); };
  return <AuthCtx.Provider value={{ token, login, logout }}>{children}</AuthCtx.Provider>;
}
const useAuth = () => useContext(AuthCtx);

// ---------- API helper ----------
function useApi() {
  const { token, logout } = useAuth();
  const call = useCallback(async (method, path, data) => {
    try {
      const res = await axios({
        method, url: `${API}${path}`, data,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      return res.data;
    } catch (e) {
      if (e.response?.status === 401) { logout(); toast.error("Sesi berakhir, silakan login."); }
      throw e;
    }
  }, [token, logout]);
  return call;
}

// ---------- Utils ----------
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
    } catch (e) {
      toast.error(e.response?.data?.detail || "Login gagal");
    } finally { setLoading(false); }
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
          <p className="text-slate-400">Kelola task, verifikasi bukti, dan pantau payout</p>
        </div>
        <form onSubmit={submit} className="card-dark p-8 space-y-5">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Username</label>
            <input className="input-dark" data-testid="login-username-input" value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" required />
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Password</label>
            <input className="input-dark" data-testid="login-password-input" type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" required />
          </div>
          <button className="btn-primary w-full flex items-center justify-center gap-2" data-testid="login-submit-button" disabled={loading}>
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
            Masuk Dashboard
          </button>
        </form>
        <p className="text-center text-xs text-slate-500 mt-6">Channel Broadcast: <span className="text-emerald-400 font-mono">@BigoCuan</span></p>
      </div>
    </div>
  );
}

// ---------- Layout ----------
function Layout({ children }) {
  const { logout } = useAuth();
  const loc = useLocation();
  const nav = useNavigate();
  const [stats, setStats] = useState({});
  const api = useApi();

  useEffect(() => {
    const load = () => api("GET", "/stats/overview").then(setStats).catch(() => {});
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [api]);

  const items = [
    { path: "/", label: "Overview", icon: LayoutDashboard, testid: "nav-overview" },
    { path: "/tasks", label: "Tasks", icon: ListTodo, testid: "nav-tasks", badge: null },
    { path: "/submissions", label: "Submissions", icon: ClipboardCheck, testid: "nav-submissions", badge: stats.pending_submissions },
    { path: "/withdrawals", label: "Withdrawals", icon: Wallet, testid: "nav-withdrawals", badge: stats.pending_withdrawals },
    { path: "/users", label: "Users", icon: Users, testid: "nav-users" },
    { path: "/broadcast", label: "Broadcast", icon: Radio, testid: "nav-broadcast" },
  ];

  return (
    <div className="min-h-screen grain">
      {/* Sidebar */}
      <aside className="fixed left-0 top-0 h-screen w-64 bg-[#080C13] border-r border-slate-800 p-5 flex flex-col z-30">
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-9 h-9 rounded-lg gradient-emerald border border-emerald-500/30 flex items-center justify-center">
              <span className="text-emerald-400 font-extrabold text-lg heading">B</span>
            </div>
            <div>
              <div className="text-white font-extrabold heading tracking-tight">BigoCuan</div>
              <div className="text-[10px] text-slate-500 uppercase tracking-widest">Admin Panel</div>
            </div>
          </div>
          <div className="flex items-center gap-2 mt-4 px-3 py-2 rounded-lg bg-slate-800/40 border border-slate-800">
            <span className={`pulse-dot ${stats.bot_running ? '' : 'opacity-30'}`}></span>
            <div className="text-xs text-slate-300">
              {stats.bot_running ? "Bot Online" : "Bot Offline"}
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-1">
          {items.map((it) => {
            const Icon = it.icon;
            const active = loc.pathname === it.path;
            return (
              <div key={it.path} className={`nav-item ${active ? "active" : ""}`} data-testid={it.testid} onClick={() => nav(it.path)}>
                <Icon className="w-4 h-4" />
                <span className="flex-1">{it.label}</span>
                {it.badge ? <span className="badge-status badge-pending">{it.badge}</span> : null}
              </div>
            );
          })}
        </nav>

        <div className="pt-4 border-t border-slate-800 space-y-2">
          <div className="px-3 py-2 text-xs text-slate-500">
            Channel: <span className="text-emerald-400 mono">@BigoCuan</span>
          </div>
          <button className="nav-item w-full text-left" data-testid="logout-button" onClick={() => { logout(); nav("/login"); toast.success("Keluar"); }}>
            <LogOut className="w-4 h-4" />
            <span>Keluar</span>
          </button>
        </div>
      </aside>

      <main className="ml-64 min-h-screen">
        <div className="p-8">{children}</div>
      </main>
    </div>
  );
}

// ---------- Overview Page ----------
function Overview() {
  const api = useApi();
  const [s, setS] = useState({});
  useEffect(() => { api("GET", "/stats/overview").then(setS).catch(() => {}); }, [api]);

  const kpis = [
    { label: "Total Users", value: s.total_users || 0, icon: Users, color: "text-cyan-400", testid: "kpi-total-users" },
    { label: "Pending Task", value: s.pending_submissions || 0, icon: Clock, color: "text-amber-400", testid: "kpi-pending-submissions" },
    { label: "Pending Withdraw", value: fmtIDR(s.pending_withdrawals_amount || 0), sub: `${s.pending_withdrawals || 0} request`, icon: Wallet, color: "text-amber-400", testid: "kpi-pending-withdrawals" },
    { label: "Total Payout", value: fmtIDR(s.total_payout || 0), icon: TrendingUp, color: "text-emerald-400", testid: "kpi-total-payout" },
  ];

  const maxDaily = Math.max(1, ...(s.daily || []).map(d => d.submissions));

  return (
    <div className="space-y-8 animate-fadein" data-testid="overview-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-extrabold heading text-white">Dashboard Overview</h1>
          <p className="text-slate-400 mt-1">Ringkasan performa BigoCuan task platform</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="px-4 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center gap-2 text-emerald-400">
            <Radio className="w-4 h-4" />
            <span className="text-sm font-semibold mono">@BigoCuan</span>
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((k) => {
          const Icon = k.icon;
          return (
            <div key={k.label} className="card-dark p-5" data-testid={k.testid}>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">{k.label}</span>
                <Icon className={`w-5 h-5 ${k.color}`} />
              </div>
              <div className="mono text-2xl font-bold text-white">{k.value}</div>
              {k.sub && <div className="text-xs text-slate-500 mt-1">{k.sub}</div>}
            </div>
          );
        })}
      </div>

      {/* Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 card-dark p-6">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-xl font-bold heading text-white">Aktivitas 7 Hari Terakhir</h3>
            <span className="badge-status badge-info">Submissions</span>
          </div>
          <div className="flex items-end gap-3 h-48">
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
          <h3 className="text-xl font-bold heading text-white mb-6">E-Wallet Distribution</h3>
          {(s.wallet_distribution || []).length === 0 ? (
            <p className="text-slate-500 text-sm">Belum ada data payout.</p>
          ) : (
            <div className="space-y-4">
              {s.wallet_distribution.map((w) => (
                <div key={w._id}>
                  <div className="flex items-center justify-between mb-1">
                    <span className={`chip-method ${methodClass(w._id)}`}>{w._id}</span>
                    <span className="text-xs text-slate-400 mono">{w.count}x · {fmtIDR(w.total)}</span>
                  </div>
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
  const load = () => api("GET", "/submissions?status_filter=pending").then((d) => setSubs(d.slice(0, 5))).catch(() => {});
  useEffect(() => { load(); }, []);

  return (
    <div className="card-dark p-6" data-testid="quick-approval-widget">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xl font-bold heading text-white">Task Menunggu Verifikasi</h3>
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

// ---------- Tasks Page ----------
function TasksPage() {
  const api = useApi();
  const [tasks, setTasks] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = () => api("GET", "/tasks").then(setTasks).catch(() => {});
  useEffect(() => { load(); }, []);

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

  return (
    <div className="space-y-6 animate-fadein" data-testid="tasks-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-extrabold heading text-white">Task Management</h1>
          <p className="text-slate-400 mt-1">Buat dan kelola task yang bisa dikerjakan user</p>
        </div>
        <button className="btn-primary flex items-center gap-2" data-testid="create-task-button" onClick={() => { setEditing(null); setShowModal(true); }}>
          <Plus className="w-4 h-4" /> Buat Task Baru
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {tasks.length === 0 ? (
          <div className="card-dark p-12 text-center col-span-full">
            <ListTodo className="w-12 h-12 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">Belum ada task. Buat task pertama Anda!</p>
          </div>
        ) : tasks.map((t) => (
          <div key={t.id} className="card-dark p-5" data-testid={`task-card-${t.id}`}>
            <div className="flex items-start justify-between mb-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`badge-status ${t.active ? "badge-approved" : "badge-rejected"}`}>{t.active ? "AKTIF" : "PAUSE"}</span>
                </div>
                <h3 className="text-lg font-bold text-white truncate">{t.title}</h3>
              </div>
              <div className="text-right">
                <div className="text-emerald-400 mono font-bold text-lg">{fmtIDR(t.reward)}</div>
              </div>
            </div>
            <p className="text-sm text-slate-400 line-clamp-2 mb-4">{t.description}</p>
            <div className="flex items-center justify-between text-xs text-slate-500 mb-4 pb-4 border-b border-slate-800">
              <span>✅ {t.approved_count} selesai</span>
              <span>⏳ {t.pending_count} pending</span>
              <span>{t.max_slots > 0 ? `${t.slots_used}/${t.max_slots} slot` : "∞ slot"}</span>
            </div>
            <div className="flex gap-2">
              <button className="btn-ghost flex-1 flex items-center justify-center gap-1" data-testid={`edit-task-${t.id}`} onClick={() => { setEditing(t); setShowModal(true); }}>
                <Edit2 className="w-3 h-3" /> Edit
              </button>
              <button className="btn-ghost flex-1" data-testid={`toggle-task-${t.id}`} onClick={() => toggle(t)}>
                {t.active ? "Pause" : "Aktifkan"}
              </button>
              <button className="btn-danger" data-testid={`delete-task-${t.id}`} onClick={() => del(t.id)}>
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {showModal && <TaskModal task={editing} onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); load(); }} />}
    </div>
  );
}

function TaskModal({ task, onClose, onSaved }) {
  const api = useApi();
  const [form, setForm] = useState(task || { title: "", description: "", reward: 5000, instructions: "", link: "", max_slots: 0 });
  const [loading, setLoading] = useState(false);

  const save = async () => {
    if (!form.title || !form.description || !form.reward) { toast.error("Isi field yang wajib"); return; }
    setLoading(true);
    try {
      if (task) await api("PATCH", `/tasks/${task.id}`, form);
      else await api("POST", "/tasks", form);
      toast.success(task ? "Task diperbarui" : "Task dibuat");
      onSaved();
    } catch (e) { toast.error("Gagal menyimpan"); }
    finally { setLoading(false); }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} data-testid="task-modal">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold heading text-white">{task ? "Edit Task" : "Buat Task Baru"}</h2>
          <button className="text-slate-400 hover:text-white" onClick={onClose}><X className="w-5 h-5" /></button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Judul Task *</label>
            <input className="input-dark" data-testid="task-title-input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Contoh: Follow akun TikTok" />
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Deskripsi *</label>
            <textarea className="textarea-dark" data-testid="task-description-input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Deskripsi singkat task" />
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Instruksi Lengkap</label>
            <textarea className="textarea-dark" data-testid="task-instructions-input" value={form.instructions} onChange={(e) => setForm({ ...form, instructions: e.target.value })} placeholder="Langkah-langkah detail (opsional)" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Reward (Rp) *</label>
              <input className="input-dark mono" data-testid="task-reward-input" type="number" value={form.reward} onChange={(e) => setForm({ ...form, reward: Number(e.target.value) })} />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Max Slot (0 = unlimited)</label>
              <input className="input-dark mono" data-testid="task-slots-input" type="number" value={form.max_slots} onChange={(e) => setForm({ ...form, max_slots: Number(e.target.value) })} />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Preview Reward</label>
              <div className="input-dark mono text-emerald-400 font-bold">{fmtIDR(form.reward)}</div>
            </div>
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Link (opsional)</label>
            <input className="input-dark" data-testid="task-link-input" value={form.link || ""} onChange={(e) => setForm({ ...form, link: e.target.value })} placeholder="https://..." />
          </div>
        </div>
        <div className="flex gap-3 mt-6">
          <button className="btn-ghost flex-1" onClick={onClose} data-testid="task-modal-cancel">Batal</button>
          <button className="btn-primary flex-1 flex items-center justify-center gap-2" onClick={save} disabled={loading} data-testid="task-modal-save">
            {loading && <Loader2 className="w-4 h-4 animate-spin" />} Simpan
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------- Submissions Page ----------
function SubmissionsPage() {
  const api = useApi();
  const [subs, setSubs] = useState([]);
  const [filter, setFilter] = useState("pending");
  const [preview, setPreview] = useState(null);

  const load = () => api("GET", `/submissions?status_filter=${filter}`).then(setSubs).catch(() => {});
  useEffect(() => { load(); }, [filter]);

  const approve = async (s) => {
    await api("POST", `/submissions/${s.id}/approve`);
    toast.success(`Disetujui! ${fmtIDR(s.task?.reward)} ditambahkan ke user.`);
    load();
  };
  const reject = async (s, reason) => {
    await api("POST", `/submissions/${s.id}/reject`, { reason });
    toast.success("Task ditolak");
    load();
  };

  return (
    <div className="space-y-6 animate-fadein" data-testid="submissions-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-extrabold heading text-white">Task Submissions</h1>
          <p className="text-slate-400 mt-1">Verifikasi bukti pengerjaan task</p>
        </div>
        <div className="flex gap-2">
          {["pending", "approved", "rejected", "all"].map((f) => (
            <button key={f} className={filter === f ? "btn-primary" : "btn-ghost"} data-testid={`filter-${f}`} onClick={() => setFilter(f)}>
              {f.toUpperCase()}
            </button>
          ))}
        </div>
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
                <div className="flex items-start justify-between gap-4 mb-2">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`badge-status badge-${s.status}`}>{s.status.toUpperCase()}</span>
                      <span className="text-xs text-slate-500">{fmtDate(s.created_at)}</span>
                    </div>
                    <h3 className="text-lg font-bold text-white">{s.task?.title || "Task"}</h3>
                    <div className="text-sm text-slate-400 mt-1">@{s.user?.username || "no_username"} · <span className="mono">{s.telegram_id}</span></div>
                  </div>
                  <div className="text-emerald-400 mono font-bold text-lg text-right">{fmtIDR(s.task?.reward || 0)}</div>
                </div>
                {s.proof_text && <p className="text-sm text-slate-300 bg-slate-800/50 p-3 rounded-lg mt-2">&ldquo;{s.proof_text}&rdquo;</p>}
                {s.reject_reason && <p className="text-sm text-red-400 mt-2">Alasan tolak: {s.reject_reason}</p>}

                {s.status === "pending" && (
                  <div className="flex gap-2 mt-4">
                    <button className="btn-primary flex items-center gap-2" data-testid={`approve-submission-${s.id}`} onClick={() => approve(s)}>
                      <Check className="w-4 h-4" /> Setujui
                    </button>
                    <button className="btn-danger flex items-center gap-2" data-testid={`reject-submission-${s.id}`} onClick={() => {
                      const reason = window.prompt("Alasan penolakan:", "Bukti tidak valid");
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

// ---------- Withdrawals Page ----------
function WithdrawalsPage() {
  const api = useApi();
  const [wds, setWds] = useState([]);
  const [filter, setFilter] = useState("pending");
  const [approving, setApproving] = useState(null);

  const load = () => api("GET", `/withdrawals?status_filter=${filter}`).then(setWds).catch(() => {});
  useEffect(() => { load(); }, [filter]);

  const reject = async (w) => {
    const reason = window.prompt("Alasan penolakan withdraw:", "Data tidak sesuai");
    if (!reason) return;
    await api("POST", `/withdrawals/${w.id}/reject`, { reason });
    toast.success("Withdraw ditolak, saldo direfund.");
    load();
  };

  return (
    <div className="space-y-6 animate-fadein" data-testid="withdrawals-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-extrabold heading text-white">Withdrawal Requests</h1>
          <p className="text-slate-400 mt-1">Proses pembayaran & broadcast bukti ke <span className="text-emerald-400 mono">@BigoCuan</span></p>
        </div>
        <div className="flex gap-2">
          {["pending", "approved", "rejected", "all"].map((f) => (
            <button key={f} className={filter === f ? "btn-primary" : "btn-ghost"} data-testid={`wd-filter-${f}`} onClick={() => setFilter(f)}>
              {f.toUpperCase()}
            </button>
          ))}
        </div>
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
                <div className="flex items-center gap-2 mb-2">
                  <span className={`badge-status badge-${w.status}`}>{w.status.toUpperCase()}</span>
                  <span className={`chip-method ${methodClass(w.method)}`}>{w.method}</span>
                  <span className="text-xs text-slate-500">{fmtDate(w.created_at)}</span>
                </div>
                <div className="mono text-2xl font-bold text-white">{fmtIDR(w.amount)}</div>
                <div className="text-sm text-slate-400 mt-1">
                  <span className="mono">{w.account_number}</span> · <span className="font-semibold">{w.account_name}</span>
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  @{w.user?.username || "no_username"} · <span className="mono">{w.telegram_id}</span>
                </div>
                {w.admin_note && <p className="text-sm text-slate-300 mt-2">📝 {w.admin_note}</p>}
                {w.reject_reason && <p className="text-sm text-red-400 mt-2">❌ {w.reject_reason}</p>}
              </div>
              {w.status === "pending" ? (
                <div className="flex gap-2 flex-shrink-0">
                  <button className="btn-primary flex items-center gap-2" data-testid={`approve-wd-${w.id}`} onClick={() => setApproving(w)}>
                    <Send className="w-4 h-4" /> Proses & Broadcast
                  </button>
                  <button className="btn-danger" data-testid={`reject-wd-${w.id}`} onClick={() => reject(w)}>
                    <X className="w-4 h-4" />
                  </button>
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
    const b64 = await fileToBase64(f);
    setImage(b64);
  };

  const submit = async () => {
    if (!image) { toast.error("Upload bukti pembayaran (foto) dulu"); return; }
    setLoading(true);
    try {
      await api("POST", `/withdrawals/${wd.id}/approve`, { note, image_base64: image });
      toast.success("Berhasil! Bukti dikirim ke user & di-broadcast ke @BigoCuan");
      onDone();
    } catch (e) { toast.error("Gagal memproses"); }
    finally { setLoading(false); }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} data-testid="wd-approve-modal">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold heading text-white">Proses Withdraw</h2>
          <button className="text-slate-400 hover:text-white" onClick={onClose}><X className="w-5 h-5" /></button>
        </div>
        <div className="p-4 rounded-lg bg-slate-800/40 border border-slate-800 mb-4">
          <div className="mono text-2xl font-bold text-emerald-400 mb-2">{fmtIDR(wd.amount)}</div>
          <div className="text-sm">
            <span className={`chip-method ${methodClass(wd.method)}`}>{wd.method}</span>
            <span className="ml-2 mono text-slate-300">{wd.account_number}</span>
            <span className="ml-2 text-white font-semibold">{wd.account_name}</span>
          </div>
          <div className="text-xs text-slate-500 mt-2">@{wd.user?.username || wd.telegram_id}</div>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Bukti Pembayaran (Foto) *</label>
            <label className="block w-full cursor-pointer" data-testid="wd-image-upload-label">
              <input type="file" accept="image/*" onChange={onFile} className="hidden" data-testid="wd-image-upload" />
              <div className="input-dark flex items-center gap-3 py-6 border-dashed">
                {image ? (
                  <img src={image} alt="preview" className="w-16 h-16 rounded object-cover" />
                ) : (
                  <Upload className="w-8 h-8 text-slate-500" />
                )}
                <div className="text-sm">
                  {image ? <span className="text-emerald-400">Bukti terupload ✓ Klik untuk ganti</span> : <span className="text-slate-400">Klik untuk upload foto bukti transfer</span>}
                </div>
              </div>
            </label>
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Keterangan / Caption</label>
            <textarea className="textarea-dark" data-testid="wd-note-input" value={note} onChange={(e) => setNote(e.target.value)} />
          </div>

          <div className="p-4 rounded-lg bg-blue-500/5 border border-blue-500/20 text-sm text-slate-300">
            <div className="flex items-center gap-2 mb-2 text-blue-400 font-semibold">
              <Radio className="w-4 h-4" /> Preview Broadcast @BigoCuan
            </div>
            <div className="mono text-xs whitespace-pre-line text-slate-400">
              💸 <b>BUKTI PEMBAYARAN WITHDRAW</b>{"\n\n"}
              👤 Nama: <b>{wd.user?.first_name || wd.user?.username || "User"}</b>{"\n"}
              🆔 Username: {wd.user?.username ? `@${wd.user.username}` : "(no username)"}{"\n"}
              💰 Nominal: <b>{fmtIDR(wd.amount)}</b>{"\n"}
              🏦 Metode: <b>{wd.method}</b>{"\n\n"}
              {note}
            </div>
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

// ---------- Users Page ----------
function UsersPage() {
  const api = useApi();
  const [users, setUsers] = useState([]);
  const [q, setQ] = useState("");
  const [detail, setDetail] = useState(null);

  useEffect(() => { api("GET", "/users").then(setUsers).catch(() => {}); }, [api]);

  const filtered = users.filter((u) =>
    !q || (u.username || "").toLowerCase().includes(q.toLowerCase()) ||
    (u.first_name || "").toLowerCase().includes(q.toLowerCase()) ||
    String(u.telegram_id).includes(q)
  );

  return (
    <div className="space-y-6 animate-fadein" data-testid="users-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-extrabold heading text-white">Users Management</h1>
          <p className="text-slate-400 mt-1">{users.length} pengguna terdaftar</p>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input className="input-dark pl-10 w-72" placeholder="Cari username / ID..." value={q} onChange={(e) => setQ(e.target.value)} data-testid="user-search" />
        </div>
      </div>

      <div className="card-dark overflow-hidden">
        <table className="w-full">
          <thead className="bg-slate-800/40 text-xs uppercase tracking-wider text-slate-400">
            <tr>
              <th className="text-left p-4">User</th>
              <th className="text-left p-4">Telegram ID</th>
              <th className="text-right p-4">Saldo</th>
              <th className="text-right p-4">Total Earned</th>
              <th className="text-center p-4">Task Selesai</th>
              <th className="text-center p-4">Bank</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr><td colSpan="7" className="p-12 text-center text-slate-500">Belum ada user. User akan muncul setelah /start di bot.</td></tr>
            ) : filtered.map((u) => (
              <tr key={u.telegram_id} className="border-t border-slate-800 hover:bg-slate-800/20" data-testid={`user-row-${u.telegram_id}`}>
                <td className="p-4">
                  <div className="font-semibold text-white">{u.first_name || "-"}</div>
                  <div className="text-xs text-slate-400">@{u.username || "no_username"}</div>
                </td>
                <td className="p-4 mono text-sm text-slate-300">{u.telegram_id}</td>
                <td className="p-4 mono font-bold text-emerald-400 text-right">{fmtIDR(u.balance)}</td>
                <td className="p-4 mono text-slate-300 text-right">{fmtIDR(u.total_earned)}</td>
                <td className="p-4 text-center text-slate-300">{u.tasks_completed}</td>
                <td className="p-4 text-center">
                  {u.bank ? <span className={`chip-method ${methodClass(u.bank.method)}`}>{u.bank.method}</span> : <span className="text-slate-600 text-xs">-</span>}
                </td>
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
    await api("POST", `/users/${telegramId}/adjust`, { amount: Number(adjustAmt), note: adjustNote });
    toast.success("Saldo disesuaikan");
    setAdjustAmt(0); setAdjustNote("");
    load();
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
          <button className="text-slate-400 hover:text-white" onClick={onClose}><X className="w-5 h-5" /></button>
        </div>

        <div className="grid grid-cols-3 gap-3 mb-6">
          <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
            <div className="text-xs text-slate-400">Saldo</div>
            <div className="mono font-bold text-emerald-400">{fmtIDR(u.balance)}</div>
          </div>
          <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-800">
            <div className="text-xs text-slate-400">Total Earned</div>
            <div className="mono font-bold text-white">{fmtIDR(u.total_earned)}</div>
          </div>
          <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-800">
            <div className="text-xs text-slate-400">Task Selesai</div>
            <div className="mono font-bold text-white">{u.tasks_completed}</div>
          </div>
        </div>

        {u.bank && (
          <div className="mb-6 p-4 rounded-lg bg-slate-800/40 border border-slate-800">
            <div className="text-xs uppercase tracking-wider text-slate-400 mb-2">Info Pembayaran</div>
            <div className="flex items-center gap-3">
              <span className={`chip-method ${methodClass(u.bank.method)}`}>{u.bank.method}</span>
              <span className="mono">{u.bank.account_number}</span>
              <span className="font-semibold">{u.bank.account_name}</span>
            </div>
          </div>
        )}

        <div className="mb-6 p-4 rounded-lg bg-amber-500/5 border border-amber-500/20">
          <div className="text-xs uppercase tracking-wider text-amber-400 mb-2 font-semibold">Penyesuaian Saldo</div>
          <div className="flex gap-2">
            <input type="number" className="input-dark mono" placeholder="Nominal (- untuk kurangi)" value={adjustAmt} onChange={(e) => setAdjustAmt(e.target.value)} data-testid="adjust-amount" />
            <input className="input-dark flex-1" placeholder="Keterangan" value={adjustNote} onChange={(e) => setAdjustNote(e.target.value)} data-testid="adjust-note" />
            <button className="btn-primary" onClick={adjust} data-testid="adjust-submit">Terapkan</button>
          </div>
        </div>

        <div>
          <h3 className="text-lg font-bold heading text-white mb-3">Riwayat Saldo</h3>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {data.balance_history.length === 0 ? <p className="text-slate-500 text-sm">Belum ada.</p> :
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

// ---------- Broadcast Page ----------
function BroadcastPage() {
  const api = useApi();
  const [logs, setLogs] = useState([]);
  const [text, setText] = useState("");
  const [image, setImage] = useState(null);
  const [sending, setSending] = useState(false);

  const load = () => api("GET", "/broadcast/logs").then(setLogs).catch(() => {});
  useEffect(() => { load(); }, []);

  const send = async () => {
    if (!text) { toast.error("Isi teks broadcast dulu"); return; }
    setSending(true);
    try {
      await api("POST", "/broadcast/manual", { text, image_base64: image });
      toast.success("Broadcast terkirim ke @BigoCuan");
      setText(""); setImage(null);
      load();
    } catch (e) { toast.error("Gagal broadcast"); }
    finally { setSending(false); }
  };

  const onFile = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    setImage(await fileToBase64(f));
  };

  return (
    <div className="space-y-6 animate-fadein" data-testid="broadcast-page">
      <div>
        <h1 className="text-4xl font-extrabold heading text-white">Broadcast @BigoCuan</h1>
        <p className="text-slate-400 mt-1">Log pesan otomatis & manual broadcast ke channel</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card-dark p-6">
          <h3 className="text-xl font-bold heading text-white mb-4">Kirim Manual</h3>
          <div className="space-y-4">
            <textarea className="textarea-dark" placeholder="Tulis pesan..." value={text} onChange={(e) => setText(e.target.value)} data-testid="broadcast-text-input" />
            <label className="block cursor-pointer">
              <input type="file" accept="image/*" className="hidden" onChange={onFile} data-testid="broadcast-image-upload" />
              <div className="input-dark flex items-center gap-3 py-4 border-dashed cursor-pointer">
                {image ? <img src={image} alt="preview" className="w-12 h-12 rounded object-cover" /> : <ImageIcon className="w-6 h-6 text-slate-500" />}
                <span className="text-sm text-slate-400">{image ? "Gambar terupload ✓" : "Upload gambar (opsional)"}</span>
              </div>
            </label>
            <button className="btn-primary w-full flex items-center justify-center gap-2" onClick={send} disabled={sending} data-testid="broadcast-send">
              {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              Broadcast ke @BigoCuan
            </button>
          </div>
        </div>

        <div className="card-dark p-6">
          <h3 className="text-xl font-bold heading text-white mb-4">Info Channel</h3>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between p-3 rounded bg-slate-800/40">
              <span className="text-slate-400">Channel</span>
              <span className="text-emerald-400 mono font-bold">@BigoCuan</span>
            </div>
            <div className="flex justify-between p-3 rounded bg-slate-800/40">
              <span className="text-slate-400">Total Broadcasts</span>
              <span className="text-white mono font-bold">{logs.length}</span>
            </div>
            <div className="flex justify-between p-3 rounded bg-slate-800/40">
              <span className="text-slate-400">Auto Broadcast</span>
              <span className="text-emerald-400 font-bold">✓ AKTIF</span>
            </div>
          </div>
        </div>
      </div>

      <div className="card-dark p-6">
        <h3 className="text-xl font-bold heading text-white mb-4">Broadcast Log</h3>
        <div className="space-y-3">
          {logs.length === 0 ? (
            <p className="text-slate-500 text-sm">Belum ada broadcast.</p>
          ) : logs.map((l) => (
            <div key={l.id} className="flex gap-3 p-4 rounded-lg bg-slate-800/30 border border-slate-800" data-testid={`broadcast-log-${l.id}`}>
              {l.image_base64 && <img src={l.image_base64} alt="" className="w-20 h-20 object-cover rounded" />}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`badge-status ${l.type === "manual" ? "badge-info" : "badge-approved"}`}>{l.type.toUpperCase()}</span>
                  <span className="text-xs text-slate-500">{fmtDate(l.created_at)}</span>
                </div>
                <p className="text-sm text-slate-300 whitespace-pre-line line-clamp-4">{l.text}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------- Protected route ----------
function Protected({ children }) {
  const { token } = useAuth();
  if (!token) return <Navigate to="/login" />;
  return <Layout>{children}</Layout>;
}

// ---------- App ----------
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
          <Route path="/broadcast" element={<Protected><BroadcastPage /></Protected>} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
