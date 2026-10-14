"""Entrypoint for the Logistics PDF Auditor desktop application."""

from __future__ import annotations

import sys
from gui import LogisticsAuditorApp


def main() -> None:
    app = LogisticsAuditorApp()
    app.run()


if __name__ == "__main__":
    main()