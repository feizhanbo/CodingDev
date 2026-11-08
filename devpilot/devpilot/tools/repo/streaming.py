"""Bounded source reads, including files containing a single enormous line."""

import codecs
import hashlib
from pathlib import Path

from devpilot.execution import check_execution


def content_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            check_execution()
            block = handle.read(65536)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def bounded_lines(path: Path, limit: int):
    """Yield bounded text, discarding the tail of long lines without buffering it."""
    with path.open("rb") as handle:
        number = 0
        while True:
            check_execution()
            chunk = handle.readline(max(1, limit) + 1)
            if not chunk:
                return
            number += 1
            clipped = len(chunk) > limit
            prefix = chunk[:limit]
            while clipped and not chunk.endswith(b"\n"):
                check_execution()
                chunk = handle.readline(65536)
                if not chunk:
                    break
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            text = decoder.decode(prefix, final=not clipped).rstrip("\r\n")
            yield number, text, clipped
