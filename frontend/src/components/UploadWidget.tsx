import React, { useCallback, useRef, useState } from 'react';
import { FileUp, FileText, AlertCircle, Loader2, HardDrive } from 'lucide-react';
import { useDocumentStore } from '../store/documentStore';
import { sanitizeFilename } from '../utils/sanitize';

// Allowed MIME types (validated on both client and server)
const ALLOWED_TYPES = [
  'application/pdf',
  'text/plain',
  'text/markdown',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
];

const ALLOWED_EXTENSIONS = ['.pdf', '.txt', '.md', '.doc', '.docx'];
const MAX_SIZE_MB = 50;

function formatSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface UploadWidgetProps {
  onUploadStart?: () => void;
  onUploadComplete?: (docId?: number) => void;
  storageUsed?: number;
  storageQuota?: number;
}

function UploadWidget({
  onUploadStart,
  onUploadComplete,
  storageUsed = 0,
  storageQuota = 1_073_741_824,
}: UploadWidgetProps) {
  const uploadDocument = useDocumentStore((s) => s.uploadDocument);
  const isUploading = useDocumentStore((s) => s.isUploading);

  const [isDragOver, setIsDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const remainingBytes = Math.max(storageQuota - storageUsed, 0);
  const remainingPercent = storageQuota > 0 ? (remainingBytes / storageQuota) * 100 : 0;

  const validateFile = useCallback(
    (file: File): string | null => {
      // Extension validation
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      if (!ALLOWED_EXTENSIONS.includes(ext)) {
        return `Unsupported file type "${ext}". Allowed: PDF, TXT, MD, DOC, DOCX`;
      }

      // MIME type validation (prevents renamed executables)
      if (!ALLOWED_TYPES.includes(file.type) && file.type !== '') {
        return `File type "${file.type}" is not allowed.`;
      }

      // Size validation
      if (file.size > MAX_SIZE_MB * 1024 * 1024) {
        return `File exceeds the ${MAX_SIZE_MB} MB limit`;
      }

      // Storage quota check
      if (file.size > remainingBytes) {
        return `Not enough storage space. Only ${formatSize(remainingBytes)} remaining, but this file is ${formatSize(file.size)}.`;
      }

      // Filename sanitization check
      const sanitized = sanitizeFilename(file.name);
      if (sanitized !== file.name) {
        return 'Filename contains invalid characters. Please rename the file and try again.';
      }

      return null;
    },
    [remainingBytes],
  );

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        return;
      }
      try {
        onUploadStart?.();
        const doc = await uploadDocument(file);
        onUploadComplete?.(doc?.id);
      } catch (err: any) {
        setError(err.message || 'Upload failed');
      }
    },
    [uploadDocument, validateFile, onUploadStart, onUploadComplete],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleClick = useCallback(() => {
    inputRef.current?.click();
  }, []);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
      // Reset so the same file can be re-uploaded
      e.target.value = '';
    },
    [handleFile],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        handleClick();
      }
    },
    [handleClick],
  );

  return (
    <div className="space-y-3">
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={handleClick}
        role="button"
        tabIndex={0}
        onKeyDown={handleKeyDown}
        className={`
          relative cursor-pointer rounded-2xl border-2 border-dashed p-8 text-center
          transition-all duration-200
          ${isDragOver
            ? 'border-cyan-400 bg-cyan-500/15 shadow-[0_0_30px_-8px_rgba(34,211,238,0.3)]'
            : 'border-slate-700 bg-slate-900/60 hover:border-slate-600 hover:bg-slate-900/80'
          }
          ${isUploading ? 'pointer-events-none opacity-60' : ''}
        `}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ALLOWED_TYPES.join(',')}
          className="hidden"
          onChange={handleInputChange}
        />

        {isUploading ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="h-10 w-10 animate-spin text-cyan-400" />
            <p className="text-base font-medium text-cyan-200">Uploading…</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            {isDragOver ? (
              <FileUp className="h-10 w-10 text-cyan-400" />
            ) : (
              <FileText className="h-10 w-10 text-slate-500" />
            )}
            <div>
              <p className="text-base font-medium text-slate-200">
                {isDragOver
                  ? 'Drop your file here'
                  : 'Drag & drop a file, or click to browse'}
              </p>
              <p className="mt-1 text-sm text-slate-500">
                PDF, TXT, MD, DOC, DOCX &mdash; up to {MAX_SIZE_MB} MB each
              </p>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Storage remaining indicator */}
      <div className="flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-2.5">
        <HardDrive className="h-4 w-4 text-slate-500" />
        <div className="flex-1">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400">
              Storage remaining: <span className="font-medium text-slate-300">{formatSize(remainingBytes)}</span>
            </span>
            <span className="text-slate-500">{remainingPercent.toFixed(0)}% free</span>
          </div>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-800">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                remainingPercent < 10
                  ? 'bg-red-500'
                  : remainingPercent < 25
                    ? 'bg-amber-500'
                    : 'bg-emerald-500/60'
              }`}
              style={{ width: `${remainingPercent}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export default React.memo(UploadWidget);
