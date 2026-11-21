"""
Rehearsal mode helper: build (or rebuild) a local copy of the CRM.

Rehearsal mode lets the whole system be practised - including approving and
rejecting in the review app - against a local copy made from the backup. The
real CRM is never contacted for writes in rehearsal mode.

Resetting wipes everything under data/rehearsal/ (the local CRM copy, the
rehearsal audit trail and rehearsal run traces), so a rehearsal can be
repeated as many times as needed.

Run it with:
    PYTHONPATH=src python -m bellhaven_sync.rehearsal reset
"""

from __future__ import annotations

import shutil
import sys

from . import backup, config
from .crm_client import LocalCrm


def reset() -> LocalCrm:
    """Wipe rehearsal data and rebuild the local CRM from the original backup.

    Returns:
        The fresh LocalCrm.
    """
    paths = config.paths_for(config.MODE_REHEARSAL)
    rehearsal_dir = paths.local_crm.parent
    if rehearsal_dir.exists():
        shutil.rmtree(rehearsal_dir)
    rehearsal_dir.mkdir(parents=True)
    return LocalCrm.from_backup(backup.original_backup(), paths.local_crm)


if __name__ == "__main__":
    if sys.argv[1:] != ["reset"]:
        print("Usage: python -m bellhaven_sync.rehearsal reset")
        raise SystemExit(2)
    crm = reset()
    print(f"Rehearsal CRM rebuilt from {backup.original_backup().name}: "
          f"{len(crm.accounts)} accounts, {len(crm.contacts)} contacts.")
    print("Rehearsal audit trail and run traces cleared.")
