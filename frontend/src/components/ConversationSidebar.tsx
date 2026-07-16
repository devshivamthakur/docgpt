import React, { useCallback } from 'react';
import {
  Plus,
  MessageSquare,
  Trash2,
  Loader2,
  Sparkles,
} from 'lucide-react';
import { useConversationStore, type Conversation } from '../store/conversationStore';

interface ConversationSidebarProps {
  onNewChat: () => void;
  onSelectChat: (id: string) => void;
  activeId: string | null;
}

// ── Memo'd conversation list item ────────────────────────────────────

interface ConversationItemProps {
  conv: Conversation;
  isActive: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}

const ConversationItem = React.memo(function ConversationItem({
  conv,
  isActive,
  onSelect,
  onDelete,
}: ConversationItemProps) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect(conv.id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(conv.id);
        }
      }}
      className={`group flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors cursor-pointer ${
        isActive
          ? 'bg-cyan-500/10 text-cyan-300 border-r-2 border-cyan-400'
          : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
      }`}
    >
      <MessageSquare className="h-4 w-4 shrink-0" />
      <span className="flex-1 truncate">{conv.title}</span>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete(conv.id);
        }}
        className="shrink-0 opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-500/15 text-slate-500 hover:text-red-300 transition-all"
        title="Delete"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  );
});

// ── Sidebar component ────────────────────────────────────────────────

function ConversationSidebar({
  onNewChat,
  onSelectChat,
  activeId,
}: ConversationSidebarProps) {
  const conversations = useConversationStore((s) => s.conversations);
  const isLoadingList = useConversationStore((s) => s.isLoadingList);
  const deleteConversation = useConversationStore((s) => s.deleteConversation);

  const handleDelete = useCallback(
    (id: string) => {
      if (confirm('Delete this conversation?')) {
        deleteConversation(id);
      }
    },
    [deleteConversation],
  );

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-4 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-cyan-400" />
          <span className="text-sm font-semibold text-white">Conversations</span>
        </div>
        <button
          onClick={onNewChat}
          className="flex items-center gap-1.5 rounded-full bg-cyan-500/15 px-3 py-1.5 text-xs font-medium text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/25 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          New
        </button>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {isLoadingList && conversations.length === 0 ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-slate-500" />
          </div>
        ) : conversations.length === 0 ? (
          <div className="px-4 py-12 text-center">
            <MessageSquare className="mx-auto h-8 w-8 text-slate-600" />
            <p className="mt-3 text-sm text-slate-500">No conversations yet</p>
            <p className="mt-1 text-xs text-slate-600">
              Start a new chat to begin
            </p>
          </div>
        ) : (
          <div className="py-2 space-y-0.5">
            {conversations.map((conv) => (
              <ConversationItem
                key={conv.id}
                conv={conv}
                isActive={activeId === conv.id}
                onSelect={onSelectChat}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default React.memo(ConversationSidebar);
