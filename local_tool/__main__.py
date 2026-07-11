"""`python -m local_tool <verb>` — see local_tool/cli for the verbs."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
