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

export interface DocumentState {
  /* ── State ────────────────────────────────────────────────────── */
  documents: Document[];
  total: number;
  isLoading: boolean;
  isUploading: boolean;
  error: string | null;
  /** Map of document-id → live progress (driven by WebSocket) */
  liveProgress: Record<number, ProgressPayload>;

  /* ── Actions ──────────────────────────────────────────────────── */
  fetchDocuments: () => Promise<void>;
  uploadDocument: (file: File) => Promise<Document>;
  deleteDocument: (id: number) => Promise<void>;
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

  fetchDocuments: async () => {
    set({ isLoading: true, error: null });
    try {
      const { data } = await api.get('/documents');
      set({ documents: data.documents, total: data.total, isLoading: false });
    } catch (err: any) {
      set({ error: err.normalizedMessage || 'Failed to load documents', isLoading: false });
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
    } catch (err: any) {
      set({ error: err.normalizedMessage || 'Failed to delete document' });
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
