import ast
import re
import subprocess
import sys
from pathlib import Path


sys.path.insert(0, "scripts")

import index_tail
import index_tail_realtime


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REALTIME_SHIM = PROJECT_ROOT / "scripts" / "index_tail_realtime.py"


def test_realtime_import_is_the_canonical_index_tail_module():
    assert index_tail_realtime is index_tail
    assert index_tail_realtime.run_realtime_index is index_tail.run_realtime_index
    assert index_tail_realtime._collect_after_snapshot is index_tail._collect_after_snapshot


def test_realtime_entrypoint_contains_no_forked_functions_or_classes():
    tree = ast.parse(REALTIME_SHIM.read_text(encoding="utf-8"))
    definitions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]

    assert definitions == []


def test_unattended_loop_imports_realtime_runner_from_canonical_module():
    source = (PROJECT_ROOT / "scripts" / "run_daily_archive_loop.py").read_text(encoding="utf-8")

    assert "from index_tail import run_realtime_index" in source
    assert "from index_tail_realtime import run_realtime_index" not in source


def test_both_script_paths_expose_the_same_collect_after_snapshot_cli():
    outputs = []
    for script_name in ("index_tail.py", "index_tail_realtime.py"):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / script_name), "--help"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
        assert result.returncode == 0
        assert "--collect-after-snapshot" in result.stdout
        assert "--stop-after-empty-pages" in result.stdout
        outputs.append(result.stdout)

    option_sets = [set(re.findall(r"--[a-z][a-z-]+", output)) for output in outputs]
    assert option_sets[0] == option_sets[1]


def test_realtime_shim_supports_package_import_and_module_execution():
    package_import = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import scripts.index_tail as canonical; "
                "import scripts.index_tail_realtime as realtime; "
                "assert realtime is canonical"
            ),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    module_help = subprocess.run(
        [sys.executable, "-m", "scripts.index_tail_realtime", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )

    assert package_import.returncode == 0, package_import.stderr
    assert module_help.returncode == 0, module_help.stderr
    assert "--stop-after-empty-pages" in module_help.stdout
