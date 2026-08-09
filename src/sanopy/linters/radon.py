"""Radon linter implementation for cyclomatic complexity analysis."""

import json
from pathlib import Path

from sanopy.linters.base import AsyncCompletedProcess, BaseLinter
from sanopy.linters.context import get_linter_context
from sanopy.linters.result import LinterResult

MIN_COMPLEXITY_RANK = "C"


class RadonLinter(BaseLinter):
    """Linter implementation for Radon (Cyclomatic Complexity)."""

    name = "Radon"

    def build_command(self, target: Path) -> list[str]:
        """Build the Radon command for the target path.

        Args:
            target: The file or directory to scan.

        Returns:
            A list of command arguments.
        """
        return [
            "radon",
            "cc",
            "-j",
            "-n",
            MIN_COMPLEXITY_RANK,
            str(target.absolute()),
        ]

    def parse_output(
        self,
        process_result: AsyncCompletedProcess,
        target: Path,
    ) -> list[LinterResult]:
        """Parse Radon JSON output.

        Args:
            process_result: The completed process result.
            target: The target that was scanned.

        Returns:
            A list of standardized linter results.
        """
        try:
            data = json.loads(process_result.stdout)
        except json.JSONDecodeError:
            return []

        parsed_results = []
        for file_path_str, blocks in data.items():
            file_path = Path(file_path_str)

            for block in blocks or []:
                block_type = block.get("type", "function")
                block_name = block.get("name", "unknown")
                classname = block.get("classname", "")
                complexity = block.get("complexity", 0)
                rank = block.get("rank", "A")
                line_start = block.get("lineno", 1)
                line_end = block.get("endline", line_start)

                qualified_name = (
                    f"{classname}.{block_name}" if classname else block_name
                )
                message = (
                    f"{block_type.capitalize()} '{qualified_name}' has "
                    f"complexity {complexity} (rank {rank})"
                )

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
                        error_code=f"CC-{rank}",
                        message=message,
                        snippet_context=raw_snippet,
                        snippet_start_line=snippet_start,
                        semantic_context=semantic_info,
                    )
                )

        return parsed_results
