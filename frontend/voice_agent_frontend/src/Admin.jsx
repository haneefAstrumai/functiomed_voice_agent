import { useState, useEffect, useCallback } from "react";

// ─── Config ───────────────────────────────────────────────────
const BACKEND_URL = "http://localhost:8000";

// ─── Helpers ──────────────────────────────────────────────────
const SERVICE_COLORS = {
  physiotherapy:        { bg: "#e0f2fe", text: "#0369a1", dot: "#0ea5e9" },
  massage:              { bg: "#fdf4ff", text: "#7e22ce", dot: "#a855f7" },
  osteopathy:           { bg: "#fef9c3", text: "#854d0e", dot: "#eab308" },
  "mental coaching":    { bg: "#dcfce7", text: "#166534", dot: "#22c55e" },
  ergotherapy:          { bg: "#fff7ed", text: "#9a3412", dot: "#f97316" },
  acupuncture:          { bg: "#fce7f3", text: "#9d174d", dot: "#ec4899" },
  "nutrition counseling":{ bg: "#ecfdf5", text: "#065f46", dot: "#10b981" },
};

const getServiceStyle = (service) =>
  SERVICE_COLORS[service?.toLowerCase()] || {
    bg: "#f1f5f9", text: "#475569", dot: "#94a3b8",
  };

const STATUS_STYLES = {
  confirmed:  { bg: "#dcfce7", text: "#166534", label: "Confirmed" },
  cancelled:  { bg: "#fee2e2", text: "#991b1b", label: "Cancelled"  },
};

const formatDate = (d) => {
  if (!d) return "—";
  const [y, m, day] = d.split("-");
  const months = ["Jan","Feb","Mar","Apr","May","Jun",
                   "Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${months[parseInt(m)-1]} ${parseInt(day)}, ${y}`;
};

const formatTime = (t) => {
  if (!t) return "—";
  const [h, min] = t.split(":");
  const hour = parseInt(h);
  const ampm = hour >= 12 ? "PM" : "AM";
  const h12  = hour % 12 || 12;
  return `${h12}:${min} ${ampm}`;
};

const todayStr = () => new Date().toISOString().split("T")[0];

// ─── Stat Card ────────────────────────────────────────────────
function StatCard({ icon, label, value, sub, color }) {
  return (
    <div style={{
      background: "#fff",
      borderRadius: 16,
      padding: "1.25rem 1.5rem",
      border: "1px solid #f1f5f9",
      boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
      display: "flex",
      alignItems: "center",
      gap: "1rem",
      flex: "1 1 160px",
      minWidth: 0,
    }}>
      <div style={{
        width: 48, height: 48, borderRadius: 12,
        background: color + "22",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: "1.4rem", flexShrink: 0,
      }}>{icon}</div>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: "0.73rem", color: "#94a3b8",
                      fontWeight: 600, textTransform: "uppercase",
                      letterSpacing: "0.06em", marginBottom: 2 }}>
          {label}
        </div>
        <div style={{ fontSize: "1.6rem", fontWeight: 800,
                      color: "#0f172a", lineHeight: 1.1 }}>
          {value}
        </div>
        {sub && (
          <div style={{ fontSize: "0.72rem", color: "#94a3b8", marginTop: 2 }}>
            {sub}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Service Badge ────────────────────────────────────────────
function ServiceBadge({ service }) {
  const s = getServiceStyle(service);
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      background: s.bg, color: s.text,
      borderRadius: 999, padding: "3px 10px",
      fontSize: "0.75rem", fontWeight: 600, whiteSpace: "nowrap",
    }}>
      <span style={{ width: 7, height: 7, borderRadius: "50%",
                     background: s.dot, flexShrink: 0 }} />
      {service ? service.charAt(0).toUpperCase() + service.slice(1) : "—"}
    </span>
  );
}

