"""
Central settings for the Bellhaven ownership sync.

Everything that another module might need to agree on lives here: where the
website and CRM are, where files are saved, the matching weights and cut-offs,
and how the API token is loaded. Keeping these in one place means the docs,
the tests and the code can never quietly disagree.

This module uses only the Python standard library.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------
# Where things are
# --------------------------------------------------------------------------

# Project root = two folders above this file (src/bellhaven_sync/config.py).
ROOT: Path = Path(__file__).resolve().parents[2]

# The fictional operator's public website and the CRM sandbox share one host.
SITE_BASE: str = "https://analyst-assessment-production.up.railway.app"
API_BASE: str = SITE_BASE + "/api/v1"

DATA_DIR: Path = ROOT / "data"
BACKUP_DIR: Path = DATA_DIR / "backups"
LOG_DIR: Path = ROOT / "logs"

# The CRM account that represents Bellhaven itself. Facilities owned by
# Bellhaven must have their parent_id pointing at this account.
BELLHAVEN_PARENT_NAME: str = "Bellhaven Senior Living (Parent Account)"

# Seconds to wait for the website or CRM before giving up on one request.
HTTP_TIMEOUT: int = 30

# --------------------------------------------------------------------------
# Matching weights and cut-offs (explained in docs/03-matching-explained.md)
# --------------------------------------------------------------------------

# Points awarded for each piece of evidence. They add up to 100.
WEIGHT_STREET_EXACT: int = 40   # same street address after tidying
WEIGHT_STREET_CLOSE: int = 25   # nearly the same street (small typo)
WEIGHT_ZIP_EXACT: int = 15      # same zip code
WEIGHT_ZIP_SWAPPED: int = 8     # zip differs only by two swapped digits
WEIGHT_CITY: int = 10           # same city
WEIGHT_NAME_MAX: int = 20       # scaled by how similar the names are (0..1)
WEIGHT_PHONE: int = 10          # same phone number
WEIGHT_ADMIN: int = 5           # website administrator is a CRM contact

# How similar two tidied street strings must be (0..1) to count as "close".
STREET_CLOSE_RATIO: float = 0.85

# Score bands. A pair's total score decides how the tool treats it.
THRESHOLD_MATCH: int = 65       # 65+  : same facility
THRESHOLD_PROBABLE: int = 50    # 50-64: probably the same, reviewer decides
THRESHOLD_LOOKALIKE: int = 30   # 30-49: lookalike, shown as evidence only

# If a scrape returns fewer than this share of the previous run's communities
# the run stops, because the website is probably broken rather than changed.
MIN_SCRAPE_SHARE: float = 0.8

# Website care offering -> CRM care_type vocabulary.
CARE_TYPE_MAP: dict[str, str] = {
    "Assisted Living": "Assisted Living",
    "Memory Support": "Memory Care",
    "Short-Term Rehabilitation & Nursing": "Skilled Nursing",
    "Independent Living": "Independent Living",
}

# The only values the CRM accepts in the status field.
VALID_STATUSES: tuple[str, ...] = ("Active", "Inactive", "Needs Review")

# Run modes. "rehearsal" works on a local copy of the CRM, "live" on the real one.
MODE_REHEARSAL: str = "rehearsal"
MODE_LIVE: str = "live"


@dataclass(frozen=True)
class ModePaths:
    """File locations that differ between rehearsal and live mode.

    Attributes:
        mode: "rehearsal" or "live".
        audit_db: SQLite audit trail file.
        runs_dir: Folder holding one sub-folder of trace records per run.
        export_csv: Human-readable export of the audit trail.
        local_crm: JSON file acting as the CRM in rehearsal mode (unused live).
    """

    mode: str
    audit_db: Path
    runs_dir: Path
    export_csv: Path
    local_crm: Path


def paths_for(mode: str) -> ModePaths:
    """Return the file locations for a run mode.

    Rehearsal files live under data/rehearsal/ so they can be wiped freely
    and can never be confused with the real audit trail.

    Args:
        mode: "rehearsal" or "live".

    Returns:
        A ModePaths describing where that mode reads and writes.

    Raises:
        ValueError: if the mode is not one of the two known modes.
    """
    if mode == MODE_LIVE:
        base = DATA_DIR
    elif mode == MODE_REHEARSAL:
        base = DATA_DIR / "rehearsal"
    else:
        raise ValueError(f"Unknown mode {mode!r}; use 'rehearsal' or 'live'.")
    return ModePaths(
        mode=mode,
        audit_db=base / "audit.db",
        runs_dir=base / "runs",
        export_csv=base / "decisions" / "audit-export.csv",
        local_crm=DATA_DIR / "rehearsal" / "crm.json",
    )


def load_token() -> str:
    """Find the personal CRM API token.

    Looks first at the BELLHAVEN_API_TOKEN environment variable, then at a
    `.env` file in the project root (a line `BELLHAVEN_API_TOKEN=...`). The
    token is deliberately never written in the source code or saved to git.

    Returns:
        The token string.

    Raises:
        RuntimeError: if no token can be found.
    """
    token = os.environ.get("BELLHAVEN_API_TOKEN", "").strip()
    if token:
        return token
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("BELLHAVEN_API_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
                if token:
                    return token
    raise RuntimeError(
        "No API token found. Put BELLHAVEN_API_TOKEN=<token> in the .env file "
        "(see .env.example)."
    )
