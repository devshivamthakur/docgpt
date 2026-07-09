import { Upload, MessageSquareText, Sparkles, ArrowUpRight } from 'lucide-react';

function DashboardPage() {
  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.18),_transparent_40%),linear-gradient(135deg,_#020617,_#0f172a)] text-white">
      <div className="mx-auto flex max-w-7xl flex-col gap-8 px-6 py-10 lg:px-10">
        <header className="flex flex-wrap items-center justify-between rounded-3xl border border-white/10 bg-white/10 px-6 py-5 backdrop-blur">
          <div>
            <p className="text-sm uppercase tracking-[0.35em] text-cyan-300">DocGPT Workspace</p>
            <h1 className="mt-2 text-3xl font-semibold">Your documents, ready for conversation.</h1>
          </div>
          <button className="rounded-full border border-cyan-400/40 bg-cyan-500/10 px-4 py-2 text-sm font-medium text-cyan-200">New project</button>
        </header>

        <section className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-2xl">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl bg-cyan-500/15 p-3 text-cyan-300">
                <Upload className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-xl font-semibold">Upload and process documents</h2>
                <p className="text-sm text-slate-400">Asynchronous parsing, embedding, and retrieval are queued in the background.</p>
              </div>
            </div>
            <div className="mt-6 rounded-2xl border border-dashed border-cyan-400/30 bg-cyan-500/10 p-8 text-center">
              <Sparkles className="mx-auto h-8 w-8 text-cyan-300" />
              <p className="mt-3 text-lg font-medium">Drop PDFs, docs, or markdown into your workspace</p>
              <p className="mt-2 text-sm text-slate-400">Progress and status updates will appear here as the pipeline runs.</p>
            </div>
          </div>

          <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-2xl">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl bg-violet-500/15 p-3 text-violet-300">
                <MessageSquareText className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-xl font-semibold">Ask anything</h2>
                <p className="text-sm text-slate-400">Grounded answers with semantic search and reasoning.</p>
              </div>
            </div>
            <div className="mt-6 space-y-3">
              {['Summarize this onboarding guide', 'What changed in the product roadmap?', 'Show the key risks from the legal brief'].map((question) => (
                <button key={question} className="flex w-full items-center justify-between rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-left text-sm text-slate-300 hover:border-cyan-400/50">
                  <span>{question}</span>
                  <ArrowUpRight className="h-4 w-4" />
                </button>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

export default DashboardPage;
