/**
 * Frontend input sanitization for DocGPT.
 *
 * Provides client-side sanitization as a first line of defence against
 * prompt injection and malicious input. Server-side sanitization
 * (in ``app.core.sanitization``) is the authoritative layer.
 */

// ── Prompt injection patterns (client-side subset) ──────────────────

/** Patterns that strongly indicate a prompt injection attempt */
const REJECTED_PATTERNS: RegExp[] = [
  // Role / instruction hijacking
  /ignore\s+(all\s+)?(previous|prior|above|the\s+above)/i,
  /disregard\s+(all\s+)?(previous|prior|above|the\s+above)/i,
  /forget\s+(all\s+)?(previous|prior|above|the\s+above)/i,
  /overr(ide|ide\s+all)\s+(instructions|prompt|system\s+prompt|rules)/i,
  /you\s+are\s+(now|no\s+longer)\s+/i,
  /from\s+now\s+on\s*,\s*you\s+are\s+/i,
  /act\s+as\s+(if\s+)?(though\s+)?you\s+are\s+/i,

  // Jailbreak attempts
  /jail\s*break/i,
  /bypass\s+(the\s+)?(restrictions|filter|safeguards|safety|rules|guidelines)/i,
  /do\s+anything\s+now/i,
  /dan\s+(mode|activated|enabled)/i,
  /unfiltered\s+(mode|access|response|answers?)/i,
  /no\s+(restrictions|limits|boundaries|rules|filter|safeguards)/i,
  /(print|output|display|show|reveal|leak|dump)\s+(your\s+)?(system\s+)?prompt/i,
  /reveal\s+(your\s+)?(instructions|prompt|system\s+message)/i,

  // Prompt leaking
  /output\s+(your\s+)?(initial|first|beginning|opening)\s+(prompt|message|instruction)/i,
  /repeat\s+(after\s+me|this|the\s+above|everything\s+above)/i,
  /summarize\s+(the\s+)?(above|previous|system)\s+(prompt|message|instruction|text)/i,
  /ignore\s+the\s+above\s+and\s+/i,

  // XSS / HTML injection in queries
  /<script[\s>]/i,
  /onerror\s*=/i,
  /onload\s*=/i,
  /onclick\s*=/i,
  /javascript\s*:/i,
  /<iframe[\s>]/i,
  /<embed[\s>]/i,
  /<object[\s>]/i,
  /<svg[\s>]/i,
  /expression\s*\(/i,
];

/** Maximum length of a user query */
const MAX_QUERY_LENGTH = 10_000;

/**
 * Characters that MUST appear in a valid URL scheme.
 * Catches data: / javascript: / vbscript: URIs.
 */
const DANGEROUS_SCHEMES = /^(data|javascript|vbscript|file):/i;

// ── Public API ──────────────────────────────────────────────────────

export interface SanitizationResult {
  /** The cleaned text */
  cleaned: string;
  /** Whether the input is safe to process */
  valid: boolean;
  /** Reason if invalid */
  reason?: string;
}

/**
 * Sanitize a user message before sending to the API.
 *
 * - Trims whitespace
 * - Enforces length limit
 * - Rejects obvious prompt injection attempts
 * - Rejects dangerous URL schemes
 *
 * @param text - The raw user input
 * @returns A {@link SanitizationResult}
 */
export function sanitizeQuery(text: string): SanitizationResult {
  const trimmed = text.trim();

  // Empty check
  if (!trimmed) {
    return { cleaned: '', valid: false, reason: 'Message is required' };
  }

  // Length check
  if (trimmed.length > MAX_QUERY_LENGTH) {
    return {
      cleaned: trimmed.slice(0, MAX_QUERY_LENGTH),
      valid: true,
    };
  }

  // Scan for injection patterns
  for (const pattern of REJECTED_PATTERNS) {
    if (pattern.test(trimmed)) {
      return {
        cleaned: trimmed,
        valid: false,
        reason: 'Message contains potentially unsafe patterns and was not sent.',
      };
    }
  }

  // Check for dangerous URL schemes
  if (DANGEROUS_SCHEMES.test(trimmed)) {
    return {
      cleaned: trimmed,
      valid: false,
      reason: 'Message contains unsafe content and was not sent.',
    };
  }

  return { cleaned: trimmed, valid: true };
}

/**
 * Strip HTML tags from a string (prevents XSS in rendered content).
 */
export function stripHtml(html: string): string {
  return html.replace(/<[^>]*>/g, '');
}

/**
 * Basic HTML escape to prevent XSS in rendered content.
 */
export function escapeHtml(text: string): string {
  const map: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#x27;',
  };
  return text.replace(/[&<>"']/g, (ch) => map[ch] ?? ch);
}

/**
 * Sanitize a filename for safe display / download.
 * Removes path separators, null bytes, and other dangerous characters.
 */
export function sanitizeFilename(filename: string): string {
  return filename
    .replace(/[/\\?%*:|"<>]/g, '_')   // Replace dangerous chars
    .replace(/\0/g, '')               // Strip null bytes
    .replace(/\.\./g, '_')            // Prevent directory traversal
    .trim();
}
