"""MyPy linter implementation."""

import re
from pathlib import Path

from sanopy.linters.base import AsyncCompletedProcess, BaseLinter
from sanopy.linters.context import get_linter_context, read_file_content
from sanopy.linters.result import LinterResult


class MyPyLinter(BaseLinter):
    """Linter implementation for MyPy (Static type checker)."""

    name = "MyPy"
    package_name = "mypy"
    module_name = "mypy"

    def build_command(self, target: Path) -> list[str]:
        """Build the MyPy command for the target path.

        Args:
            target: The file or directory to scan.

        Returns:
            A list of command arguments.
        """
        return [
            "mypy",
            "--show-column-numbers",
            "--show-error-codes",
            "--no-error-summary",
            str(target.absolute()),
        ]

    def parse_output(
        self,
        process_result: AsyncCompletedProcess,
        target: Path,
    ) -> list[LinterResult]:
        """Parse MyPy text output.

        Args:
            process_result: The completed process result.
            target: The target that was scanned.

        Returns:
            A list of standardized linter results.
        """

        pattern = re.compile(
            r"^(?P<file>.+?):(?P<line>\d+):(?P<col>\d+):\s*"
            r"(?P<severity>error|warning|note):\s*"
            r"(?P<msg>.+?)\s*\[(?P<code>.+?)\]$"
        )

        parsed_results = []
        content_cache: dict[Path, str | None] = {}
        for line in process_result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue

            match = pattern.match(line)
            if not match:
                continue

            file_path = Path(match.group("file"))
            if file_path not in content_cache:
                content_cache[file_path] = read_file_content(file_path)

            line_start = int(match.group("line"))
            col_start = int(match.group("col"))
            message = match.group("msg")
            error_code = match.group("code")
            severity = match.group("severity")

            raw_snippet, snippet_start, semantic_info = get_linter_context(
                file_path=file_path,
                line_start=line_start,
                line_end=line_start,
                context_lines=10,
                content=content_cache[file_path],
            )

            parsed_results.append(
                LinterResult(
                    file_path=file_path,
                    line_start=line_start,
                    line_end=line_start,
                    col_start=col_start,
                    col_end=None,
                    linter_name=self.name,
                    error_code=error_code,
                    message=message,
                    raw_severity=severity,
                    snippet_context=raw_snippet,
                    snippet_start_line=snippet_start,
                    semantic_context=semantic_info,
                )
            )

        return parsed_results
