"""
Command-line start-up for the review app.

    PYTHONPATH=src python -m bellhaven_sync.review_app
    PYTHONPATH=src python -m bellhaven_sync.review_app --rehearsal-only

One running app serves both modes; switch between them with the Rehearsal /
Production control at the top of every page. The app always opens in
Rehearsal unless told otherwise.

The app listens on this computer only (127.0.0.1), so nobody else on the
network can reach the Approve button.
"""

from __future__ import annotations

import argparse

from .. import config
from . import SLUG_OF_MODE, create_app


def main() -> None:
    """Parse the command line and start the local web server."""
    parser = argparse.ArgumentParser(description="Bellhaven ownership sync: review app.")
    parser.add_argument("--mode", choices=[config.MODE_REHEARSAL, config.MODE_LIVE, "production"],
                        default=config.MODE_REHEARSAL,
                        help="which mode the app opens in (default: rehearsal). "
                             "'live' and 'production' mean the same thing.")
    parser.add_argument("--rehearsal-only", action="store_true",
                        help="switch production mode off entirely for this session")
    parser.add_argument("--port", type=int, default=5001, help="port to listen on (default 5001)")
    args = parser.parse_args()

    mode = config.MODE_LIVE if args.mode == "production" else args.mode
    if args.rehearsal_only:
        mode = config.MODE_REHEARSAL
    app = create_app(default_mode=mode, allow_production=not args.rehearsal_only)

    base = f"http://127.0.0.1:{args.port}"
    print(f"\n  Review app running: {base}")
    print(f"    Rehearsal : {base}/rehearsal/   (local copy; includes the Smoke test page)")
    if args.rehearsal_only:
        print("    Production: switched off (--rehearsal-only)")
    else:
        print(f"    Production: {base}/production/  (real CRM)")
    print(f"  Opens in {SLUG_OF_MODE[mode].upper()} mode.\n")
    # debug=False: no auto-reloader, so the app can never start twice and
    # there is no interactive debugger exposed.
    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
