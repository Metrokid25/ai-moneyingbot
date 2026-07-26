"""Small helpers for console interaction shared by Archive entry points."""

from __future__ import annotations

import sys
from typing import TextIO


def wait_for_console_enter(
    prompt: str | None = None,
    *,
    stdin: TextIO | None = None,
) -> None:
    """Wait for Enter without Windows PowerShell stdin EOF bypassing the wait."""
    if prompt is not None:
        print(prompt, flush=True)

    if sys.platform == "win32":
        import msvcrt

        while msvcrt.getwch() not in ("\r", "\n"):
            pass
        return

    input_stream = stdin if stdin is not None else sys.stdin
    input_stream.readline()
