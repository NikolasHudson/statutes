"""Tiny streaming reader for the Phase-1 JSONL artifacts.

One JSON object per line. Streams — never loads the (multi-GB) opinions
artifact into memory.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)
