"""Vulture linter implementation for finding dead code."""

import re
from pathlib import Path

from sanopy.linters.base import AsyncCompletedProcess, BaseLinter
from sanopy.linters.context import get_linter_context
from sanopy.linters.result import LinterResult


class VultureLinter(BaseLinter):
    """Linter implementation for Vulture."""

    name = "Vulture"

    def build_command(self, target: Path) -> list[str]:
        """Build the Vulture command for the target path.

        Args:
            target: The file or directory to scan.

        Returns:
            A list of command arguments.
        """
        return ["vulture", str(target.absolute())]

    def parse_output(
        self, process_result: AsyncCompletedProcess, target: Path
    ) -> list[LinterResult]:
        """Parse Vulture text output.

        Args:
            process_result: The completed process result.
            target: The target that was scanned.

        Returns:
            A list of standardized linter results.
        """

        # Regex for Vulture output: filename:lineno: message
        pattern = re.compile(r"^(?P<file>.+?):(?P<line>\d+):\s*(?P<msg>.+)$")

        parsed_results = []
        for line in process_result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue

            match = pattern.match(line)
            if not match:
                continue

            file_path = Path(match.group("file"))
            line_start = int(match.group("line"))
            message = match.group("msg")

            raw_snippet, snippet_start, semantic_info = get_linter_context(
                file_path=file_path,
                line_start=line_start,
                line_end=line_start,
                context_lines=10,
            )

            parsed_results.append(
                LinterResult(
                    file_path=file_path,
                    line_start=line_start,
                    line_end=line_start,
                    col_start=None,
                    col_end=None,
                    linter_name=self.name,
                    error_code="unused-code",
                    message=message,
                    snippet_context=raw_snippet,
                    snippet_start_line=snippet_start,
                    semantic_context=semantic_info,
                )
            )

        return parsed_results
