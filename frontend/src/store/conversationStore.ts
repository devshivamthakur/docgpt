import { create } from 'zustand';
import api from './api';

// ── Types ────────────────────────────────────────────────────────────

export interface SourceItem {
  document_id: number;
  document_name: string;
  page_index: number | null;
  chunk_index: number | null;
  content: string;
  score: number | null;
}

export interface Message {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  sources: SourceItem[] | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface ConversationState {
  /* ── State ────────────────────────────────────────────────────── */
  conversations: Conversation[];
  total: number;
  activeConversationId: string | null;
  activeConversation: ConversationDetail | null;
  isLoadingList: boolean;
  isLoadingDetail: boolean;
  isStreaming: boolean;
  error: string | null;
  /** Accumulated streaming content for the current assistant response */
  streamContent: string;
  streamSources: SourceItem[];
  /** Error message from the stream (e.g., timeout, safety rejection) */
  streamError: string | null;

  /* ── Actions ──────────────────────────────────────────────────── */
  fetchConversations: () => Promise<void>;
  createConversation: (title?: string) => Promise<Conversation>;
  selectConversation: (id: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
  sendMessage: (conversationId: string, content: string) => void;
  appendStreamToken: (token: string) => void;
  setStreamSources: (sources: SourceItem[]) => void;
  setStreamError: (message: string) => void;
  finalizeStream: (content: string, sources?: SourceItem[]) => void;
  resetStream: () => void;
  clearError: () => void;
  /** Add a user message to the active conversation optimistically */
  addOptimisticUserMessage: (content: string) => void;
}

// ── Store ────────────────────────────────────────────────────────────

export const useConversationStore = create<ConversationState>((set, get) => ({
  conversations: [],
  total: 0,
  activeConversationId: null,
  activeConversation: null,
  isLoadingList: false,
  isLoadingDetail: false,
  isStreaming: false,
  error: null,
  streamContent: '',
  streamSources: [],
  streamError: null,

  fetchConversations: async () => {
    set({ isLoadingList: true, error: null });
    try {
      const { data } = await api.get('/conversations');
      set({
        conversations: data.conversations,
        total: data.total,
        isLoadingList: false,
      });
    } catch (err: any) {
      set({
        error: err.normalizedMessage || 'Failed to load conversations',
        isLoadingList: false,
      });
    }
  },

  createConversation: async (title = 'New conversation') => {
    set({ error: null });
    try {
      const { data } = await api.post('/conversations', { title });
      set((s) => ({
        conversations: [data, ...s.conversations],
        total: s.total + 1,
      }));
      return data as Conversation;
    } catch (err: any) {
      set({ error: err.normalizedMessage || 'Failed to create conversation' });
      throw err;
    }
  },

  selectConversation: async (id: string) => {
    set({ isLoadingDetail: true, error: null, activeConversationId: id });
    try {
      const { data } = await api.get(`/conversations/${id}`);
      set({
        activeConversation: data as ConversationDetail,
        isLoadingDetail: false,
      });
    } catch (err: any) {
      set({
        error: err.normalizedMessage || 'Failed to load conversation',
        isLoadingDetail: false,
      });
    }
  },

  deleteConversation: async (id: string) => {
    set({ error: null });
    try {
      await api.delete(`/conversations/${id}`);
      set((s) => {
        const next = {
          conversations: s.conversations.filter((c) => c.id !== id),
          total: s.total - 1,
        };
        // If the deleted conversation was active, clear it
        if (s.activeConversationId === id) {
          return {
            ...next,
            activeConversationId: null,
            activeConversation: null,
          };
        }
        return next;
      });
    } catch (err: any) {
      set({ error: err.normalizedMessage || 'Failed to delete conversation' });
    }
  },

  sendMessage: (_conversationId: string, _content: string) => {
    // The actual SSE connection is managed by the useChatStream hook
    // This just sets streaming state
    set({ isStreaming: true, streamContent: '', streamSources: [], streamError: null });
  },

  appendStreamToken: (token: string) => {
    set((s) => ({ streamContent: s.streamContent + token }));
  },

  setStreamSources: (sources: SourceItem[]) => {
    set({ streamSources: sources });
  },

  setStreamError: (message: string) => {
    set({ streamError: message, isStreaming: false });
  },

  finalizeStream: (content: string, sources?: SourceItem[]) => {
    set((s) => {
      const activeConv = s.activeConversation;
      if (!activeConv) return { isStreaming: false };

      const finalSources = sources ?? s.streamSources;

      const newMessage: Message = {
        id: -Date.now(), // temporary negative id until conversation is refreshed
        role: 'assistant',
        content: content || s.streamContent,
        sources: finalSources.length > 0 ? finalSources : null,
        created_at: new Date().toISOString(),
      };

      return {
        isStreaming: false,
        streamContent: '',
        streamError: null,
        activeConversation: {
          ...activeConv,
          messages: [...activeConv.messages, newMessage],
        },
      };
    });
  },

  resetStream: () => {
    set({
      isStreaming: false,
      streamContent: '',
      streamSources: [],
      streamError: null,
    });
  },

  clearError: () => set({ error: null }),

  addOptimisticUserMessage: (content: string) => {
    set((s) => {
      const activeConv = s.activeConversation;
      if (!activeConv) return {};

      const tempMsg: Message = {
        id: -Date.now(), // temporary negative id
        role: 'user',
        content,
        sources: null,
        created_at: new Date().toISOString(),
      };

      return {
        activeConversation: {
          ...activeConv,
          messages: [...activeConv.messages, tempMsg],
        },
      };
    });
  },
}));
