"""Child-process entry point for one transcription: ``python -m research_control.media_worker AUDIO OUT``."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from research_control.media import transcribe_in_process


def main() -> None:
    audio, output = Path(sys.argv[1]), Path(sys.argv[2])
    lines, note = transcribe_in_process(audio)
    output.write_text(json.dumps({"lines": lines, "note": note}), encoding="utf-8")


if __name__ == "__main__":
    main()
