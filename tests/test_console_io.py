import io
import sys
import types

import pytest

sys.path.insert(0, "src")

import console_io


def test_wait_for_console_enter_uses_msvcrt_until_enter(monkeypatch):
    keys = iter(["x", "\r"])
    fake_msvcrt = types.SimpleNamespace(getwch=lambda: next(keys))
    stdin = io.StringIO("must not be read")

    monkeypatch.setattr(console_io.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)

    console_io.wait_for_console_enter(stdin=stdin)

    assert stdin.tell() == 0


def test_wait_for_console_enter_prints_prompt(monkeypatch, capsys):
    fake_msvcrt = types.SimpleNamespace(getwch=lambda: "\n")

    monkeypatch.setattr(console_io.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)

    console_io.wait_for_console_enter("press enter")

    assert capsys.readouterr().out == "press enter\n"


def test_wait_for_console_enter_rejects_stdin_eof(monkeypatch):
    class EofStream(io.StringIO):
        def __init__(self):
            super().__init__("")
            self.readline_calls = 0

        def readline(self, *args, **kwargs):
            self.readline_calls += 1
            return super().readline(*args, **kwargs)

    stdin = EofStream()

    monkeypatch.setattr(console_io.sys, "platform", "linux")

    with pytest.raises(console_io.ConsoleInputClosedError, match="stdin closed"):
        console_io.wait_for_console_enter(stdin=stdin)

    assert stdin.readline_calls == 1


def test_wait_for_console_enter_supports_injected_windows_key_reader():
    keys = iter(["x", "\x00", "\r"])

    console_io.wait_for_console_enter(
        platform="win32",
        key_reader=lambda: next(keys),
    )

    assert list(keys) == []
