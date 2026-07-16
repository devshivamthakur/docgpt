import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Menu,
  Sparkles,
  LogOut,
  User,
  ChevronLeft,
  MessageSquare,
  AlertCircle,
} from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { useConversationStore } from '../store/conversationStore';
import { useChatStream } from '../hooks/useChatStream';
import ChatMessage from '../components/ChatMessage';
import ChatInput from '../components/ChatInput';
import SourcePanel from '../components/SourcePanel';
import ConversationSidebar from '../components/ConversationSidebar';
import TypingIndicator from '../components/TypingIndicator';

function ChatPage() {
  const { id: routeId } = useParams<{ id: string }>();
  const { user, logout: storeLogout } = useAuthStore();
  const navigate = useNavigate();

  const logout = useCallback(() => {
    storeLogout();
    navigate('/login', { replace: true });
  }, [storeLogout, navigate]);
  const { startStream, abortStream } = useChatStream();

  const activeConversation = useConversationStore((s) => s.activeConversation);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);
  const isStreaming = useConversationStore((s) => s.isStreaming);
  const streamContent = useConversationStore((s) => s.streamContent);
  const streamSources = useConversationStore((s) => s.streamSources);
  const streamError = useConversationStore((s) => s.streamError);
  const selectConversation = useConversationStore((s) => s.selectConversation);
  const createConversation = useConversationStore((s) => s.createConversation);
  const fetchConversations = useConversationStore((s) => s.fetchConversations);

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sourcesOpen, setSourcesOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // ── Refs for frequently-changing values used in callbacks ─────────
  const activeConversationIdRef = useRef(activeConversationId);
  activeConversationIdRef.current = activeConversationId;

  const sidebarOpenRef = useRef(sidebarOpen);
  sidebarOpenRef.current = sidebarOpen;

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeConversation?.messages, streamContent]);

  // Load conversations on mount
  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  // Load conversation from route ID
  useEffect(() => {
    if (routeId) {
      selectConversation(routeId);
    }
  }, [routeId, selectConversation]);

  // Check if we should show the welcome screen
  const hasMessages = activeConversation && activeConversation.messages.length > 0;
  const showWelcome = !activeConversationId || (!hasMessages && !isStreaming);

  const handleSend = useCallback(
    async (content: string) => {
      let convId = activeConversationIdRef.current;

      // Auto-create conversation if none is active
      if (!convId) {
        try {
          const conv = await createConversation();
          convId = conv.id;
          await selectConversation(conv.id);
        } catch {
          return;
        }
      }

      await startStream(convId, content);
    },
    [createConversation, selectConversation, startStream],
  );

  const handleNewChat = useCallback(() => {
    // Just clear the selection, a new conversation will be created on first message
    useConversationStore.setState({
      activeConversationId: null,
      activeConversation: null,
      streamContent: '',
      streamSources: [],
    });
  }, []);

  const handleSelectChat = useCallback(
    (id: string) => {
      selectConversation(id);
      setSidebarOpen(false); // auto-close sidebar on mobile
    },
    [selectConversation],
  );

  const toggleSidebar = useCallback(() => {
    setSidebarOpen((s) => !s);
  }, []);

  return (
    <div className="flex h-screen bg-slate-950 text-white overflow-hidden">
      {/* ── Sidebar ──────────────────────────────────────────────── */}
      <aside
        className={`fixed inset-y-0 left-0 z-30 w-72 border-r border-slate-800 bg-slate-950/95 backdrop-blur-xl transform transition-transform duration-200 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <ConversationSidebar
          onNewChat={handleNewChat}
          onSelectChat={handleSelectChat}
          activeId={activeConversationId}
        />
      </aside>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/50 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ── Main chat area ────────────────────────────────────────── */}
      <div className={`flex flex-1 flex-col min-w-0 transition-all duration-200 ${
        sidebarOpen ? 'lg:ml-72' : 'lg:ml-0'
      }`}>
        {/* ── Top bar ──────────────────────────────────────────── */}
        <header className="flex items-center justify-between border-b border-slate-800 bg-slate-950/80 backdrop-blur-sm px-4 py-3 shrink-0">
          <div className="flex items-center gap-3">
            <button
              onClick={toggleSidebar}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
            >
              {sidebarOpen ? (
                <ChevronLeft className="h-5 w-5" />
              ) : (
                <Menu className="h-5 w-5" />
              )}
            </button>
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-cyan-400" />
              <span className="text-sm font-semibold">
                {activeConversation?.title || 'DocGPT Chat'}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {user && (
              <span className="hidden sm:flex items-center gap-2 text-sm text-slate-400">
                <User className="h-4 w-4" />
                {user.full_name}
              </span>
            )}
            <button
              onClick={logout}
              className="flex items-center gap-2 rounded-full border border-red-400/20 bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-300 transition hover:bg-red-500/20"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </header>

        {/* ── Messages area ───────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          <div className="mx-auto max-w-3xl px-4 py-6">
            {/* Welcome screen */}
            {showWelcome && (
              <div className="flex h-full min-h-[60vh] flex-col items-center justify-center text-center">
                <div className="rounded-3xl bg-gradient-to-br from-cyan-500/10 via-slate-900 to-violet-500/10 p-8 border border-slate-800 shadow-2xl max-w-md">
                  <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-cyan-500/15 text-cyan-300 mb-4">
                    <MessageSquare className="h-8 w-8" />
                  </div>
                  <h2 className="text-xl font-semibold text-white">
                    Ask anything about your documents
                  </h2>
                  <p className="mt-2 text-sm text-slate-400 leading-relaxed">
                    Your documents have been processed and indexed. Start a
                    conversation to ask questions, get summaries, or extract
                    insights using AI-powered RAG.
                  </p>
                  <div className="mt-6 flex flex-wrap justify-center gap-2 text-xs text-slate-500">
                    <span className="rounded-full border border-slate-700 px-3 py-1">
                      🔍 Hybrid search
                    </span>
                    <span className="rounded-full border border-slate-700 px-3 py-1">
                      📄 Source citations
                    </span>
                    <span className="rounded-full border border-slate-700 px-3 py-1">
                      ⚡ Real-time streaming
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Messages */}
            {hasMessages && (
              <div className="space-y-5">
                {activeConversation.messages.map((msg) => (
                  <ChatMessage key={msg.id} message={msg} />
                ))}

                {/* Streaming content */}
                {isStreaming && streamContent && (
                  <ChatMessage
                    message={{
                      id: -1,
                      role: 'assistant',
                      content: streamContent,
                      sources: null,
                      created_at: new Date().toISOString(),
                    }}
                    isStreaming={true}
                  />
                )}

                {/* Typing indicator (before any tokens arrive) */}
                {isStreaming && !streamContent && <TypingIndicator />}
              </div>
            )}

            {/* Stream error */}
            {streamError && (
              <div className="mt-5 flex items-start gap-3 rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3">
                <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-400" />
                <div>
                  <p className="text-sm font-medium text-red-300">Stream Error</p>
                  <p className="mt-1 text-sm text-red-200/80">{streamError}</p>
                </div>
              </div>
            )}

            {/* Sources panel */}
            {streamSources.length > 0 && (
              <div className="mt-5">
                <SourcePanel
                  sources={streamSources}
                  isOpen={sourcesOpen}
                  onToggle={() => setSourcesOpen((s) => !s)}
                />
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* ── Input area ──────────────────────────────────────── */}
        <div className="border-t border-slate-800 bg-slate-950/80 backdrop-blur-sm px-4 py-3 shrink-0">
          <div className="mx-auto max-w-3xl">
            <ChatInput
              onSend={handleSend}
              onAbort={abortStream}
              isStreaming={isStreaming}
            />
            <p className="mt-2 text-center text-[10px] text-slate-600">
              Responses are generated by AI based on your document context.
              Verify important information.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ChatPage;
