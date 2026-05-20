"use client";

import { useState, useEffect, useCallback } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Phone,
  History,
  BarChart3,
  Users,
  Settings,
  Activity,
  Mic,
  RefreshCcw,
  Plus,
  Cpu,
  Database,
  ShieldCheck,
  Globe,
  AlertCircle,
  CheckCircle,
  Clock,
  Loader2,
  Monitor,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import { cn } from "@/lib/utils";
import { StatCard } from "@/components/dashboard/StatCard";
import { TabButton } from "@/components/dashboard/TabButton";
import { SplashScreen } from "@/components/dashboard/SplashScreen";
import { VoiceOrb } from "@/components/VoiceOrb";

type TabId = "dial" | "calls" | "analytics" | "agents" | "system";

const TABS: { id: TabId; label: string; icon: typeof Phone }[] = [
  { id: "dial", label: "Dial", icon: Plus },
  { id: "calls", label: "Call Log", icon: History },
  { id: "analytics", label: "Analytics", icon: BarChart3 },
  { id: "agents", label: "Agents", icon: Users },
  { id: "system", label: "System", icon: Settings },
];

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Agent {
  id: string;
  name: string;
  description?: string;
  voice_english: string;
  voice_hindi: string;
  language_mode: string;
}

interface Call {
  id: string;
  call_sid: string;
  phone: string;
  status: string;
  intent?: string;
  follow_up_action?: string | null;
  sentiment_score?: number | null;
  recording_url?: string | null;
  duration_s: number;
  language: string;
  created_at: string;
}

interface CallTurn {
  turn_index: number;
  speaker: "user" | "agent";
  transcript: string;
  language?: string | null;
  intent?: string | null;
  sentiment?: number | null;
  latency_ms?: number | null;
  created_at?: string | null;
}

interface LatencyStats {
  sample_count: number;
  avg_stt_ms: number;
  avg_llm_ms: number;
  avg_tts_ms: number;
  avg_total_ms: number;
  p95_total_ms: number;
  recent: Array<Record<string, number>>;
}

interface Stats {
  total_calls_today: number;
  avg_duration_seconds: number;
  intent_breakdown: Record<string, number>;
  conversion_metrics?: {
    qualified_calls: number;
    conversion_rate_percent: number;
  };
  intent_false_positive_rate_percent?: number;
  recent_calls: Call[];
  active_calls: number;
  latency?: LatencyStats;
  _warning?: string;
}

interface HealthInfo {
  status: string;
  env?: string;
  db_enabled?: boolean;
  db_connected?: boolean;
  db_crm_ready?: boolean;
  groq_configured?: boolean;
  twilio_configured?: boolean;
}

const intentColors: Record<string, string> = {
  interested: "#34d399",
  high_ticket: "#f59e0b",
  confused: "#fbbf24",
  angry: "#ef4444",
  callback: "#818cf8",
  not_interested: "#71717a",
  neutral: "#6366f1",
  spam_invalid: "#dc2626",
};

function formatApiError(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) =>
        typeof d === "object" && d && "msg" in d ? String((d as { msg: string }).msg) : String(d)
      )
      .join("; ");
  }
  return "Request failed.";
}

const fmtDuration = (s: number) => {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
};

function previewE164(raw: string): string | null {
  const s = raw.trim();
  if (!s) return null;
  const digits = s.replace(/\D/g, "");
  if (s.startsWith("+")) {
    if (digits.startsWith("91")) {
      if (digits.length === 12 && /^[6-9]/.test(digits.slice(2, 3))) return `+${digits}`;
      return null;
    }
    if (digits.startsWith("1")) {
      if (digits.length === 11) return `+${digits}`;
      return null;
    }
    return digits.length >= 10 ? `+${digits}` : null;
  }
  if (digits.length === 10 && /^[6-9]/.test(digits)) return `+91${digits}`;
  if (digits.length === 12 && digits.startsWith("91")) return `+${digits}`;
  if (digits.length === 11 && digits.startsWith("0") && /^[6-9]/.test(digits.slice(1)))
    return `+91${digits.slice(1)}`;
  return null;
}

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.15 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.45, ease: "easeOut" } },
};

const chartTooltipStyle = {
  backgroundColor: "#18181b",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 8,
  fontSize: 12,
};

