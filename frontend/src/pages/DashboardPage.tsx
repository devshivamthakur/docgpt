import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Upload,
  FileText,
  LogOut,
  User,
  MessageSquare,
  HardDrive,
  Files,
  CheckCircle2,
  Clock,
  AlertCircle,
  Activity,
  BarChart3,
  ExternalLink,
} from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import {
  useDocumentStore,
  STATUS_LABELS,
  type Document,
} from '../store/documentStore';
import UploadWidget from '../components/UploadWidget';
import DocumentGrid from '../components/DocumentGrid';

// ── Helpers ──────────────────────────────────────────────────────────

function formatSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

// ── StatCard ─────────────────────────────────────────────────────────

function StatCard({
  icon,
  label,
  value,
  sub,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  sub?: string;
  color: string;
}) {
  return (
    <div className="group relative overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60 p-5 transition-all duration-300 hover:border-slate-700 hover:bg-slate-900/80 hover:shadow-lg">
      {/* Hover glow */}
      <div
        className={`pointer-events-none absolute -inset-1 opacity-0 blur-2xl transition duration-500 group-hover:opacity-20 ${color}`}
      />
      <div className="relative flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</p>
          <p className="mt-2 text-2xl font-bold tracking-tight text-white">{value}</p>
          {sub && <p className="mt-0.5 text-xs text-slate-500">{sub}</p>}
        </div>
        <div className={`rounded-xl p-2.5 ${color} bg-opacity-15`}>{icon}</div>
      </div>
    </div>
  );
}

// ── StorageBar ───────────────────────────────────────────────────────

function StorageBar({
  usedBytes,
  quotaBytes,
}: {
  usedBytes: number;
  quotaBytes: number;
}) {
  const percent = quotaBytes > 0 ? (usedBytes / quotaBytes) * 100 : 0;
  const clamped = Math.min(percent, 100);
  const remaining = Math.max(quotaBytes - usedBytes, 0);

  const barColor =
    clamped >= 95
      ? 'from-red-500 to-rose-600'
      : clamped >= 75
        ? 'from-amber-400 to-orange-500'
        : 'from-cyan-400 to-violet-500';

  const barGlow =
    clamped >= 95
      ? 'shadow-red-500/25'
      : clamped >= 75
        ? 'shadow-amber-500/25'
        : 'shadow-cyan-500/25';

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-slate-800 p-2.5 text-slate-400">
            <HardDrive className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm font-medium text-slate-200">Storage Quota</p>
            <p className="text-xs text-slate-500">
              {formatSize(usedBytes)} used · {formatSize(remaining)} remaining
            </p>
          </div>
        </div>
        <div className="text-right">
          <p className={`text-lg font-bold tabular-nums ${clamped >= 95 ? 'text-red-400' : clamped >= 75 ? 'text-amber-400' : 'text-cyan-400'}`}>
            {clamped.toFixed(1)}%
          </p>
          <p className="text-xs text-slate-500">of {formatSize(quotaBytes)}</p>
        </div>
      </div>

      {/* Progress bar */}
      <div className={`relative mt-4 h-3 overflow-hidden rounded-full bg-slate-800 shadow-inner ${barGlow}`}>
        <div
          className={`h-full rounded-full bg-gradient-to-r ${barColor} transition-all duration-1000 ease-out`}
          style={{ width: `${clamped}%` }}
        />
        {/* Animated shimmer */}
        <div
          className="absolute inset-0 h-full rounded-full bg-gradient-to-r from-transparent via-white/10 to-transparent"
          style={{
            width: `${clamped}%`,
            animation: 'shimmer 2s infinite',
            backgroundSize: '200% 100%',
          }}
        />
      </div>

      {/* Segments for visual reference */}
      <div className="mt-2 flex justify-between text-[10px] text-slate-600">
        <span>0%</span>
        <span>25%</span>
        <span>50%</span>
        <span>75%</span>
        <span>100%</span>
      </div>
    </div>
  );
}

// ── RecentActivity ───────────────────────────────────────────────────

