import re

# ── Auth / Password ────────────────────────────────────────────────────
PASSWORD_MIN_LENGTH: int = 8

PASSWORD_PATTERN: re.Pattern = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()\-_=+{};:,<.>]).+$"
)

PASSWORD_SPECIAL_CHARS: str = r"!@#$%^&*()\-_=+{};:,<.>"
