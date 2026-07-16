import re

# ── LLM Providers ──────────────────────────────────────────────────────
PROVIDER_OPENAI: str = "openai"
PROVIDER_OPENAI_COMPATIBLE: str = "openai_compatible"
PROVIDER_GOOGLE: str = "google"

# ── Auth / Password ────────────────────────────────────────────────────
PASSWORD_MIN_LENGTH: int = 8

PASSWORD_PATTERN: re.Pattern = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()\-_=+{};:,<.>]).+$"
)

PASSWORD_SPECIAL_CHARS: str = r"!@#$%^&*()\-_=+{};:,<.>"

# ── Rate Limiting ──────────────────────────────────────────────────────
RATE_LIMIT_GLOBAL_MAX: int = 100  # Max requests per window
RATE_LIMIT_GLOBAL_WINDOW: int = 60  # Window in seconds (per minute)

RATE_LIMIT_AUTH_MAX: int = 10  # Login/register attempts
RATE_LIMIT_AUTH_WINDOW: int = 60  # Per minute

RATE_LIMIT_DOCUMENTS_MAX: int = 30  # Document operations
RATE_LIMIT_DOCUMENTS_WINDOW: int = 60  # Per minute

RATE_LIMIT_CONVERSATIONS_MAX: int = 60  # Chat / conversation ops
RATE_LIMIT_CONVERSATIONS_WINDOW: int = 60  # Per minute
