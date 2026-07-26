"""Console input helpers shared by interactive Archive commands."""
from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TextIO


class ConsoleInputClosedError(RuntimeError):
    """Raised when an interactive confirmation cannot read from stdin."""


def wait_for_console_enter(
    *,
    stdin: TextIO | None = None,
    key_reader: Callable[[], str] | None = None,
    platform: str | None = None,
) -> None:
    """Wait for a real Enter confirmation without treating stdin EOF as input."""
    current_platform = sys.platform if platform is None else platform
    if current_platform == "win32":
        if key_reader is None:
            import msvcrt

            key_reader = msvcrt.getwch
        while True:
            if key_reader() in ("\r", "\n"):
                return

    stream = sys.stdin if stdin is None else stdin
    if stream.readline() == "":
        raise ConsoleInputClosedError(
            "stdin closed while waiting for interactive Enter confirmation"
        )
