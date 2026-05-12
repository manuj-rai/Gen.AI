from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    resolved = level.strip().upper() if level else "INFO"
    root = logging.getLogger()
    if root.handlers:
        # Avoid duplicate handlers when create_app() runs more than once (tests, reload).
        root.setLevel(resolved)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(resolved)
