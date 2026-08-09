"""Pylint linter implementation."""

import json
from pathlib import Path

from sanopy.linters.base import AsyncCompletedProcess, BaseLinter
from sanopy.linters.context import get_linter_context
from sanopy.linters.result import LinterResult


class PylintLinter(BaseLinter):
    """Linter implementation for Pylint."""

    name = "Pylint"

    def build_command(self, target: Path) -> list[str]:
        """Build the Pylint command for the target path.

        Args:
            target: The file or directory to scan.

        Returns:
            A list of command arguments including output format and config.
        """
        # Get effective config (nearest local or bundled default)
        config_file = self._get_effective_config_path(
            target, [".pylintrc", "pylintrc", "pyproject.toml"]
        )

        cmd = ["pylint", "--output-format=json"]
        if config_file:
            # If it's pyproject.toml, it might need different handling,
            # but usually Pylint finds it or we pass it via --rcfile.
            cmd += [f"--rcfile={config_file.absolute()}"]

        return cmd + [str(target.absolute())]

    def parse_output(
        self,
        process_result: AsyncCompletedProcess,
        target: Path,
    ) -> list[LinterResult]:
        """Parse Pylint JSON output.

        Args:
            process_result: The completed process result.
            target: The target that was scanned.

        Returns:
            A list of standardized linter results.
        """

        try:
            errors = json.loads(process_result.stdout) or []
        except json.JSONDecodeError:
            return []

        parsed_results = []
        for error in errors:
            file_path = Path(error.get("path", target.name))

            line_start = error.get("line", 1)
            col_start = error.get("column", 1)
            line_end = error.get("endLine")
            col_end = error.get("endColumn")

            error_code = error.get(
                "message-id", error.get("symbol", "Unknown")
            )
            message = error.get("message", "Unknown error")

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
