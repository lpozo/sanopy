"""Tests for the Linter Engine Orchestrator."""

from pathlib import Path

import pytest

from sanopy.linters import BaseLinter, Engine
from sanopy.linters.result import LinterResult


class MockLinter(BaseLinter):
    """A mock linter that returns predefined results or raises.

    ``package_name`` is ``echo`` so the linter really resolves and spawns
    a harmless process; ``build_command`` puts ``echo`` first to match.
    """

    name = "MockLinter"
    package_name = "echo"
    module_name: str | None = None

    def __init__(
        self,
        name: str,
        return_list: list[LinterResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        super().__init__()
        self.name = name
        self._returns = return_list or []
        self._error = error

    def build_command(self, target: Path) -> list[str]:
        return ["echo", str(target)]

    def parse_output(self, process_result, target: Path) -> list[LinterResult]:
        if self._error:
            raise self._error
        return self._returns


def _results(name: str, count: int) -> list[LinterResult]:
    """Build ``count`` LinterResults for a given linter name."""
    return [
        LinterResult(
            Path(f"{name}{i}.py"),
            i,
            None,
            None,
            None,
            name,
            "E1",
            f"Msg {i}",
            "",
        )
        for i in range(count)
    ]


@pytest.mark.parametrize(
    "linter_specs, expected_count",
    [
        # Multiple linters with varying result counts
        ([("L1", 1), ("L2", 2)], 3),
        # A linter that returns no results
        ([("L1", 1), ("L2", 0)], 1),
        # No linters configured
        ([], 0),
        # A single linter with many results
        ([("A", 3)], 3),
    ],
)
@pytest.mark.asyncio
async def test_engine_combines_results(
    linter_specs: list[tuple[str, int]], expected_count: int
) -> None:
    """Test that the engine merges results from multiple linters."""
    linters: list[BaseLinter] = [
        MockLinter(name, _results(name, count)) for name, count in linter_specs
    ]

    results = await Engine(linters=linters).run_all(Path())

    assert len(results) == expected_count
    assert {r.linter_name for r in results} == {
        name for name, count in linter_specs if count > 0
    }


@pytest.mark.parametrize(
    "counts, failing_index, expected_count",
    [
        # First linter fails
        ([1, 2, 3], 0, 5),
        # Middle linter fails
        ([1, 2, 3], 1, 4),
        # Last linter fails
        ([1, 2, 3], 2, 3),
        # Only linter fails
        ([1], 0, 0),
    ],
)
@pytest.mark.asyncio
async def test_engine_isolates_failures(
    counts: list[int], failing_index: int, expected_count: int
) -> None:
    """Test that a failing linter does not discard other linters' results."""
    linters: list[BaseLinter] = []
    for idx, count in enumerate(counts):
        if idx == failing_index:
            linters.append(MockLinter(f"L{idx}", error=RuntimeError("boom")))
        else:
            linters.append(MockLinter(f"L{idx}", _results(f"L{idx}", count)))

    results = await Engine(linters=linters).run_all(Path())

    assert len(results) == expected_count
    assert all(r.linter_name != f"L{failing_index}" for r in results)


@pytest.mark.parametrize(
    "linter_count, failing_count",
    [
        (0, 0),
        (1, 0),
        (3, 0),
        (3, 1),
    ],
)
@pytest.mark.asyncio
async def test_engine_progress_callback(
    linter_count: int, failing_count: int
) -> None:
    """Test that the progress callback fires once per linter task."""
    linters: list[BaseLinter] = []
    for idx in range(linter_count):
        if idx < failing_count:
            linters.append(MockLinter(f"L{idx}", error=RuntimeError("boom")))
        else:
            linters.append(MockLinter(f"L{idx}", _results(f"L{idx}", 1)))

    calls: list[int] = []

    def callback() -> None:
        calls.append(1)

    await Engine(linters=linters).run_all(Path(), progress_callback=callback)

    assert len(calls) == linter_count


@pytest.mark.parametrize(
    "failing_names, expected_survivors",
    [
        pytest.param([], {"L0", "L1"}, id="none-fail"),
        pytest.param(["L0"], {"L1"}, id="first-fails"),
        pytest.param(["L1"], {"L0"}, id="second-fails"),
        pytest.param(["L0", "L1"], set(), id="all-fail"),
    ],
)
@pytest.mark.asyncio
async def test_engine_reports_failures_without_losing_results(
    failing_names: list[str], expected_survivors: set[str], capsys
) -> None:
    """A failing linter is reported on stderr and does not stop the others.

    Diagnostics must not go to stdout, which carries the JSON document in
    machine mode.
    """
    linters: list[BaseLinter] = [
        MockLinter(name, error=RuntimeError(f"boom {name}"))
        if name in failing_names
        else MockLinter(name, _results(name, 1))
        for name in ("L0", "L1")
    ]

    results = await Engine(linters=linters).run_all(Path())

    assert {r.linter_name for r in results} == expected_survivors
    captured = capsys.readouterr()
    assert captured.out == ""
    for name in failing_names:
        assert f"boom {name}" in captured.err
