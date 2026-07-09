// ── Auth / Password ──────────────────────────────────────────────────
export const PASSWORD_MIN_LENGTH = 8;

export const PASSWORD_PATTERN =
  /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()\-_=+{};:,<.>]).+$/;

export const PASSWORD_SPECIAL_CHARS = '!@#$%^&*()\\-_=+{};:,<.>';

// ── Email ────────────────────────────────────────────────────────────
export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
