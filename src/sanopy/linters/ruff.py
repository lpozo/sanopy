"""Linter implementation for Ruff."""

import json
from pathlib import Path

from sanopy.linters.base import AsyncCompletedProcess, BaseLinter
from sanopy.linters.context import get_linter_context
from sanopy.linters.result import LinterResult


class RuffLinter(BaseLinter):
    """Linter implementation for Ruff."""

    name = "Ruff"
    package_name = "ruff"
    module_name = "ruff"

    def build_command(self, target: Path) -> list[str]:
        """Build the Ruff command for the target path.

        Args:
            target: The file or directory to scan.

        Returns:
            A list of command arguments including output format and config.
        """
        # Get effective config (nearest local or bundled default)
        config_file = self._get_effective_config_path(
            target, ["pyproject.toml", "ruff.toml", ".ruff.toml"]
        )

        cmd = ["ruff", "check", "--output-format=json"]
        if config_file:
            cmd += ["--config", str(config_file.absolute())]

        return cmd + [str(target.absolute())]

    def parse_output(
        self,
        process_result: AsyncCompletedProcess,
        target: Path,
    ) -> list[LinterResult]:
        """Parse Ruff JSON output.

        Args:
            process_result: The completed process result.
            target: The target that was scanned.

        Returns:
            A list of standardized linter results.
        """
        # pylint: disable=too-many-locals

        try:
            errors = json.loads(process_result.stdout) or []
        except json.JSONDecodeError:
            return []

        parsed_results = []
        for error in errors:
            file_path = Path(error.get("filename", ""))

            line_start = error.get("location", {}).get("row", 1)
            col_start = error.get("location", {}).get("column", 1)
            line_end = error.get("end_location", {}).get("row")
            col_end = error.get("end_location", {}).get("column")

            error_code = error.get("code", "Unknown")
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