// ─── Status Badge ─────────────────────────────────────────────
function StatusBadge({ status }) {
  const s = STATUS_STYLES[status] || STATUS_STYLES.confirmed;
  return (
    <span style={{
      background: s.bg, color: s.text,
      borderRadius: 999, padding: "3px 10px",
      fontSize: "0.72rem", fontWeight: 700,
    }}>
      {s.label}
    </span>
  );
}

// ─── Row Detail Drawer ────────────────────────────────────────
function DetailDrawer({ appt, onClose }) {
  if (!appt) return null;
  const fields = [
    ["Patient",      appt.name],
    ["Service",      appt.service],
    ["Date",         formatDate(appt.date)],
    ["Time",         formatTime(appt.time)],
    ["Email",        appt.email],
    ["Phone",        appt.phone],
    ["Notes",        appt.notes || "None"],
    ["Status",       appt.status],
    ["Booking ID",   `#${appt.id}`],
    ["Booked at",    appt.created_at ? appt.created_at.split(".")[0].replace("T"," ") : "—"],
    ["Room ID",      appt.room_id || "—"],
  ];
  return (
    <>
      {/* Backdrop */}
      <div onClick={onClose} style={{
        position: "fixed", inset: 0, background: "rgba(15,23,42,0.35)",
        zIndex: 40, backdropFilter: "blur(2px)",
      }} />
      {/* Drawer */}
      <div style={{
        position: "fixed", top: 0, right: 0, bottom: 0,
        width: "min(380px, 100vw)",
        background: "#fff", zIndex: 50,
        boxShadow: "-8px 0 40px rgba(0,0,0,0.12)",
        display: "flex", flexDirection: "column",
        animation: "slideIn 0.22s ease",
      }}>
        <style>{`
          @keyframes slideIn {
            from { transform: translateX(100%); }
            to   { transform: translateX(0); }
          }
        `}</style>

        {/* Drawer header */}
        <div style={{
          padding: "1.25rem 1.5rem",
          borderBottom: "1px solid #f1f5f9",
          display: "flex", alignItems: "center",
          justifyContent: "space-between",
        }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: "1rem", color: "#0f172a" }}>
              Appointment #{appt.id}
            </div>
            <div style={{ fontSize: "0.75rem", color: "#94a3b8", marginTop: 2 }}>
              Full details
            </div>
          </div>
          <button onClick={onClose} style={{
            border: "none", background: "#f1f5f9",
            borderRadius: 8, width: 32, height: 32,
            cursor: "pointer", fontSize: "1rem",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>✕</button>
        </div>

        {/* Avatar */}
        <div style={{
          padding: "1.5rem", display: "flex",
          flexDirection: "column", alignItems: "center", gap: "0.5rem",
          borderBottom: "1px solid #f8fafc",
          background: "linear-gradient(135deg,#f8fafc,#f1f5f9)",
        }}>
          <div style={{
            width: 64, height: 64, borderRadius: "50%",
            background: "#e0f2fe", display: "flex",
            alignItems: "center", justifyContent: "center",
            fontSize: "1.8rem",
          }}>👤</div>
          <div style={{ fontWeight: 700, fontSize: "1.05rem", color: "#0f172a" }}>
            {appt.name}
          </div>
          <ServiceBadge service={appt.service} />
        </div>

        {/* Fields */}
        <div style={{ flex: 1, overflowY: "auto", padding: "1rem 1.5rem" }}>
          {fields.map(([label, value]) => (
            <div key={label} style={{
              display: "flex", justifyContent: "space-between",
              alignItems: "flex-start", gap: "1rem",
              padding: "0.7rem 0",
              borderBottom: "1px solid #f8fafc",
            }}>
              <span style={{ fontSize: "0.75rem", color: "#94a3b8",
                             fontWeight: 600, textTransform: "uppercase",
                             letterSpacing: "0.05em", flexShrink: 0, paddingTop: 2 }}>
                {label}
              </span>
              <span style={{ fontSize: "0.85rem", color: "#334155",
                             fontWeight: 500, textAlign: "right", wordBreak: "break-all" }}>
                {label === "Service" ? <ServiceBadge service={value} />
                : label === "Status" ? <StatusBadge status={value} />
                : value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

// ─── Main Admin Dashboard ─────────────────────────────────────
export default function Admin() {
  const [appointments, setAppointments] = useState([]);
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState("");
  const [lastRefresh, setLastRefresh]   = useState(null);

  // Filters
  const [filterDate, setFilterDate]       = useState("");
  const [filterService, setFilterService] = useState("all");
  const [filterStatus, setFilterStatus]   = useState("all");
  const [searchText, setSearchText]       = useState("");

  // UI state
  const [selectedAppt, setSelectedAppt] = useState(null);
  const [sortField, setSortField]        = useState("date");
  const [sortDir, setSortDir]            = useState("asc");

  // ── Fetch appointments ─────────────────────────────────────
  const fetchAppointments = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (filterDate) params.set("date", filterDate);
      const url = `${BACKEND_URL}/appointments${params.toString() ? "?" + params : ""}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setAppointments(data.appointments || []);
      setLastRefresh(new Date());
    } catch (e) {
      setError(`Could not load appointments: ${e.message}. Make sure FastAPI is running on port 8000.`);
    } finally {
      setLoading(false);
    }
  }, [filterDate]);

  useEffect(() => { fetchAppointments(); }, [fetchAppointments]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const id = setInterval(fetchAppointments, 30000);
    return () => clearInterval(id);
  }, [fetchAppointments]);

  // ── Filter + sort ──────────────────────────────────────────
  const filtered = appointments
    .filter(a => filterService === "all" || a.service === filterService)
    .filter(a => filterStatus  === "all" || a.status  === filterStatus)
    .filter(a => {
      if (!searchText) return true;
      const q = searchText.toLowerCase();
      return (
        a.name?.toLowerCase().includes(q)  ||
        a.email?.toLowerCase().includes(q) ||
        a.phone?.includes(q)               ||
        String(a.id).includes(q)
      );
    })
    .sort((a, b) => {
      let av = a[sortField] ?? "", bv = b[sortField] ?? "";
      if (sortField === "id") { av = +av; bv = +bv; }
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ?  1 : -1;
      return 0;
    });

  // ── Stats ──────────────────────────────────────────────────
  const total      = appointments.length;
  const confirmed  = appointments.filter(a => a.status === "confirmed").length;
  const todayCount = appointments.filter(a => a.date === todayStr()).length;
  const services   = [...new Set(appointments.map(a => a.service).filter(Boolean))];

  // ── Sort toggle ────────────────────────────────────────────
  const toggleSort = (field) => {
    if (sortField === field) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortField(field); setSortDir("asc"); }
  };

  const SortIcon = ({ field }) => {
    if (sortField !== field) return <span style={{ color: "#cbd5e1" }}> ⇅</span>;
    return <span style={{ color: "#3b82f6" }}>{sortDir === "asc" ? " ↑" : " ↓"}</span>;
  };

  // ── CSV export ─────────────────────────────────────────────
  const exportCSV = () => {
    const header = ["ID","Name","Email","Phone","Service","Date","Time","Status","Notes","Created"];
    const rows   = filtered.map(a =>
      [a.id, a.name, a.email, a.phone, a.service,
       a.date, a.time, a.status, a.notes, a.created_at]
      .map(v => `"${(v??'').toString().replace(/"/g,'""')}"`)
      .join(",")
    );
    const csv  = [header.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `appointments_${new Date().toISOString().split("T")[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── Column header helper ───────────────────────────────────
  const Th = ({ field, label, align = "left" }) => (
    <th onClick={() => toggleSort(field)} style={{
      padding: "0.75rem 1rem", textAlign: align,
      fontSize: "0.72rem", fontWeight: 700, color: "#64748b",
      textTransform: "uppercase", letterSpacing: "0.07em",
      cursor: "pointer", userSelect: "none", whiteSpace: "nowrap",
      background: "#f8fafc",
      borderBottom: "1px solid #e2e8f0",
    }}>
      {label}<SortIcon field={field} />
    </th>
  );

  // ─────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────
  return (
    <div style={{
      minHeight: "100vh",
      background: "#f8fafc",
      fontFamily: "'DM Sans', 'Segoe UI', system-ui, sans-serif",
    }}>
      {/* ── Sidebar + Main layout ── */}
      <div style={{ display: "flex", minHeight: "100vh" }}>

        {/* ── Sidebar ── */}
        <aside style={{
          width: 220, background: "#0f172a", flexShrink: 0,
          display: "flex", flexDirection: "column", padding: "1.5rem 0",
          position: "sticky", top: 0, height: "100vh",
        }}>
          {/* Logo */}
          <div style={{ padding: "0 1.25rem 1.5rem", borderBottom: "1px solid #1e293b" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
              <div style={{
                width: 36, height: 36, borderRadius: 10,
                background: "#3b82f6",
                display: "flex", alignItems: "center",
                justifyContent: "center", fontSize: "1.1rem",
              }}>🏥</div>
              <div>
                <div style={{ color: "#fff", fontWeight: 700, fontSize: "0.95rem" }}>
                  Functiomed
                </div>
                <div style={{ color: "#64748b", fontSize: "0.68rem" }}>Admin Portal</div>
              </div>
            </div>
          </div>

          {/* Nav */}
          <nav style={{ padding: "1rem 0.75rem", flex: 1 }}>
            {[
              { icon: "📋", label: "Appointments", active: true }
            ].map(item => (
              <div key={item.label} style={{
                display: "flex", alignItems: "center", gap: "0.6rem",
                padding: "0.6rem 0.75rem", borderRadius: 8, marginBottom: 2,
                background: item.active ? "#1e3a5f" : "transparent",
                color: item.active ? "#93c5fd" : "#64748b",
                cursor: "pointer", fontSize: "0.85rem", fontWeight: 500,
                transition: "all 0.15s",
              }}>
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </div>
            ))}
          </nav>

          {/* Bottom */}
          <div style={{ padding: "0 1rem", borderTop: "1px solid #1e293b", paddingTop: "1rem" }}>
            <div style={{ fontSize: "0.7rem", color: "#475569", textAlign: "center" }}>
              {lastRefresh
                ? `Last updated ${lastRefresh.toLocaleTimeString()}`
                : "Loading..."}
            </div>
          </div>
        </aside>

        {/* ── Main Content ── */}
        <main style={{ flex: 1, padding: "2rem", overflowX: "auto", minWidth: 0 }}>

          {/* ── Page header ── */}
          <div style={{
            display: "flex", alignItems: "flex-start",
            justifyContent: "space-between", gap: "1rem",
            marginBottom: "1.75rem", flexWrap: "wrap",
          }}>
            <div>
              <h1 style={{ fontSize: "1.5rem", fontWeight: 800,
                           color: "#0f172a", margin: 0 }}>
                Appointments
              </h1>
              <p style={{ color: "#94a3b8", fontSize: "0.83rem", marginTop: 4 }}>
                All bookings saved from the Voice AI assistant
              </p>
            </div>
            <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
              <button onClick={fetchAppointments} disabled={loading} style={{
                display: "flex", alignItems: "center", gap: "0.4rem",
                padding: "0.55rem 1rem", borderRadius: 8, border: "1px solid #e2e8f0",
                background: "#fff", color: "#475569", fontSize: "0.82rem",
                fontWeight: 600, cursor: loading ? "not-allowed" : "pointer",
              }}>
                <span style={{
                  display: "inline-block",
                  animation: loading ? "spin 1s linear infinite" : "none",
                }}>🔄</span>
                {loading ? "Loading..." : "Refresh"}
              </button>
              <button onClick={exportCSV} disabled={filtered.length === 0} style={{
                display: "flex", alignItems: "center", gap: "0.4rem",
                padding: "0.55rem 1rem", borderRadius: 8, border: "none",
                background: "#3b82f6", color: "#fff", fontSize: "0.82rem",
                fontWeight: 600, cursor: filtered.length === 0 ? "not-allowed" : "pointer",
                opacity: filtered.length === 0 ? 0.5 : 1,
              }}>
                ⬇ Export CSV
              </button>
            </div>
          </div>

          {/* ── Stat cards ── */}
          <div style={{
            display: "flex", gap: "1rem",
            flexWrap: "wrap", marginBottom: "1.5rem",
          }}>
            <StatCard icon="📋" label="Total Bookings" value={total}
                      sub="all time" color="#3b82f6" />
            <StatCard icon="✅" label="Confirmed"      value={confirmed}
                      sub={`${total - confirmed} cancelled`} color="#22c55e" />
            <StatCard icon="📅" label="Today"          value={todayCount}
                      sub={new Date().toLocaleDateString("en-US",{weekday:"long"})} color="#f59e0b" />
            <StatCard icon="💊" label="Services"       value={services.length}
                      sub="types offered" color="#a855f7" />
          </div>

          {/* ── Error banner ── */}
          {error && (
            <div style={{
              background: "#fef2f2", border: "1px solid #fecaca",
              borderRadius: 12, padding: "0.85rem 1rem",
              color: "#dc2626", fontSize: "0.83rem",
              display: "flex", alignItems: "center", gap: "0.5rem",
              marginBottom: "1rem",
            }}>
              ❌ {error}
            </div>
          )}

          {/* ── Filter bar ── */}
          <div style={{
            background: "#fff", borderRadius: 14,
            padding: "1rem 1.25rem",
            border: "1px solid #f1f5f9",
            boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
            display: "flex", gap: "0.75rem",
            flexWrap: "wrap", alignItems: "center",
            marginBottom: "1rem",
          }}>
            {/* Search */}
            <div style={{ position: "relative", flex: "1 1 180px", minWidth: 0 }}>
              <span style={{ position: "absolute", left: 10, top: "50%",
                             transform: "translateY(-50%)", color: "#94a3b8" }}>
                🔍
              </span>
              <input
                value={searchText}
                onChange={e => setSearchText(e.target.value)}
                placeholder="Search name, email, phone, ID..."
                style={{
                  width: "100%", padding: "0.5rem 0.75rem 0.5rem 2.1rem",
                  border: "1px solid #e2e8f0", borderRadius: 8,
                  fontSize: "0.83rem", color: "#334155", outline: "none",
                  background: "#f8fafc", boxSizing: "border-box",
                }}
              />
            </div>

            {/* Date filter */}
            <input
              type="date"
              value={filterDate}
              onChange={e => setFilterDate(e.target.value)}
              style={{
                padding: "0.5rem 0.75rem", border: "1px solid #e2e8f0",
                borderRadius: 8, fontSize: "0.83rem", color: "#334155",
                background: "#f8fafc", outline: "none", flex: "0 0 auto",
              }}
            />

            {/* Service filter */}
            <select value={filterService} onChange={e => setFilterService(e.target.value)} style={{
              padding: "0.5rem 0.75rem", border: "1px solid #e2e8f0",
              borderRadius: 8, fontSize: "0.83rem", color: "#334155",
              background: "#f8fafc", outline: "none", flex: "0 0 auto",
              cursor: "pointer",
            }}>
              <option value="all">All Services</option>
              {services.map(s => (
                <option key={s} value={s}>
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                </option>
              ))}
            </select>

            {/* Status filter */}
            <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} style={{
              padding: "0.5rem 0.75rem", border: "1px solid #e2e8f0",
              borderRadius: 8, fontSize: "0.83rem", color: "#334155",
              background: "#f8fafc", outline: "none", flex: "0 0 auto",
              cursor: "pointer",
            }}>
              <option value="all">All Statuses</option>
              <option value="confirmed">Confirmed</option>
              <option value="cancelled">Cancelled</option>
            </select>

            {/* Clear filters */}
            {(filterDate || filterService !== "all" || filterStatus !== "all" || searchText) && (
              <button onClick={() => {
                setFilterDate(""); setFilterService("all");
                setFilterStatus("all"); setSearchText("");
              }} style={{
                padding: "0.5rem 0.9rem", border: "1px solid #fca5a5",
                borderRadius: 8, background: "#fff5f5", color: "#dc2626",
                fontSize: "0.8rem", fontWeight: 600, cursor: "pointer",
                flexShrink: 0,
              }}>
                ✕ Clear
              </button>
            )}

            <div style={{
              marginLeft: "auto", fontSize: "0.78rem", color: "#94a3b8",
              whiteSpace: "nowrap", flexShrink: 0,
            }}>
              {filtered.length} of {total} result{total !== 1 ? "s" : ""}
            </div>
          </div>

          {/* ── Table ── */}
          <div style={{
            background: "#fff", borderRadius: 16,
            border: "1px solid #f1f5f9",
            boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
            overflow: "hidden",
          }}>
            {loading && appointments.length === 0 ? (
              <div style={{
                padding: "4rem", textAlign: "center",
                color: "#94a3b8", fontSize: "0.9rem",
              }}>
                <div style={{ fontSize: "2rem", marginBottom: "0.75rem" }}>⏳</div>
                Loading appointments...
              </div>
            ) : filtered.length === 0 ? (
              <div style={{
                padding: "4rem", textAlign: "center",
                color: "#94a3b8",
              }}>
                <div style={{ fontSize: "3rem", marginBottom: "0.75rem" }}>📭</div>
                <div style={{ fontWeight: 600, color: "#475569", marginBottom: 4 }}>
                  No appointments found
                </div>
                <div style={{ fontSize: "0.82rem" }}>
                  {appointments.length === 0
                    ? "Book an appointment via the Voice AI assistant to see it here."
                    : "Try adjusting your filters."}
                </div>
              </div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr>
                      <Th field="id"      label="ID"      />
                      <Th field="name"    label="Patient" />
                      <Th field="service" label="Service" />
                      <Th field="date"    label="Date"    />
                      <Th field="time"    label="Time"    />
                      <Th field="status"  label="Status"  />
                      <th style={{
                        padding: "0.75rem 1rem", textAlign: "center",
                        fontSize: "0.72rem", fontWeight: 700, color: "#64748b",
                        textTransform: "uppercase", letterSpacing: "0.07em",
                        background: "#f8fafc", borderBottom: "1px solid #e2e8f0",
                      }}>
                        Details
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((appt, idx) => (
                      <tr key={appt.id} style={{
                        borderBottom: "1px solid #f8fafc",
                        background: idx % 2 === 0 ? "#fff" : "#fafbfc",
                        transition: "background 0.12s",
                        cursor: "default",
                      }}
                        onMouseEnter={e => e.currentTarget.style.background = "#eff6ff"}
                        onMouseLeave={e => e.currentTarget.style.background = idx % 2 === 0 ? "#fff" : "#fafbfc"}
                      >
                        {/* ID */}
                        <td style={{ padding: "0.85rem 1rem" }}>
                          <span style={{
                            fontFamily: "monospace", fontSize: "0.8rem",
                            color: "#94a3b8", fontWeight: 600,
                          }}>
                            #{appt.id}
                          </span>
                        </td>

                        {/* Patient */}
                        <td style={{ padding: "0.85rem 1rem" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                            <div style={{
                              width: 32, height: 32, borderRadius: "50%",
                              background: "#e0f2fe",
                              display: "flex", alignItems: "center",
                              justifyContent: "center", fontSize: "0.9rem",
                              flexShrink: 0,
                            }}>👤</div>
                            <div style={{ minWidth: 0 }}>
                              <div style={{ fontWeight: 600, fontSize: "0.85rem",
                                           color: "#0f172a", whiteSpace: "nowrap" }}>
                                {appt.name}
                              </div>
                              <div style={{ fontSize: "0.72rem", color: "#94a3b8",
                                           overflow: "hidden", textOverflow: "ellipsis",
                                           maxWidth: 180, whiteSpace: "nowrap" }}>
                                {appt.email}
                              </div>
                            </div>
                          </div>
                        </td>

                        {/* Service */}
                        <td style={{ padding: "0.85rem 1rem" }}>
                          <ServiceBadge service={appt.service} />
                        </td>

                        {/* Date */}
                        <td style={{ padding: "0.85rem 1rem" }}>
                          <div style={{ fontWeight: 500, fontSize: "0.83rem",
                                       color: "#334155", whiteSpace: "nowrap" }}>
                            {formatDate(appt.date)}
                          </div>
                        </td>

                        {/* Time */}
                        <td style={{ padding: "0.85rem 1rem" }}>
                          <div style={{
                            display: "inline-flex", alignItems: "center", gap: 5,
                            background: "#f1f5f9", borderRadius: 6,
                            padding: "3px 8px",
                          }}>
                            <span style={{ fontSize: "0.7rem" }}>🕐</span>
                            <span style={{ fontSize: "0.8rem", fontWeight: 600,
                                          color: "#475569", fontFamily: "monospace" }}>
                              {formatTime(appt.time)}
                            </span>
                          </div>
                        </td>

                        {/* Status */}
                        <td style={{ padding: "0.85rem 1rem" }}>
                          <StatusBadge status={appt.status} />
                        </td>

                        {/* View button */}
                        <td style={{ padding: "0.85rem 1rem", textAlign: "center" }}>
                          <button
                            onClick={() => setSelectedAppt(appt)}
                            style={{
                              border: "1px solid #e2e8f0",
                              background: "#fff", borderRadius: 7,
                              padding: "5px 12px", fontSize: "0.75rem",
                              fontWeight: 600, color: "#3b82f6",
                              cursor: "pointer", whiteSpace: "nowrap",
                              transition: "all 0.15s",
                            }}
                            onMouseEnter={e => {
                              e.currentTarget.style.background = "#eff6ff";
                              e.currentTarget.style.borderColor = "#93c5fd";
                            }}
                            onMouseLeave={e => {
                              e.currentTarget.style.background = "#fff";
                              e.currentTarget.style.borderColor = "#e2e8f0";
                            }}
                          >
                            View →
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Table footer */}
            {filtered.length > 0 && (
              <div style={{
                padding: "0.75rem 1.25rem",
                borderTop: "1px solid #f1f5f9",
                display: "flex", alignItems: "center",
                justifyContent: "space-between",
                background: "#f8fafc",
              }}>
                <span style={{ fontSize: "0.75rem", color: "#94a3b8" }}>
                  Showing {filtered.length} appointment{filtered.length !== 1 ? "s" : ""}
                </span>
                <span style={{ fontSize: "0.75rem", color: "#94a3b8" }}>
                  Auto-refreshes every 30 seconds
                </span>
              </div>
            )}
          </div>
        </main>
      </div>

      {/* ── Detail Drawer ── */}
      {selectedAppt && (
        <DetailDrawer
          appt={selectedAppt}
          onClose={() => setSelectedAppt(null)}
        />
      )}

      {/* Spin animation */}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        * { box-sizing: border-box; }
        input[type=date]::-webkit-calendar-picker-indicator {
          cursor: pointer; opacity: 0.6;
        }
      `}</style>
    </div>
  );
}