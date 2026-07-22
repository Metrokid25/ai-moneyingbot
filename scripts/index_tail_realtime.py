"""Compatibility entry point for the canonical :mod:`index_tail` module.

Historically this file was a full fork of ``index_tail.py``.  Importers now
receive the canonical module object so monkeypatching and private helper access
continue to behave exactly as they did, while the script path remains valid for
existing launchers and logs.
"""
from __future__ import annotations

import sys

if __package__:
    from . import index_tail as _canonical
else:
    import index_tail as _canonical


if __name__ == "__main__":
    raise SystemExit(_canonical.main())

# ``from index_tail_realtime import run_realtime_index`` and ordinary imports
# both resolve to the same module object.  This preserves existing callers that
# monkeypatch module-level helpers without maintaining a second implementation.
sys.modules[__name__] = _canonical
