"""Opt-in bridge to selected host-language modules.

Everything in this file is explicitly FOREIGN: it is not llang-native, it is
allowlisted, and values cross the boundary as ordinary Python numbers, texts,
lists and maps. Programs using it are marked by `use the foreign <name> module`.

The `shell` module is the most powerful entry here. It is opt-in for the same
reason: no llang program can execute a host command unless it explicitly says
`use the foreign shell module`. Every call takes the command as visible text,
captures stdout/stderr, enforces a timeout, and returns a map; nothing runs
implicitly, and there is no host-object leakage.
"""

import json as _json
import math as _math
import os as _os
import subprocess as _subprocess


def _unary(fn):
    def call(**kwargs):
        return fn(kwargs["value"])
    return call


def _json_dumps(**kwargs):
    return _json.dumps(kwargs["value"], ensure_ascii=False)


def _json_loads(**kwargs):
    return _json.loads(kwargs["text"])


def _shell_run(command, directory=None, timeout=30):
    if not isinstance(command, str):
        raise ValueError("run command requires a text command")
    if directory is not None and not isinstance(directory, str):
        raise ValueError("directory must be text")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        raise ValueError("timeout must be a number")
    options = {
        "shell": True,
        "capture_output": True,
        "text": True,
        "timeout": timeout,
    }
    if directory is not None:
        options["cwd"] = directory
    try:
        process = _subprocess.run(command, **options)
    except _subprocess.TimeoutExpired:
        raise ValueError(f"command timed out after {timeout} seconds: {command}")
    except OSError as exc:
        raise ValueError(f"could not run command: {exc}")
    return {
        "command": command,
        "code": process.returncode,
        "output": process.stdout,
        "error": process.stderr,
    }


def _shell_output(**kwargs):
    result = _shell_run(
        kwargs["command"], kwargs.get("directory"), kwargs.get("timeout", 30))
    if result["code"] != 0:
        detail = result["error"] or result["output"] or "no detail"
        raise ValueError(
            f"command failed with code {result['code']}: {detail.strip()}")
    return result["output"]


def _shell_succeeds(**kwargs):
    result = _shell_run(
        kwargs["command"], kwargs.get("directory"), kwargs.get("timeout", 30))
    return result["code"] == 0


def _environment_value(**kwargs):
    name = kwargs["name"]
    if not isinstance(name, str):
        raise ValueError("environment variable name must be text")
    return _os.environ.get(name, kwargs.get("default"))


# module -> {name: (callable, required labels, optional labels)}
FOREIGN_FUNCTIONS = {
    "math": {
        "sqrt": (_unary(_math.sqrt), ("value",), ()),
        "sin": (_unary(_math.sin), ("value",), ()),
        "cos": (_unary(_math.cos), ("value",), ()),
        "tan": (_unary(_math.tan), ("value",), ()),
        "log": (_unary(_math.log), ("value",), ()),
        "floor": (_unary(_math.floor), ("value",), ()),
        "ceil": (_unary(_math.ceil), ("value",), ()),
        "absolute": (_unary(abs), ("value",), ()),
    },
    "json": {
        "dumps": (_json_dumps, ("value",), ()),
        "loads": (_json_loads, ("text",), ()),
    },
    "shell": {
        "run command": (_shell_run, ("command",), ("directory", "timeout")),
        "output of command": (_shell_output, ("command",), ("directory", "timeout")),
        "command succeeds": (_shell_succeeds, ("command",), ("directory", "timeout")),
        "environment value": (_environment_value, ("name",), ("default",)),
    },
}

FOREIGN_CONSTANTS = {
    "math": {"pi": _math.pi, "e": _math.e},
}
