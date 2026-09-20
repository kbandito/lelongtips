"""Where the session cookie comes from.

The value is read from a file by default rather than an environment
variable. Laravel's cookie is percent-encoded, and Windows batch files
mangle "%" during expansion, so passing it through `set` silently corrupts
it. A file keeps the bytes intact and out of the shell history.
"""

import os
from pathlib import Path

DEFAULT_FILE = Path(__file__).resolve().parent.parent / "local" / "cookie.txt"


def load_cookie():
    """Return the cookie string, or "" when none is configured.

    Order: LELONGTIPS_COOKIE, then the file named by LELONGTIPS_COOKIE_FILE,
    then local/cookie.txt. CI supplies the environment variable; a local run
    normally uses the file.
    """
    raw = os.getenv("LELONGTIPS_COOKIE", "").strip()
    if raw:
        return raw

    path = os.getenv("LELONGTIPS_COOKIE_FILE", "").strip()
    candidate = Path(path) if path else DEFAULT_FILE
    try:
        if candidate.is_file():
            # Take the first non-empty line; editors like to add a trailing one.
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
    except OSError as e:
        print(f"Could not read cookie file {candidate}: {e}")
    return ""


def describe_source():
    """Say where the cookie came from, without revealing it."""
    if os.getenv("LELONGTIPS_COOKIE", "").strip():
        return "environment variable LELONGTIPS_COOKIE"
    path = os.getenv("LELONGTIPS_COOKIE_FILE", "").strip()
    candidate = Path(path) if path else DEFAULT_FILE
    return str(candidate) if candidate.is_file() else "nowhere (no cookie configured)"
