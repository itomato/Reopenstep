#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from reopenstep_tool.boote_test import main


if __name__ == "__main__":
    raise SystemExit(main())
