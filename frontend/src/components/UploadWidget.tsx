import React, { useCallback, useRef, useState } from 'react';
import { FileUp, FileText, AlertCircle, Loader2 } from 'lucide-react';
import { useDocumentStore } from '../store/documentStore';

const ALLOWED_TYPES = [
  'application/pdf',
  'text/plain',
  'text/markdown',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
];

const ALLOWED_EXTENSIONS = ['.pdf', '.txt', '.md', '.doc', '.docx'];
const MAX_SIZE_MB = 50;

interface UploadWidgetProps {
  onUploadStart?: () => void;
  onUploadComplete?: (docId?: number) => void;
}

function UploadWidget({ onUploadStart, onUploadComplete }: UploadWidgetProps) {
  const uploadDocument = useDocumentStore((s) => s.uploadDocument);
  const isUploading = useDocumentStore((s) => s.isUploading);

  const [isDragOver, setIsDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const validateFile = useCallback((file: File): string | null => {
    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `Unsupported file type "${ext}". Allowed: PDF, TXT, MD, DOC, DOCX`;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      return `File exceeds the ${MAX_SIZE_MB} MB limit`;
    }
    return null;
  }, []);

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
                PDF, TXT, MD, DOC, DOCX &mdash; up to {MAX_SIZE_MB} MB
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
    </div>
  );
}

export default React.memo(UploadWidget);