function RecentActivity({ documents }: { documents: Document[] }) {
  const recent = useMemo(() => documents.slice(0, 6), [documents]);

  if (recent.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-800 py-10 text-center">
        <Activity className="h-8 w-8 text-slate-700" />
        <p className="mt-3 text-sm text-slate-500">No activity yet</p>
        <p className="text-xs text-slate-600">Upload a document to get started</p>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {recent.map((doc, idx) => {
        const statusIcon = {
          uploading: <Clock className="h-3.5 w-3.5 text-blue-400" />,
          uploaded: <Clock className="h-3.5 w-3.5 text-slate-400" />,
          parsing: <Clock className="h-3.5 w-3.5 text-amber-400" />,
          chunking: <Clock className="h-3.5 w-3.5 text-cyan-400" />,
          embedding: <Clock className="h-3.5 w-3.5 text-violet-400" />,
          indexing: <Clock className="h-3.5 w-3.5 text-indigo-400" />,
          ready: <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />,
          failed: <AlertCircle className="h-3.5 w-3.5 text-red-400" />,
        }[doc.status];

        const isLast = idx === recent.length - 1;

        return (
          <div key={doc.id} className="group flex items-start gap-3 px-1 py-2">
            {/* Timeline line + dot */}
            <div className="flex flex-col items-center">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-800 ring-1 ring-slate-700">
                {statusIcon}
              </div>
              {!isLast && <div className="mt-1 h-5 w-px bg-slate-800" />}
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0 pt-0.5">
              <p className="truncate text-sm font-medium text-slate-200" title={doc.original_filename}>
                {doc.original_filename}
              </p>
              <p className="flex items-center gap-2 text-xs text-slate-500">
                <span>{STATUS_LABELS[doc.status]}</span>
                <span>·</span>
                <span>{formatSize(doc.file_size)}</span>
                <span>·</span>
                <span>{formatDate(doc.created_at)}</span>
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── DashboardPage ────────────────────────────────────────────────────

function DashboardPage() {
  const navigate = useNavigate();
  const { user, logout: storeLogout } = useAuthStore();

  const logout = useCallback(() => {
    storeLogout();
    navigate('/login', { replace: true });
  }, [storeLogout, navigate]);
  const fetchDocuments = useDocumentStore((s) => s.fetchDocuments);
  const fetchStorageUsage = useDocumentStore((s) => s.fetchStorageUsage);
  const documents = useDocumentStore((s) => s.documents) ?? [];
  const total = useDocumentStore((s) => s.total);
  const storageUsage = useDocumentStore((s) => s.storageUsage);
  const reprocessDocument = useDocumentStore((s) => s.reprocessDocument);

  const [selectedDocId, setSelectedDocId] = useState<number | null>(null);

  useEffect(() => {
    fetchDocuments();
    fetchStorageUsage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleUploadComplete = useCallback(
    (docId?: number) => {
      fetchDocuments();
      fetchStorageUsage();
      if (docId) setSelectedDocId(docId);
    },
    [fetchDocuments, fetchStorageUsage],
  );

  // ── Computed stats ──────────────────────────────────────────────
  const stats = useMemo(() => {
    const ready = documents.filter((d) => d.status === 'ready').length;
    const processing = documents.filter(
      (d) => !['ready', 'failed'].includes(d.status),
    ).length;
    const failed = documents.filter((d) => d.status === 'failed').length;
    const totalSize = documents.reduce((acc, d) => acc + d.file_size, 0);
    return { ready, processing, failed, totalSize };
  }, [documents]);

  const recentDocuments = useMemo(() => {
    return [...documents].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );
  }, [documents]);

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.18),_transparent_40%),linear-gradient(135deg,_#020617,_#0f172a)] text-white">
      {/* ── Subtle grid overlay ── */}
      <div
        className="pointer-events-none fixed inset-0 opacity-[0.015]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.1) 1px, transparent 1px)',
          backgroundSize: '60px 60px',
        }}
      />

      <div className="relative mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6 sm:py-10 lg:px-10 lg:gap-8">
        {/* ══════════════════════════════════════════════════════════
            HEADER
           ══════════════════════════════════════════════════════════ */}
        <header className="flex flex-wrap items-center justify-between rounded-3xl border border-white/10 bg-white/10 px-5 py-4 backdrop-blur-xl sm:px-6 sm:py-5">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-cyan-300 sm:text-sm">
              DocGPT Workspace
            </p>
            <h1 className="mt-1 text-2xl font-semibold sm:mt-2 sm:text-3xl">
              Your documents, ready for conversation.
            </h1>
          </div>
          <div className="mt-3 flex w-full items-center gap-3 sm:mt-0 sm:w-auto">
            {user && (
              <span className="hidden items-center gap-2 text-sm text-slate-400 md:flex">
                <User className="h-4 w-4" />
                {user.full_name}
              </span>
            )}
            <button
              onClick={() => navigate('/chat')}
              className="flex flex-1 items-center justify-center gap-2 rounded-full bg-gradient-to-r from-cyan-500 to-violet-500 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-cyan-500/20 transition hover:opacity-90 sm:flex-initial"
            >
              <MessageSquare className="h-4 w-4" />
              Go to Chat
            </button>
            <button
              onClick={logout}
              className="flex flex-1 items-center justify-center gap-2 rounded-full border border-red-400/20 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-300 transition hover:bg-red-500/20 sm:flex-initial"
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </button>
          </div>
        </header>

        {/* ══════════════════════════════════════════════════════════
            STORAGE + STATS ROW
           ══════════════════════════════════════════════════════════ */}
        <div className="grid gap-6 lg:grid-cols-3">
          {/* ── Storage bar (spans 2 cols) ── */}
          <div className="lg:col-span-2">
            {storageUsage ? (
              <StorageBar
                usedBytes={storageUsage.total_used_bytes}
                quotaBytes={storageUsage.quota_bytes}
              />
            ) : (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
                <div className="flex items-center gap-3">
                  <div className="rounded-xl bg-slate-800 p-2.5 text-slate-400">
                    <HardDrive className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-200">Storage Quota</p>
                    <p className="text-xs text-slate-500">Loading storage info…</p>
                  </div>
                </div>
                <div className="mt-4 h-3 animate-pulse rounded-full bg-slate-800" />
              </div>
            )}

            {/* Mini stats row */}
            <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-5">
              <StatCard
                icon={<Files className="h-4 w-4" />}
                label="Total Documents"
                value={total}
                color="text-sky-400"
              />
              <StatCard
                icon={<CheckCircle2 className="h-4 w-4" />}
                label="Ready"
                value={stats.ready}
                sub={total > 0 ? `${Math.round((stats.ready / total) * 100)}% of all` : '—'}
                color="text-emerald-400"
              />
              <StatCard
                icon={<Clock className="h-4 w-4" />}
                label="Processing"
                value={stats.processing}
                color="text-amber-400"
              />
              <StatCard
                icon={<AlertCircle className="h-4 w-4" />}
                label="Failed"
                value={stats.failed}
                sub={stats.failed > 0 ? 'Needs attention' : ''}
                color="text-red-400"
              />
              <StatCard
                icon={<BarChart3 className="h-4 w-4" />}
                label="Total Size"
                value={formatSize(stats.totalSize)}
                color="text-violet-400"
              />
            </div>
          </div>

          {/* ── Recent activity ── */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
            <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
              <Activity className="h-4 w-4 text-cyan-400" />
              <h3 className="text-sm font-semibold text-slate-200">Recent Activity</h3>
            </div>
            <div className="mt-3 max-h-[320px] overflow-y-auto scrollbar-thin scrollbar-track-slate-900 scrollbar-thumb-slate-700">
              <RecentActivity documents={recentDocuments} />
            </div>
          </div>
        </div>

        {/* ══════════════════════════════════════════════════════════
            UPLOAD SECTION
           ══════════════════════════════════════════════════════════ */}
        <section className="rounded-3xl border border-slate-800 bg-slate-900/80 p-5 shadow-2xl sm:p-6">
          <div className="flex flex-wrap items-center gap-3">
            <div className="rounded-2xl bg-cyan-500/15 p-3 text-cyan-300">
              <Upload className="h-5 w-5" />
            </div>
            <div className="flex-1">
              <h2 className="text-xl font-semibold">Upload and process documents</h2>
              <p className="text-sm text-slate-400">
                Drag & drop or browse — parsing, chunking, and embedding run asynchronously.
              </p>
            </div>
            {storageUsage && (
              <div className="flex items-center gap-2 rounded-full border border-slate-700/50 bg-slate-800/50 px-3 py-1.5 text-xs text-slate-400">
                <HardDrive className="h-3.5 w-3.5" />
                <span>
                  {formatSize(storageUsage.total_used_bytes)} / {formatSize(storageUsage.quota_bytes)}
                </span>
              </div>
            )}
          </div>
          <div className="mt-5">
            <UploadWidget
              onUploadComplete={handleUploadComplete}
              storageUsed={storageUsage?.total_used_bytes ?? 0}
              storageQuota={storageUsage?.quota_bytes ?? 1_073_741_824}
            />
          </div>
        </section>

        {/* ══════════════════════════════════════════════════════════
            DOCUMENTS SECTION
           ══════════════════════════════════════════════════════════ */}
        <section className="rounded-3xl border border-slate-800 bg-slate-900/80 p-5 shadow-2xl sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl bg-violet-500/15 p-3 text-violet-300">
                <FileText className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-xl font-semibold">Your documents</h2>
                <p className="text-sm text-slate-400">
                  {total > 0
                    ? `${total} document${total !== 1 ? 's' : ''} · ${stats.ready} ready to chat`
                    : 'Click a document to view its processing timeline.'}
                </p>
              </div>
            </div>

            {/* View all → dedicated page */}
            {total > 3 && (
              <button
                onClick={() => navigate('/documents')}
                className="flex items-center gap-1.5 rounded-full border border-slate-700/50 bg-slate-800/50 px-3.5 py-1.5 text-xs font-medium text-slate-300 transition hover:border-slate-600 hover:bg-slate-700/50"
              >
                <ExternalLink className="h-3 w-3" />
                View all
              </button>
            )}
          </div>

          {/* Retry-all banner for failed documents */}
          {stats.failed > 0 && (
            <div className="mt-4 flex items-center gap-3 rounded-xl border border-red-500/20 bg-red-500/5 px-4 py-3">
              <AlertCircle className="h-5 w-5 shrink-0 text-red-400" />
              <p className="flex-1 text-sm text-red-300">
                <span className="font-medium">{stats.failed}</span> document{stats.failed !== 1 ? 's' : ''} failed
                {stats.failed > 1 && (
                  <span>
                    {' · '}
                    <button
                      onClick={async () => {
                        const failedDocs = documents.filter((d) => d.status === 'failed');
                        await Promise.allSettled(failedDocs.map((d) => reprocessDocument(d.id)));
                      }}
                      className="underline underline-offset-2 transition hover:text-red-200"
                    >
                      Retry all
                    </button>
                  </span>
                )}
              </p>
              <span className="text-xs text-red-400/60">Click a card to retry individually</span>
            </div>
          )}

          <div className="mt-5">
            <DocumentGrid
              selectedDocId={selectedDocId}
              onSelectDoc={setSelectedDocId}
              compact
            />
          </div>
        </section>

        {/* ══════════════════════════════════════════════════════════
            FOOTER
           ══════════════════════════════════════════════════════════ */}
        <footer className="text-center text-xs text-slate-600">
          DocGPT · All your documents are processed locally · {total} document{total !== 1 ? 's' : ''} indexed
        </footer>
      </div>

      {/* ── Global styles for shimmer animation ── */}
      <style>{`
        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
        .scrollbar-thin::-webkit-scrollbar {
          width: 4px;
        }
        .scrollbar-thin::-webkit-scrollbar-track {
          background: transparent;
        }
        .scrollbar-thin::-webkit-scrollbar-thumb {
          background: rgb(51 65 85);
          border-radius: 9999px;
        }
        .scrollbar-thin::-webkit-scrollbar-thumb:hover {
          background: rgb(71 85 105);
        }
      `}</style>
    </div>
  );
}

export default DashboardPage;
