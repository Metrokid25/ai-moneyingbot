import io
import sys

import pytest

sys.path.insert(0, "src")

from console_io import ConsoleInputClosedError, wait_for_console_enter


def test_windows_wait_ignores_other_keys_until_enter():
    keys = iter(["x", "\x00", "\r"])

    wait_for_console_enter(platform="win32", key_reader=lambda: next(keys))

    assert list(keys) == []


def test_stream_wait_accepts_a_submitted_line():
    wait_for_console_enter(platform="linux", stdin=io.StringIO("confirmed\n"))


def test_stream_wait_rejects_stdin_eof():
    with pytest.raises(ConsoleInputClosedError, match="stdin closed"):
        wait_for_console_enter(platform="linux", stdin=io.StringIO(""))
