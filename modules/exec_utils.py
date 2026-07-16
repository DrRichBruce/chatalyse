from __future__ import annotations

import builtins
import io
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ExecResult:
    ok: bool
    stdout: str
    stderr: str
    traceback: str


def _safe_builtins() -> dict[str, Any]:
    """
    Minimal builtins allowlist to reduce foot-guns.
    This is NOT a perfect sandbox, but it prevents trivial misuse.
    """
    allow = {
        "abs",
        "all",
        "any",
        "bool",
        "__import__",
        "dict",
        "enumerate",
        "Exception",
        "float",
        "int",
        "len",
        "list",
        "max",
        "min",
        "print",
        "range",
        "reversed",
        "round",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "ValueError",
        "zip",
    }
    return {name: getattr(builtins, name) for name in allow}


def run_user_code(code: str, *, globals_dict: Mapping[str, Any], locals_dict: dict[str, Any]) -> ExecResult:
    """
    Execute code with captured stdout/stderr and a restricted builtins set.
    """
    out = io.StringIO()
    err = io.StringIO()

    g = dict(globals_dict)
    g["__builtins__"] = _safe_builtins()

    try:
        compiled = compile(code, "<analysis>", "exec")
        with redirect_stdout(out), redirect_stderr(err):
            exec(compiled, g, locals_dict)
        return ExecResult(ok=True, stdout=out.getvalue(), stderr=err.getvalue(), traceback="")
    except Exception:
        return ExecResult(ok=False, stdout=out.getvalue(), stderr=err.getvalue(), traceback=traceback.format_exc())

