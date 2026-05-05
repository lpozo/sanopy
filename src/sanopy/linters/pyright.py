"""Pyright linter implementation for static type checking."""

import json
from pathlib import Path

from sanopy.linters.base import AsyncCompletedProcess, BaseLinter
from sanopy.linters.context import get_linter_context
from sanopy.linters.result import LinterResult


class PyrightLinter(BaseLinter):
    """Linter implementation for Pyright."""

    name = "Pyright"

    def build_command(self, target: Path) -> list[str]:
        """Build the Pyright command for the target path.

        Args:
            target: The file or directory to scan.

        Returns:
            A list of command arguments.
        """
        return ["pyright", "--outputjson", str(target.absolute())]

    def parse_output(
        self,
        process_result: AsyncCompletedProcess,
        target: Path,
    ) -> list[LinterResult]:
        """Parse Pyright JSON output.

        Args:
            process_result: The completed process result.
            target: The target that was scanned.

        Returns:
            A list of standardized linter results.
        """

        try:
            data = json.loads(process_result.stdout)
            diagnostics = data.get("generalDiagnostics", [])
        except json.JSONDecodeError:
            return []

        parsed_results = []
        for diag in diagnostics:
            file_path = Path(diag.get("file", str(target)))

            # Pyright is 0-indexed, normalizing to 1-indexed for LinterResult
            line_start = (
                diag.get("range", {}).get("start", {}).get("line", 0) + 1
            )
            col_start = (
                diag.get("range", {}).get("start", {}).get("character", 0) + 1
            )
            line_end = diag.get("range", {}).get("end", {}).get("line", 0) + 1
            col_end = (
                diag.get("range", {}).get("end", {}).get("character", 0) + 1
            )

            error_code = diag.get("rule", "Unknown")
            severity = diag.get("severity", "error").upper()
            message = f"[{severity}] {diag.get('message', 'No message')}"

            raw_snippet, snippet_start, semantic_info = get_linter_context(
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                context_lines=10,
            )

            parsed_results.append(
                LinterResult(
                    file_path=file_path,
                    line_start=line_start,
                    line_end=line_end,
                    col_start=col_start,
                    col_end=col_end,
                    linter_name=self.name,
                    error_code=error_code,
                    message=message,
                    snippet_context=raw_snippet,
                    snippet_start_line=snippet_start,
                    semantic_context=semantic_info,
                )
            )

        return parsed_results
