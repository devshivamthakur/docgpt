import { create } from 'zustand';
import api from './api';

// ── Types ────────────────────────────────────────────────────────────

export type DocumentStatus =
  | 'uploading'
  | 'uploaded'
  | 'parsing'
  | 'chunking'
  | 'embedding'
  | 'indexing'
  | 'ready'
  | 'failed';

export interface Document {
  id: number;
  filename: string;
  original_filename: string;
  file_size: number;
  mime_type: string;
  status: DocumentStatus;
  progress: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProgressPayload {
  status: DocumentStatus;
  progress: number;
  message: string;
}

export interface StorageUsage {
  total_used_bytes: number;
  quota_bytes: number;
  used_percent: number;
}

export interface DocumentState {
  /* ── State ────────────────────────────────────────────────────── */
  documents: Document[];
  total: number;
  isLoading: boolean;
  isUploading: boolean;
  error: string | null;
  /** Map of document-id → live progress (driven by WebSocket) */
  liveProgress: Record<number, ProgressPayload>;
  /** Storage usage info */
  storageUsage: StorageUsage | null;

  /* ── Actions ──────────────────────────────────────────────────── */
  fetchDocuments: () => Promise<void>;
  fetchDocumentsPage: (skip?: number, limit?: number) => Promise<void>;
  fetchStorageUsage: () => Promise<void>;
  uploadDocument: (file: File) => Promise<Document>;
  deleteDocument: (id: number) => Promise<void>;
  reprocessDocument: (id: number) => Promise<void>;
  updateProgress: (docId: number, payload: ProgressPayload) => void;
  clearError: () => void;
}

// ── Status display helpers ──────────────────────────────────────────

export const STATUS_LABELS: Record<DocumentStatus, string> = {
  uploading: 'Uploading…',
  uploaded: 'Queued',
  parsing: 'Parsing…',
  chunking: 'Chunking…',
  embedding: 'Embedding…',
  indexing: 'Indexing…',
  ready: 'Ready',
  failed: 'Failed',
};

export const STATUS_ORDER: DocumentStatus[] = [
  'uploading',
  'uploaded',
  'parsing',
  'chunking',
  'embedding',
  'indexing',
  'ready',
  'failed',
];

// ── Store ────────────────────────────────────────────────────────────

export const useDocumentStore = create<DocumentState>((set, get) => ({
  documents: [],
  total: 0,
  isLoading: false,
  isUploading: false,
  error: null,
  liveProgress: {},
  storageUsage: null,

  fetchDocuments: async () => {
    set({ isLoading: true, error: null });
    try {
      const { data } = await api.get('/documents');
      set({ documents: data.documents, total: data.total, isLoading: false });
    } catch (err: any) {
      set({ error: err.normalizedMessage || 'Failed to load documents', isLoading: false });
    }
  },

  fetchDocumentsPage: async (skip = 0, limit = 20) => {
    set({ isLoading: true, error: null });
    try {
      const { data } = await api.get('/documents', { params: { skip, limit } });
      set({ documents: data.documents, total: data.total, isLoading: false });
    } catch (err: any) {
      set({ error: err.normalizedMessage || 'Failed to load documents', isLoading: false });
    }
  },

  fetchStorageUsage: async () => {
    try {
      const { data } = await api.get('/documents/storage/usage');
      set({ storageUsage: data });
    } catch {
      // Non-critical — silently ignore
    }
  },

  uploadDocument: async (file: File) => {
    set({ isUploading: true, error: null });
    try {
      const formData = new FormData();
      formData.append('file', file);
      const { data } = await api.post('/documents', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      // Prepend the new document to the list
      const newDoc: Document = {
        id: data.id,
        filename: data.filename,
        original_filename: data.filename,
        file_size: file.size,
        mime_type: file.type || 'application/octet-stream',
        status: data.status,
        progress: 0,
        error_message: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      set((s) => ({
        documents: [newDoc, ...s.documents],
        total: s.total + 1,
        isUploading: false,
      }));
      return newDoc;
    } catch (err: any) {
      const message = err.normalizedMessage || 'Upload failed';
      set({ error: message, isUploading: false });
      throw new Error(message);
    }
  },

  deleteDocument: async (id: number) => {
    set({ error: null });
    try {
      await api.delete(`/documents/${id}`);
      set((s) => ({
        documents: s.documents.filter((d) => d.id !== id),
        total: s.total - 1,
      }));
      // Refresh storage after deletion
      get().fetchStorageUsage();
    } catch (err: any) {
      set({ error: err.normalizedMessage || 'Failed to delete document' });
    }
  },

  reprocessDocument: async (id: number) => {
    set({ error: null });
    try {
      // Optimistically mark as 'uploaded' so the UI shows progress
      set((s) => ({
        documents: s.documents.map((d) =>
          d.id === id
            ? { ...d, status: 'uploaded' as DocumentStatus, progress: 0, error_message: null }
            : d,
        ),
      }));

      await api.post(`/documents/${id}/reprocess`);
      // The WebSocket will drive further progress updates
    } catch (err: any) {
      // Revert on failure — re-fetch to get accurate state
      set({ error: err.normalizedMessage || 'Failed to reprocess document' });
      get().fetchDocuments();
    }
  },

  updateProgress: (docId: number, payload: ProgressPayload) => {
    set((s) => ({
      liveProgress: { ...s.liveProgress, [docId]: payload },
      // Also update the document in the list
      documents: s.documents.map((d) =>
        d.id === docId
          ? { ...d, status: payload.status, progress: payload.progress }
          : d,
      ),
    }));
  },

  clearError: () => set({ error: null }),
}));