export default function Dashboard() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string>("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [calling, setCalling] = useState(false);
  const [callResult, setCallResult] = useState<{ success: boolean; message: string } | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("dial");
  const [splash, setSplash] = useState(true);
  const [healthStatus, setHealthStatus] = useState<"ok" | "error" | "checking">("checking");
  const [healthInfo, setHealthInfo] = useState<HealthInfo | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [diagLoading, setDiagLoading] = useState(false);
  const [diagResults, setDiagResults] = useState<Record<string, unknown> | null>(null);
  const [selectedCall, setSelectedCall] = useState<Call | null>(null);
  const [callTurns, setCallTurns] = useState<CallTurn[]>([]);
  const [turnsLoading, setTurnsLoading] = useState(false);

  const fetchAgents = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/v1/agents`);
      if (!res.ok) {
        setFetchError(`Agents API error (${res.status})`);
        return;
      }
      const data = await res.json();
      const list: Agent[] = data.agents || [];
      setAgents(list);
      if (list.length > 0) setSelectedAgent((prev) => prev || list[0].id);
    } catch (e: unknown) {
      setFetchError(e instanceof Error ? e.message : "Failed to load agents");
    }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/v1/dashboard/stats`);
      if (!res.ok) {
        setFetchError(`Stats API error (${res.status})`);
        return;
      }
      const data = await res.json();
      setStats(data);
      if (data._warning) {
        setFetchError(
          data._warning.includes("relation") || data._warning.includes("Stats unavailable")
            ? "CRM tables not set up — calls still work. Run init_db or use Docker Postgres for history."
            : data._warning
        );
      } else {
        setFetchError((prev) => (prev?.includes("Agents API") ? prev : null));
      }
    } catch (e: unknown) {
      setFetchError(e instanceof Error ? e.message : "Failed to load stats");
    }
  }, []);

  const checkHealth = useCallback(async () => {
    setHealthStatus("checking");
    try {
      const res = await fetch(`${API}/health`);
      if (!res.ok) {
        setHealthStatus("error");
        setHealthInfo(null);
        return;
      }
      const data: HealthInfo = await res.json();
      setHealthInfo(data);
      setHealthStatus(data.status === "ok" ? "ok" : "error");
    } catch {
      setHealthStatus("error");
      setHealthInfo(null);
    }
  }, []);

  const syncAll = () => {
    void checkHealth();
    void fetchAgents();
    void fetchStats();
  };

  const runDiagnostics = async () => {
    setDiagLoading(true);
    setDiagResults(null);
    try {
      const [providers, llm, smoke, overview] = await Promise.all([
        fetch(`${API}/api/v1/debug/providers`).then((r) => r.json()),
        fetch(`${API}/api/v1/debug/llm-test`).then((r) => r.json()),
        fetch(`${API}/api/v1/debug/smoke-test`).then((r) => r.json()),
        fetch(`${API}/api/v1/analytics/overview`).then((r) => r.json()),
      ]);
      setDiagResults({ providers, llm, smoke, overview });
    } catch (e: unknown) {
      setDiagResults({ error: e instanceof Error ? e.message : "Diagnostics failed" });
    } finally {
      setDiagLoading(false);
    }
  };

  const loadCallTurns = async (call: Call) => {
    setSelectedCall(call);
    setTurnsLoading(true);
    setCallTurns([]);
    try {
      const res = await fetch(`${API}/api/v1/calls/${call.id}/turns`);
      const data = await res.json();
      if (res.ok) {
        setCallTurns((data.turns || []) as CallTurn[]);
      }
    } finally {
      setTurnsLoading(false);
    }
  };

  useEffect(() => {
    const boot = async () => {
      await Promise.all([checkHealth(), fetchAgents(), fetchStats()]);
      setTimeout(() => setSplash(false), 900);
    };
    void boot();
    const statsInterval = setInterval(fetchStats, 15000);
    const healthInterval = setInterval(checkHealth, 30000);
    return () => {
      clearInterval(statsInterval);
      clearInterval(healthInterval);
    };
  }, [checkHealth, fetchAgents, fetchStats]);

  const initiateCall = async () => {
    const normalizedPhone = previewE164(phoneNumber);
    if (!phoneNumber.trim()) {
      setCallResult({ success: false, message: "Enter a phone number first." });
      return;
    }
    if (!normalizedPhone) {
      setCallResult({
        success: false,
        message:
          "Invalid number format. For India use a valid 10-digit mobile or +91XXXXXXXXXX.",
      });
      return;
    }
    setCalling(true);
    setCallResult(null);
    try {
      const res = await fetch(`${API}/api/v1/calls/initiate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phone_number: normalizedPhone,
          agent_id: selectedAgent || undefined,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setCallResult({
          success: true,
          message: `Call initiated to ${data.to || previewE164(phoneNumber) || phoneNumber}! SID: ${data.call_sid}`,
        });
        setTimeout(fetchStats, 3000);
      } else {
        setCallResult({
          success: false,
          message: formatApiError(data.detail) || "Failed to initiate call.",
        });
      }
    } catch (e: unknown) {
      setCallResult({
        success: false,
        message: `Network error: ${e instanceof Error ? e.message : "unknown"}`,
      });
    } finally {
      setCalling(false);
    }
  };

  const intentChartData = stats
    ? Object.entries(stats.intent_breakdown).map(([name, value]) => ({
        name: name.replace(/_/g, " "),
        value,
        color: intentColors[name] || "#6b7280",
      }))
    : [];

  const latencyChartData =
    stats?.latency?.recent?.map((row, i) => ({
      turn: `T${i + 1}`,
      stt: row.stt_ms ?? row.stt ?? 0,
      llm: row.llm_ms ?? row.llm ?? 0,
      tts: row.tts_ms ?? row.tts ?? 0,
    })) ?? [];

  const isLive = calling || (stats?.active_calls ?? 0) > 0;
  const e164 = previewE164(phoneNumber);

  const providers = [
    { name: "Groq AI", ok: healthInfo?.groq_configured },
    { name: "Twilio", ok: healthInfo?.twilio_configured },
    { name: "PostgreSQL", ok: healthInfo?.db_connected },
    { name: "CRM Tables", ok: healthInfo?.db_crm_ready },
  ];

  return (
    <>
      <AnimatePresence>{splash && <SplashScreen />}</AnimatePresence>

      <motion.div
        className="min-h-screen selection:bg-indigo-500/30"
        initial={{ opacity: 0 }}
        animate={{ opacity: splash ? 0 : 1 }}
        transition={{ duration: 0.5 }}
      >
        <motion.div
          className="bg-aurora"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 1.2 }}
        >
          <motion.div
            className="aurora-blur -left-20 -top-20 bg-indigo-500/10"
            animate={{ x: [0, 30, 0], y: [0, 20, 0] }}
            transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }}
          />
          <motion.div
            className="aurora-blur -right-40 top-1/2 bg-purple-500/5"
            animate={{ x: [0, -25, 0], y: [0, -15, 0] }}
            transition={{ duration: 22, repeat: Infinity, ease: "easeInOut" }}
          />
          <motion.div
            className="aurora-blur -bottom-20 left-1/3 bg-cyan-500/5"
            animate={{ x: [0, 20, 0], y: [0, -25, 0] }}
            transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
          />
        </motion.div>

        <motion.header
          initial={{ y: -64, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.55, ease: "circOut" }}
          className="fixed top-0 z-50 flex h-16 w-full items-center justify-between border-b border-white/10 bg-black/40 px-4 backdrop-blur-md sm:px-6"
        >
          <div className="flex items-center gap-3">
            <motion.div
              className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 shadow-lg shadow-indigo-500/20"
              whileHover={{ scale: 1.05, rotate: 3 }}
              whileTap={{ scale: 0.98 }}
            >
              <Mic className="h-6 w-6 text-white" />
            </motion.div>
            <motion.div initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 }}>
              <h1 className="text-lg font-bold leading-none tracking-tight text-white">AI Calling Agent</h1>
              <p className="mt-1 text-[10px] font-bold uppercase tracking-widest text-indigo-400">
                Voice AI Platform
              </p>
            </motion.div>
          </div>

          <div className="flex items-center gap-2 sm:gap-4">
            <div className="hidden items-center gap-3 glass-pill md:flex">
              <div className="flex items-center gap-1.5 border-r border-white/10 pr-3">
                <motion.div
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    healthStatus === "ok" ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]" : "bg-rose-400"
                  )}
                  animate={healthStatus === "ok" ? { scale: [1, 1.2, 1] } : {}}
                  transition={{ duration: 2, repeat: Infinity }}
                />
                <span
                  className={cn(
                    "text-[10px] font-bold uppercase",
                    healthStatus === "ok" ? "text-emerald-400" : "text-rose-400"
                  )}
                >
                  {healthStatus === "checking" ? "Syncing" : healthStatus === "ok" ? "Live" : "Offline"}
                </span>
              </div>
              <span className="flex items-center gap-1 text-[10px] font-bold uppercase text-zinc-400">
                Groq{" "}
                <ShieldCheck
                  className={cn("h-3 w-3", healthInfo?.groq_configured ? "text-emerald-500" : "text-zinc-600")}
                />
              </span>
              <span className="flex items-center gap-1 text-[10px] font-bold uppercase text-zinc-400">
                CRM{" "}
                <ShieldCheck
                  className={cn("h-3 w-3", healthInfo?.db_crm_ready ? "text-emerald-500" : "text-amber-500")}
                />
              </span>
              <span className="flex items-center gap-1 text-[10px] font-bold uppercase text-zinc-400">
                Twilio{" "}
                <ShieldCheck
                  className={cn("h-3 w-3", healthInfo?.twilio_configured ? "text-emerald-500" : "text-zinc-600")}
                />
              </span>
            </div>
            <motion.button
              type="button"
              onClick={syncAll}
              className="p-2 text-zinc-400 transition-colors hover:text-white"
              whileHover={{ rotate: 180 }}
              transition={{ duration: 0.4 }}
            >
              <RefreshCcw className={cn("h-4 w-4", healthStatus === "checking" && "animate-spin")} />
            </motion.button>
          </div>
        </motion.header>

        <motion.main
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="mx-auto max-w-7xl space-y-8 px-4 pb-16 pt-24 sm:px-6"
        >
          {fetchError && (
            <motion.div
              variants={itemVariants}
              className="flex items-start gap-3 rounded-xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-200"
            >
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
              <span>{fetchError}</span>
            </motion.div>
          )}

          <motion.section variants={itemVariants} className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              icon={Phone}
              label="Calls Today"
              value={stats?.total_calls_today ?? "—"}
              sublabel="Daily outbound volume"
            />
            <StatCard
              icon={Activity}
              label="Active Now"
              value={stats?.active_calls ?? 0}
              sublabel="Live interactions"
              active={(stats?.active_calls ?? 0) > 0}
            />
            <StatCard
              icon={Clock}
              label="Avg Duration"
              value={stats ? fmtDuration(Math.round(stats.avg_duration_seconds)) : "—"}
              sublabel="Per completed call"
            />
            <StatCard
              icon={Users}
              label="Intent FP Rate"
              value={stats?.intent_false_positive_rate_percent != null ? `${stats.intent_false_positive_rate_percent}%` : "—"}
              sublabel="Estimated misclassification"
            />
          </motion.section>

          <motion.nav
            variants={itemVariants}
            className="no-scrollbar flex overflow-x-auto border-b border-white/10"
          >
            {TABS.map((tab) => (
              <TabButton
                key={tab.id}
                id={tab.id}
                label={tab.label}
                icon={tab.icon}
                active={activeTab === tab.id}
                onClick={(id) => setActiveTab(id as TabId)}
              />
            ))}
          </motion.nav>

          <motion.div variants={itemVariants} className="relative min-h-[480px]">
            <AnimatePresence mode="wait">
              <motion.div
                key={activeTab}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -12 }}
                transition={{ duration: 0.28, ease: "easeOut" }}
              >
                {activeTab === "dial" && (
                  <div className="mx-auto flex max-w-2xl flex-col items-center space-y-8 py-6">
                    <motion.div
                      initial={{ scale: 0.9, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={{ type: "spring", stiffness: 200, damping: 20 }}
                    >
                      <VoiceOrb active={isLive} size="lg" />
                    </motion.div>
                    <p className="max-w-md text-center text-sm text-zinc-500">
                      Start an outbound AI voice call with real-time speech, intent tracking, and bilingual EN/HI
                      support.
                    </p>

                    <div className="glass-panel relative w-full space-y-8 overflow-hidden p-8">
                      <Phone className="absolute right-4 top-4 h-24 w-24 opacity-[0.06]" />
                      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}>
                        <h2 className="text-2xl font-bold text-white">Initiate Call</h2>
                        <p className="text-sm text-zinc-400">Select an agent and enter the customer number.</p>
                      </motion.div>

                      <motion.div className="space-y-4" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                        <div className="space-y-2">
                          <label className="text-xs font-bold uppercase tracking-widest text-zinc-500">
                            Phone Number
                          </label>
                          <motion.div className="relative" whileFocus={{ scale: 1.01 }}>
                            <input
                              type="tel"
                              value={phoneNumber}
                              onChange={(e) => setPhoneNumber(e.target.value)}
                              onKeyDown={(e) => e.key === "Enter" && initiateCall()}
                              placeholder="+91 00000 00000"
                              className="glass-input pr-12"
                            />
                            <Globe className="absolute right-4 top-1/2 h-5 w-5 -translate-y-1/2 text-zinc-600" />
                          </motion.div>
                          <p className="font-mono text-[10px] text-zinc-500">
                            E.164 preview:{" "}
                            <span className="text-indigo-400">{e164 || "+91…"}</span>
                          </p>
                        </div>

                        <div className="flex gap-3 rounded-xl border border-amber-500/20 bg-amber-500/10 p-4">
                          <AlertCircle className="h-5 w-5 shrink-0 text-amber-500" />
                          <motion.div
                            className="space-y-1"
                            animate={{ opacity: [0.85, 1, 0.85] }}
                            transition={{ duration: 3, repeat: Infinity }}
                          >
                            <p className="text-xs font-bold uppercase tracking-wide text-amber-500">
                              Twilio trial notice
                            </p>
                            <p className="text-[11px] text-amber-500/80">
                              Only verified numbers can receive calls in trial mode. 10-digit mobiles auto-format as
                              +91.
                            </p>
                          </motion.div>
                        </div>

                        <motion.div className="space-y-3" layout>
                          <label className="text-xs font-bold uppercase tracking-widest text-zinc-500">
                            Select Agent Profile
                          </label>
                          {agents.length === 0 ? (
                            <p className="text-sm text-zinc-500">No agents loaded. Check API and database.</p>
                          ) : (
                            <motion.div className="grid grid-cols-1 gap-3 md:grid-cols-2" layout>
                              {agents.map((agent) => (
                                <motion.button
                                  key={agent.id}
                                  type="button"
                                  layout
                                  onClick={() => setSelectedAgent(agent.id)}
                                  whileHover={{ scale: 1.02 }}
                                  whileTap={{ scale: 0.98 }}
                                  className={cn(
                                    "glass-panel flex items-center gap-3 p-4 text-left transition-colors",
                                    selectedAgent === agent.id && "border-indigo-500/50 ring-1 ring-indigo-500/30"
                                  )}
                                >
                                  <div
                                    className={cn(
                                      "flex h-10 w-10 items-center justify-center rounded-full font-bold transition-all",
                                      selectedAgent === agent.id
                                        ? "bg-indigo-500 text-white"
                                        : "bg-indigo-500/20 text-indigo-400"
                                    )}
                                  >
                                    {agent.name.charAt(0)}
                                  </div>
                                  <motion.div className="min-w-0 grow">
                                    <span className="block text-sm font-bold text-white">{agent.name}</span>
                                    <span className="block truncate text-[10px] uppercase tracking-wide text-zinc-500">
                                      {agent.description || agent.language_mode}
                                    </span>
                                  </motion.div>
                                  <span className="badge-pill bg-indigo-500/20 text-indigo-400">
                                    {agent.language_mode}
                                  </span>
                                </motion.button>
                              ))}
                            </motion.div>
                          )}
                        </motion.div>

                        <motion.button
                          type="button"
                          onClick={initiateCall}
                          disabled={calling || !phoneNumber.trim()}
                          whileHover={!calling && phoneNumber.trim() ? { scale: 1.02 } : {}}
                          whileTap={!calling && phoneNumber.trim() ? { scale: 0.98 } : {}}
                          className={cn(
                            "flex w-full items-center justify-center gap-3 rounded-xl py-4 font-bold transition-all",
                            calling || !phoneNumber.trim()
                              ? "cursor-not-allowed bg-zinc-800 text-zinc-500"
                              : "bg-indigo-600 text-white shadow-lg shadow-indigo-500/30 hover:bg-indigo-500"
                          )}
                        >
                          {calling ? (
                            <>
                              <Loader2 className="h-5 w-5 animate-spin" />
                              Connecting to Twilio…
                            </>
                          ) : (
                            <>
                              <Phone className="h-5 w-5" />
                              Call Now
                            </>
                          )}
                        </motion.button>

                        <AnimatePresence>
                          {callResult && (
                            <motion.div
                              initial={{ opacity: 0, height: 0 }}
                              animate={{ opacity: 1, height: "auto" }}
                              exit={{ opacity: 0, height: 0 }}
                              className={cn(
                                "flex items-start gap-3 rounded-xl border p-4",
                                callResult.success
                                  ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
                                  : "border-rose-500/20 bg-rose-500/10 text-rose-400"
                              )}
                            >
                              {callResult.success ? (
                                <CheckCircle className="mt-0.5 h-4 w-4 shrink-0" />
                              ) : (
                                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                              )}
                              <span className="text-sm">{callResult.message}</span>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </motion.div>
                    </div>
                  </div>
                )}

                {activeTab === "calls" && (
                  <div className="space-y-6">
                    <div className="flex flex-wrap items-center justify-between gap-4">
                      <div>
                        <h2 className="text-2xl font-bold text-white">Call Log</h2>
                        <p className="text-sm text-zinc-400">Recent interactions and AI-detected intents.</p>
                      </div>
                      <button
                        type="button"
                        onClick={fetchStats}
                        className="flex items-center gap-2 glass-pill text-sm font-medium transition-all hover:bg-white/10"
                      >
                        <RefreshCcw className="h-4 w-4" />
                        Sync Logs
                      </button>
                    </div>
                    <div className="glass-panel overflow-hidden">
                      <div className="overflow-x-auto">
                        <table className="w-full text-left">
                          <thead className="bg-white/5 text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-500">
                            <tr>
                              <th className="px-6 py-4">Customer</th>
                              <th className="px-6 py-4">Status</th>
                              <th className="px-6 py-4">Intent</th>
                              <th className="px-6 py-4">Action</th>
                              <th className="px-6 py-4">Duration</th>
                              <th className="px-6 py-4">Sentiment</th>
                              <th className="px-6 py-4">Lang</th>
                              <th className="px-6 py-4">Time</th>
                              <th className="px-6 py-4">Recording</th>
                              <th className="px-6 py-4">Transcript</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-white/5">
                            {(stats?.recent_calls || []).length === 0 ? (
                              <tr>
                                <td colSpan={10} className="px-6 py-12 text-center text-zinc-600">
                                  No calls yet. Use Dial to place your first call.
                                </td>
                              </tr>
                            ) : (
                              stats?.recent_calls.map((call) => (
                                <motion.tr
                                  key={call.id}
                                  className="cursor-pointer transition-colors hover:bg-white/5"
                                  whileHover={{ x: 4 }}
                                >
                                  <td className="px-6 py-4">
                                    <span className="font-mono text-sm text-zinc-100">{call.phone}</span>
                                    {call.call_sid && (
                                      <span className="mt-0.5 block text-[10px] font-bold uppercase text-zinc-600">
                                        SID: {call.call_sid.slice(0, 12)}…
                                      </span>
                                    )}
                                  </td>
                                  <td className="px-6 py-4">
                                    <span
                                      className={cn(
                                        "badge-pill flex w-fit items-center gap-1",
                                        call.status === "completed" && "bg-emerald-500/10 text-emerald-400",
                                        call.status === "in-progress" && "animate-pulse bg-indigo-500/10 text-indigo-400",
                                        call.status !== "completed" &&
                                          call.status !== "in-progress" &&
                                          "bg-rose-500/10 text-rose-400"
                                      )}
                                    >
                                      {call.status}
                                    </span>
                                  </td>
                                  <td className="px-6 py-4">
                                    {call.intent && (
                                      <span
                                        className="rounded border px-2 py-1 text-[10px] font-bold uppercase"
                                        style={{
                                          borderColor: (intentColors[call.intent] || "#71717a") + "40",
                                          color: intentColors[call.intent] || "#a1a1aa",
                                          backgroundColor: (intentColors[call.intent] || "#71717a") + "15",
                                        }}
                                      >
                                        {call.intent.replace(/_/g, " ")}
                                      </span>
                                    )}
                                  </td>
                                  <td className="px-6 py-4 text-xs text-zinc-300">
                                    {call.follow_up_action?.replace(/_/g, " ") || "—"}
                                  </td>
                                  <td className="px-6 py-4 font-mono text-sm text-zinc-400">
                                    {fmtDuration(call.duration_s)}
                                  </td>
                                  <td className="px-6 py-4 text-xs text-zinc-300">
                                    {call.sentiment_score != null ? call.sentiment_score.toFixed(2) : "—"}
                                  </td>
                                  <td className="px-6 py-4 text-xs font-bold text-zinc-500">
                                    {call.language === "hi" ? "HI" : "EN"}
                                  </td>
                                  <td className="px-6 py-4 text-xs text-zinc-400">
                                    {call.created_at ? new Date(call.created_at).toLocaleString() : "—"}
                                  </td>
                                  <td className="px-6 py-4">
                                    {call.recording_url ? (
                                      <audio controls preload="none" src={call.recording_url} className="h-8 w-44" />
                                    ) : (
                                      <span className="text-xs text-zinc-600">—</span>
                                    )}
                                  </td>
                                  <td className="px-6 py-4">
                                    <button
                                      type="button"
                                      onClick={() => loadCallTurns(call)}
                                      className="rounded-md border border-white/10 bg-white/5 px-2 py-1 text-[10px] font-bold uppercase text-zinc-300 hover:bg-white/10"
                                    >
                                      View
                                    </button>
                                  </td>
                                </motion.tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                    {selectedCall && (
                      <div className="glass-panel p-4">
                        <div className="mb-3 flex items-center justify-between">
                          <h3 className="text-sm font-bold text-white">
                            Transcript · {selectedCall.phone} · {selectedCall.call_sid?.slice(0, 12)}...
                          </h3>
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedCall(null);
                              setCallTurns([]);
                            }}
                            className="text-xs text-zinc-400 hover:text-white"
                          >
                            Close
                          </button>
                        </div>
                        {turnsLoading ? (
                          <p className="text-sm text-zinc-500">Loading transcript...</p>
                        ) : callTurns.length === 0 ? (
                          <p className="text-sm text-zinc-500">No transcript turns found for this call.</p>
                        ) : (
                          <div className="max-h-72 space-y-2 overflow-auto pr-1">
                            {callTurns.map((t) => (
                              <div key={`${t.turn_index}-${t.speaker}`} className="rounded-lg border border-white/10 bg-white/5 p-2">
                                <p className="text-[10px] font-bold uppercase text-zinc-400">
                                  {t.speaker} · {t.intent || "—"} · {t.language || "—"}
                                </p>
                                <p className="text-sm text-zinc-200">{t.transcript}</p>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {activeTab === "analytics" && (
                  <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                    <div className="glass-panel space-y-6 p-6">
                      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <h3 className="text-lg font-bold text-white">Intent Breakdown</h3>
                        <p className="mt-1 text-xs uppercase tracking-widest text-zinc-400">AI classification</p>
                      </motion.div>
                      <div className="h-[250px] w-full">
                        {intentChartData.length === 0 ? (
                          <motion.div
                            className="flex h-full items-center justify-center text-sm text-zinc-600"
                            animate={{ opacity: [0.5, 1, 0.5] }}
                            transition={{ duration: 2, repeat: Infinity }}
                          >
                            No intent data yet
                          </motion.div>
                        ) : (
                          <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                              <Pie
                                data={intentChartData}
                                innerRadius={60}
                                outerRadius={80}
                                paddingAngle={5}
                                dataKey="value"
                              >
                                {intentChartData.map((entry, index) => (
                                  <Cell key={index} fill={entry.color} />
                                ))}
                              </Pie>
                              <Tooltip contentStyle={chartTooltipStyle} />
                            </PieChart>
                          </ResponsiveContainer>
                        )}
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        {intentChartData.map((item) => (
                          <motion.div
                            key={item.name}
                            className="flex items-center gap-2"
                            whileHover={{ x: 4 }}
                          >
                            <motion.div
                              className="h-2 w-2 rounded-full"
                              style={{ backgroundColor: item.color }}
                              animate={{ scale: [1, 1.2, 1] }}
                              transition={{ duration: 2, repeat: Infinity, delay: 0.1 }}
                            />
                            <span className="text-xs capitalize text-zinc-400">{item.name}</span>
                            <span className="ml-auto text-xs font-bold text-white">{item.value}</span>
                          </motion.div>
                        ))}
                      </div>
                    </div>

                    <div className="glass-panel space-y-6 p-6">
                      <div>
                        <h3 className="text-lg font-bold text-white">Processing Latency</h3>
                        <p className="mt-1 text-xs uppercase tracking-widest text-zinc-400">STT · LLM · TTS (ms)</p>
                      </div>
                      <motion.div className="h-[250px] w-full" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        {latencyChartData.length === 0 ? (
                          <div className="flex h-full items-center justify-center text-sm text-zinc-600">
                            Latency samples appear after live calls
                          </div>
                        ) : (
                          <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={latencyChartData}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
                              <XAxis dataKey="turn" stroke="#71717a" fontSize={10} />
                              <YAxis stroke="#71717a" fontSize={10} />
                              <Tooltip contentStyle={chartTooltipStyle} />
                              <Bar dataKey="stt" stackId="a" fill="#6366f1" name="STT" />
                              <Bar dataKey="llm" stackId="a" fill="#4f46e5" name="LLM" />
                              <Bar dataKey="tts" stackId="a" fill="#3730a3" radius={[4, 4, 0, 0]} name="TTS" />
                            </BarChart>
                          </ResponsiveContainer>
                        )}
                      </motion.div>
                      {stats?.latency && (
                        <div className="flex justify-between border-t border-white/5 pt-4 text-[10px] font-bold uppercase text-zinc-500">
                          <span>Avg turn: {Math.round(stats.latency.avg_total_ms)}ms</span>
                          <span className="text-emerald-500">P95: {Math.round(stats.latency.p95_total_ms)}ms</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {activeTab === "agents" && (
                  <motion.div className="space-y-6" layout>
                    <div className="flex flex-wrap items-center justify-between gap-4">
                      <div>
                        <h2 className="text-2xl font-bold text-white">Voice Agents</h2>
                        <p className="text-sm text-zinc-400">AI personalities and voice parameters.</p>
                      </div>
                    </div>
                    {agents.length === 0 ? (
                      <div className="glass-panel py-16 text-center text-zinc-600">No agents found.</div>
                    ) : (
                      <motion.div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3" layout>
                        {agents.map((agent, i) => (
                          <motion.div
                            key={agent.id}
                            layout
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: i * 0.06 }}
                            whileHover={{ scale: 1.02 }}
                            className="glass-panel group space-y-6 p-6"
                          >
                            <div className="flex items-start justify-between">
                              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-600 text-xl font-bold text-white shadow-lg shadow-indigo-500/20">
                                {agent.name.charAt(0)}
                              </div>
                              <span className="badge-pill bg-zinc-500/10 text-zinc-400">idle</span>
                            </div>
                            <div>
                              <h4 className="text-lg font-bold uppercase text-white transition-colors group-hover:text-indigo-400">
                                {agent.name}
                              </h4>
                              <p className="mt-1 text-xs font-bold uppercase tracking-widest text-zinc-500">
                                {agent.language_mode}
                              </p>
                            </div>
                            <div className="space-y-4">
                              <div className="flex items-center justify-between border-y border-white/5 py-2 text-xs">
                                <span className="font-bold uppercase tracking-widest text-zinc-500">EN voice</span>
                                <span className="font-medium text-white">{agent.voice_english}</span>
                              </div>
                              <motion.div className="flex items-center justify-between border-b border-white/5 pb-2 text-xs">
                                <span className="font-bold uppercase tracking-widest text-zinc-500">HI voice</span>
                                <span className="font-medium text-white">{agent.voice_hindi}</span>
                              </motion.div>
                            </div>
                            {agent.description && (
                              <p className="text-xs text-zinc-500">{agent.description}</p>
                            )}
                            <div className="flex gap-2">
                              <button
                                type="button"
                                onClick={() => {
                                  setSelectedAgent(agent.id);
                                  setActiveTab("dial");
                                }}
                                className="grow rounded-lg border border-white/10 bg-white/5 py-2 text-[10px] font-bold uppercase transition-all hover:bg-white/10"
                              >
                                Use for call
                              </button>
                              <button
                                type="button"
                                className="rounded-lg border border-white/10 bg-white/5 p-2 transition-all hover:text-indigo-400"
                                aria-label="Agent details"
                              >
                                <Monitor className="h-4 w-4" />
                              </button>
                            </div>
                          </motion.div>
                        ))}
                      </motion.div>
                    )}
                  </motion.div>
                )}

                {activeTab === "system" && (
                  <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                    <div className="space-y-6 lg:col-span-2">
                      <div className="glass-panel space-y-6 p-6">
                        <motion.div
                          className="flex flex-wrap items-center justify-between gap-4"
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                        >
                          <h3 className="text-lg font-bold text-white">System Diagnostics</h3>
                          <motion.button
                            type="button"
                            onClick={runDiagnostics}
                            disabled={diagLoading}
                            whileHover={{ scale: 1.03 }}
                            whileTap={{ scale: 0.97 }}
                            className="rounded-lg bg-indigo-500 px-4 py-2 text-xs font-bold uppercase tracking-widest text-white shadow-md disabled:opacity-50"
                          >
                            {diagLoading ? "Scanning…" : "Run Full Scan"}
                          </motion.button>
                        </motion.div>
                        <div className="space-y-4">
                          <motion.div
                            className="flex items-start gap-4 rounded-xl border border-indigo-500/10 bg-indigo-500/5 p-4"
                            whileHover={{ x: 4 }}
                          >
                            <Cpu className="mt-1 h-5 w-5 text-indigo-400" />
                            <div className="space-y-1">
                              <p className="text-sm font-bold text-white">Groq LLM & STT</p>
                              <p className="text-xs italic text-zinc-400">
                                {healthInfo?.groq_configured
                                  ? "API key configured. Models ready for voice pipeline."
                                  : "Groq not configured — set GROQ_API_KEY on the API."}
                              </p>
                            </div>
                            <span
                              className={cn(
                                "ml-auto text-[10px] font-bold uppercase",
                                healthInfo?.groq_configured ? "text-emerald-400" : "text-rose-400"
                              )}
                            >
                              {healthInfo?.groq_configured ? "Optimal" : "Missing"}
                            </span>
                          </motion.div>
                          <motion.div
                            className="flex items-start gap-4 rounded-xl border border-amber-500/10 bg-amber-500/5 p-4"
                            whileHover={{ x: 4 }}
                          >
                            <Database className="mt-1 h-5 w-5 text-amber-400" />
                            <motion.div className="space-y-1">
                              <p className="text-sm font-bold text-white">CRM & Database</p>
                              <p className="text-xs text-zinc-400">
                                {healthInfo?.db_crm_ready
                                  ? "CRM tables ready for call history and leads."
                                  : healthInfo?.db_connected
                                    ? "Connected — CRM schema may need initialization."
                                    : "Database not connected or disabled."}
                              </p>
                            </motion.div>
                            <span
                              className={cn(
                                "ml-auto text-[10px] font-bold uppercase",
                                healthInfo?.db_crm_ready ? "text-emerald-400" : "text-amber-400"
                              )}
                            >
                              {healthInfo?.db_crm_ready ? "Ready" : "Attention"}
                            </span>
                          </motion.div>
                        </div>
                      </div>
                      <AnimatePresence>
                        {diagResults && (
                          <motion.div
                            initial={{ opacity: 0, y: 12 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0 }}
                            className="glass-panel space-y-4 p-6"
                          >
                            <h3 className="text-sm font-bold uppercase tracking-[0.2em] text-zinc-500">
                              Debug output (JSON)
                            </h3>
                            <pre className="glass-panel max-h-96 overflow-auto bg-black/40 p-4 font-mono text-[11px] text-indigo-300">
                              {JSON.stringify(diagResults, null, 2)}
                            </pre>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                    <div className="space-y-6">
                      <h3 className="px-2 text-xs font-bold uppercase tracking-widest text-zinc-500">
                        Provider Status
                      </h3>
                      <div className="space-y-3">
                        {providers.map((p, i) => (
                          <motion.div
                            key={p.name}
                            initial={{ opacity: 0, x: 12 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: i * 0.05 }}
                            className="glass-panel flex items-center justify-between p-4"
                          >
                            <span className="text-xs font-bold uppercase text-white">{p.name}</span>
                            <div className="flex items-center gap-1.5">
                              <motion.div
                                className={cn("h-1.5 w-1.5 rounded-full", p.ok ? "bg-emerald-400" : "bg-rose-400")}
                                animate={p.ok ? { scale: [1, 1.3, 1] } : {}}
                                transition={{ duration: 2, repeat: Infinity }}
                              />
                              <span
                                className={cn(
                                  "text-[10px] font-bold uppercase tracking-wider",
                                  p.ok ? "text-emerald-400" : "text-rose-400"
                                )}
                              >
                                {p.ok ? "Up" : "Down"}
                              </span>
                            </div>
                          </motion.div>
                        ))}
                      </div>
                      <motion.div
                        className="relative overflow-hidden rounded-2xl bg-indigo-600 p-6"
                        whileHover={{ scale: 1.02 }}
                      >
                        <div className="relative z-10 space-y-4">
                          <h4 className="font-bold leading-tight text-white">
                            4-layer voice
                            <br />
                            architecture
                          </h4>
                          <p className="text-xs text-indigo-200">
                            Twilio · Groq · Kokoro TTS · CRM pipeline
                          </p>
                        </div>
                        <Phone className="absolute -bottom-6 -right-6 h-32 w-32 -rotate-12 text-indigo-500/30" />
                      </motion.div>
                    </div>
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
          </motion.div>
        </motion.main>

        <motion.footer
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5 }}
          className="flex h-20 items-center justify-center border-t border-white/5 opacity-40"
        >
          <p className="text-[10px] font-bold uppercase tracking-[0.35em] text-zinc-500">
            AI Calling Agent · Groq · Twilio · Kokoro
          </p>
        </motion.footer>
      </motion.div>

      <AnimatePresence>
        {healthStatus === "error" && !splash && (
          <motion.div
            initial={{ opacity: 0, y: 50 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 50 }}
            className="fixed bottom-6 left-1/2 z-[90] flex -translate-x-1/2 items-center gap-4 rounded-xl bg-rose-600 px-6 py-4 text-white shadow-2xl"
          >
            <AlertCircle className="h-6 w-6 shrink-0" />
            <div>
              <p className="text-sm font-bold">Backend offline</p>
              <p className="text-xs opacity-90">Check {API} or Railway deployment.</p>
            </div>
            <button
              type="button"
              onClick={syncAll}
              className="ml-2 rounded-lg px-3 py-1 text-xs font-bold uppercase hover:bg-white/20"
            >
              Retry
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
