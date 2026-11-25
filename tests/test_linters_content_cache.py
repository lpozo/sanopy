"""Cross-linter tests for per-file content caching in parse_output.

The per-linter suites cover parsing; this module covers the shared
contract that every context-using linter reads, parses, and indexes each
file at most once per parse, reusing it for every finding in the file.
"""

import json
from pathlib import Path

import pytest

from sanopy.linters import LINTER_MAP
from sanopy.linters.base import AsyncCompletedProcess
from sanopy.linters.context import get_linter_context

CONTENT = "x = 1\n"


def _bandit_stdout(mod: Path) -> str:
    def finding(msg: str) -> dict[str, object]:
        return {
            "filename": str(mod),
            "line_number": 1,
            "line_range": [1],
            "test_id": "B101",
            "issue_text": msg,
            "issue_severity": "LOW",
        }

    return json.dumps({"results": [finding("msg1"), finding("msg2")]})


def _mypy_stdout(mod: Path) -> str:
    return (
        f"{mod}:1:1: error: msg1 [attr-defined]\n"
        f"{mod}:1:1: error: msg2 [attr-defined]\n"
    )


def _pylint_stdout(mod: Path) -> str:
    def finding(msg: str) -> dict[str, object]:
        return {
            "line": 1,
            "column": 1,
            "path": str(mod),
            "message": msg,
            "message-id": "E0001",
        }

    return json.dumps([finding("msg1"), finding("msg2")])


def _pyright_stdout(mod: Path) -> str:
    def finding(msg: str) -> dict[str, object]:
        return {
            "file": str(mod),
            "range": {
                "start": {"line": 0, "character": 0},
                "end": {"line": 0, "character": 1},
            },
            "rule": "reportArgumentType",
            "severity": "error",
            "message": msg,
        }

    return json.dumps(
        {"generalDiagnostics": [finding("msg1"), finding("msg2")]}
    )


def _radon_stdout(mod: Path) -> str:
    def block(name: str) -> dict[str, object]:
        return {
            "type": "function",
            "name": name,
            "classname": "",
            "complexity": 10,
            "rank": "D",
            "lineno": 1,
            "endline": 1,
        }

    return json.dumps({str(mod): [block("f1"), block("f2")]})


def _ruff_stdout(mod: Path) -> str:
    def finding(msg: str) -> dict[str, object]:
        return {
            "code": "E501",
            "message": msg,
            "filename": str(mod),
            "location": {"row": 1, "column": 1},
        }

    return json.dumps([finding("msg1"), finding("msg2")])


def _semgrep_stdout(mod: Path) -> str:
    def finding(msg: str) -> dict[str, object]:
        return {
            "path": str(mod),
            "start": {"line": 1, "col": 1},
            "end": {"line": 1, "col": 2},
            "check_id": "python.lang.security.audit.eval-used",
            "extra": {"severity": "WARNING", "message": msg},
        }

    return json.dumps({"results": [finding("msg1"), finding("msg2")]})


def _vulture_stdout(mod: Path) -> str:
    return f"{mod}:1: unused variable 'a' (msg1)\n{mod}:1: unused 'b' (msg2)\n"


@pytest.mark.parametrize(
    "linter_name, make_stdout",
    [
        pytest.param("bandit", _bandit_stdout, id="bandit"),
        pytest.param("mypy", _mypy_stdout, id="mypy"),
        pytest.param("pylint", _pylint_stdout, id="pylint"),
        pytest.param("pyright", _pyright_stdout, id="pyright"),
        pytest.param("radon", _radon_stdout, id="radon"),
        pytest.param("ruff", _ruff_stdout, id="ruff"),
        pytest.param("semgrep", _semgrep_stdout, id="semgrep"),
        pytest.param("vulture", _vulture_stdout, id="vulture"),
    ],
)
@pytest.mark.asyncio
async def test_linter_reuses_content_per_file(
    mocker, tmp_path, linter_name: str, make_stdout
) -> None:
    """Every finding in a file reuses one read of that file's content."""
    linter_cls = LINTER_MAP[linter_name]
    linter = linter_cls()
    src = tmp_path / "target"
    src.mkdir()
    mod = src / "mod.py"
    mod.write_text(CONTENT, encoding="utf-8")

    mock_result = AsyncCompletedProcess(
        stdout=make_stdout(mod), stderr="", returncode=0
    )
    mocker.patch.object(linter_cls, "_run_command", return_value=mock_result)

    caches: list[object] = []

    def _capture(**kwargs):
        caches.append(kwargs.get("cache"))
        return ("snippet", 1, "context")

    module = linter_cls.__module__.rsplit(".", 1)[-1]
    mocker.patch(
        f"sanopy.linters.{module}.get_linter_context",
        side_effect=_capture,
    )

    results = await linter.run(src)

    assert len(results) == 2
    assert caches[0] is not None
    assert caches[0] is caches[1]


@pytest.mark.asyncio
async def test_unreadable_file_is_read_once_and_cached(
    mocker, tmp_path
) -> None:
    """An unreadable file is attempted once, not once per finding.

    The cache remembers the failed read (None), which get_linter_context
    treats as "known unreadable" rather than "content not supplied".
    """
    linter = LINTER_MAP["ruff"]()
    src = tmp_path / "target"
    src.mkdir()
    binary = src / "mod.bin"
    binary.write_bytes(b"\xff\xfe\xfd")

    stdout = json.dumps(
        [
            {
                "code": "E501",
                "message": "odd",
                "filename": str(binary),
                "location": {"row": 1, "column": 1},
            },
            {
                "code": "E501",
                "message": "odd again",
                "filename": str(binary),
                "location": {"row": 1, "column": 1},
            },
        ]
    )
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(type(linter), "_run_command", return_value=mock_result)
    mocker.patch(
        "sanopy.linters.ruff.get_linter_context",
        side_effect=get_linter_context,
    )

    read_calls: list[str] = []
    real_read = Path.read_text

    def _tracked_read(self: Path, *args, **kwargs):
        read_calls.append(str(self))
        return real_read(self, *args, **kwargs)

    mocker.patch.object(Path, "read_text", _tracked_read)

    results = await linter.run(src)

    assert len(results) == 2
    assert all(r.snippet_context == "" for r in results)
    # One attempted read for the binary file, not one per finding.
    assert read_calls.count(str(binary)) == 1
