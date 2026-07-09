import { useEffect } from 'react';
import { Upload, FileText, LogOut, User } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { useDocumentStore } from '../store/documentStore';
import UploadWidget from '../components/UploadWidget';
import DocumentGrid from '../components/DocumentGrid';

function DashboardPage() {
  const { user, logout } = useAuthStore();
  const fetchDocuments = useDocumentStore((s) => s.fetchDocuments);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.18),_transparent_40%),linear-gradient(135deg,_#020617,_#0f172a)] text-white">
      <div className="mx-auto flex max-w-7xl flex-col gap-8 px-6 py-10 lg:px-10">
        {/* ── Header ──────────────────────────────────────────── */}
        <header className="flex flex-wrap items-center justify-between rounded-3xl border border-white/10 bg-white/10 px-6 py-5 backdrop-blur">
          <div>
            <p className="text-sm uppercase tracking-[0.35em] text-cyan-300">DocGPT Workspace</p>
            <h1 className="mt-2 text-3xl font-semibold">Your documents, ready for conversation.</h1>
          </div>
          <div className="flex items-center gap-4">
            {user && (
              <span className="flex items-center gap-2 text-sm text-slate-400">
                <User className="h-4 w-4" />
                {user.full_name}
              </span>
            )}
            <button
              onClick={logout}
              className="flex items-center gap-2 rounded-full border border-red-400/20 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-300 transition hover:bg-red-500/20"
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </button>
          </div>
        </header>

        {/* ── Upload section ──────────────────────────────────── */}
        <section className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-2xl">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-cyan-500/15 p-3 text-cyan-300">
              <Upload className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-xl font-semibold">Upload and process documents</h2>
              <p className="text-sm text-slate-400">
                Drag & drop or browse — parsing, chunking, and embedding run asynchronously in the background.
              </p>
            </div>
          </div>
          <div className="mt-5">
            <UploadWidget onUploadComplete={fetchDocuments} />
          </div>
        </section>

        {/* ── Document grid ───────────────────────────────────── */}
        <section className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-2xl">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-violet-500/15 p-3 text-violet-300">
              <FileText className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-xl font-semibold">Your documents</h2>
              <p className="text-sm text-slate-400">
                Click a document to view its processing timeline.
              </p>
            </div>
          </div>
          <div className="mt-5">
            <DocumentGrid />
          </div>
        </section>
      </div>
    </div>
  );
}

export default DashboardPage;
