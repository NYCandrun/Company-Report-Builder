#!/usr/bin/env python3
"""Compatibility entry point for independent release acceptance."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_control.gates.release import main


if __name__ == "__main__":
    main()
