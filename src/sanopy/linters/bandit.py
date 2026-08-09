"""Bandit linter implementation."""

import json
from pathlib import Path

from sanopy.linters.base import AsyncCompletedProcess, BaseLinter
from sanopy.linters.context import get_linter_context
from sanopy.linters.result import LinterResult


class BanditLinter(BaseLinter):
    """Linter implementation for Bandit (Security scanner)."""

    name = "Bandit"

    def build_command(self, target: Path) -> list[str]:
        """Build the Bandit command for the target path.

        Args:
            target: The file or directory to scan.

        Returns:
            A list of command arguments including format flags and config.
        """
        target_str = str(target.absolute())
        args = ["-r", target_str] if target.is_dir() else [target_str]

        # Get effective config (nearest local or bundled default)
        config_file = self._get_effective_config_path(
            target, ["bandit.yaml", ".bandit", "pyproject.toml"]
        )

        cmd = ["bandit", "-f", "json"]
        if config_file:
            cmd += ["-c", str(config_file.absolute())]

        return cmd + args

    def parse_output(
        self,
        process_result: AsyncCompletedProcess,
        target: Path,
    ) -> list[LinterResult]:
        """Parse Bandit JSON output.

        Args:
            process_result: The completed process result.
            target: The target that was scanned.

        Returns:
            A list of standardized linter results.
        """

        try:
            output = json.loads(process_result.stdout)
            errors = output.get("results") or []
        except json.JSONDecodeError:
            return []

        parsed_results = []
        for error in errors:
            file_path = Path(error.get("filename", target.name))

            line_start = error.get("line_number", 1)
            line_range = error.get("line_range", [])
            line_end = max(line_range) if line_range else line_start

            error_code = error.get("test_id", "Unknown")
            issue_text = error.get("issue_text", "Unknown security issue")
            severity = error.get("issue_severity", "LOW")
            message = f"[{severity}] {issue_text}"

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
                    col_start=None,
                    col_end=None,
                    linter_name=self.name,
                    error_code=error_code,
                    message=message,
                    snippet_context=raw_snippet,
                    snippet_start_line=snippet_start,
                    semantic_context=semantic_info,
                )
            )

        return parsed_results
