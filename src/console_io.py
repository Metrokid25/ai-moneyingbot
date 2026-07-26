"""Small helpers for console interaction shared by Archive entry points."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TextIO


class ConsoleInputClosedError(RuntimeError):
    """Raised when an interactive confirmation cannot read from stdin."""


def wait_for_console_enter(
    prompt: str | None = None,
    *,
    stdin: TextIO | None = None,
    key_reader: Callable[[], str] | None = None,
    platform: str | None = None,
) -> None:
    """Wait for a real Enter confirmation without treating stdin EOF as input."""
    if prompt is not None:
        print(prompt, flush=True)

    current_platform = sys.platform if platform is None else platform
    if current_platform == "win32":
        if key_reader is None:
            import msvcrt

            key_reader = msvcrt.getwch
        while True:
            if key_reader() in ("\r", "\n"):
                return

    input_stream = stdin if stdin is not None else sys.stdin
    if input_stream.readline() == "":
        raise ConsoleInputClosedError(
            "stdin closed while waiting for interactive Enter confirmation"
        )
