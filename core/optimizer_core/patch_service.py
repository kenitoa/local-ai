from __future__ import annotations

import difflib


class PatchService:
    def create_patch(
        self,
        original: str,
        updated: str,
        source_path: str = "uploaded.py",
    ) -> str:
        if original == updated:
            return ""
        diff = list(
            difflib.unified_diff(
                original.splitlines(),
                updated.splitlines(),
                fromfile=f"a/{source_path}",
                tofile=f"b/{source_path}",
                lineterm="",
            )
        )
        return "\n".join(diff) + "\n"

    def is_unified_diff(self, patch: str) -> bool:
        lines = patch.splitlines()
        return bool(lines) and any(line.startswith("--- ") for line in lines) and any(
            line.startswith("@@") for line in lines
        )

    def apply_patch(self, original: str, patch: str) -> str | None:
        if not self.is_unified_diff(patch):
            return None
        original_lines = original.splitlines()
        patched: list[str] = []
        original_index = 0
        lines = patch.splitlines()
        index = 0
        while index < len(lines):
            line = lines[index]
            if line.startswith(("--- ", "+++ ")):
                index += 1
                continue
            if not line.startswith("@@"):
                index += 1
                continue
            old_start = parse_hunk_start(line)
            if old_start is None:
                return None
            hunk_start = old_start - 1
            if hunk_start < original_index:
                return None
            patched.extend(original_lines[original_index:hunk_start])
            original_index = hunk_start
            index += 1
            while index < len(lines) and not lines[index].startswith("@@"):
                hunk_line = lines[index]
                if hunk_line.startswith(" "):
                    text = hunk_line[1:]
                    if original_index >= len(original_lines) or original_lines[original_index] != text:
                        return None
                    patched.append(text)
                    original_index += 1
                elif hunk_line.startswith("-"):
                    text = hunk_line[1:]
                    if original_index >= len(original_lines) or original_lines[original_index] != text:
                        return None
                    original_index += 1
                elif hunk_line.startswith("+"):
                    patched.append(hunk_line[1:])
                elif hunk_line.startswith("\\"):
                    pass
                else:
                    return None
                index += 1
        patched.extend(original_lines[original_index:])
        return "\n".join(patched) + ("\n" if original.endswith("\n") else "")

    def fallback_python_patch(self, original: str, source_path: str = "uploaded.py") -> str:
        updated = original
        updated = updated.replace("result = result + ", "result += ")
        updated = updated.replace("total = total + ", "total += ")
        updated = updated.replace("count = count + 1", "count += 1")
        return self.create_patch(original, updated, source_path)


def parse_hunk_start(header: str) -> int | None:
    try:
        old_range = header.split(" ", 2)[1]
        return int(old_range.removeprefix("-").split(",", 1)[0])
    except (IndexError, ValueError):
        return None
