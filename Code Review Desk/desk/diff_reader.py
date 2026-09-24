import asyncio
from dataclasses import dataclass


@dataclass
class DiffError:
    message: str


@dataclass
class FileChunk:
    file: str
    content: str


async def read_diff(path: str) -> str | DiffError:
    try:
        def _read() -> str:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()

        content = await asyncio.to_thread(_read)
    except FileNotFoundError:
        return DiffError(f"Diff file not found: {path}")
    except OSError as e:
        return DiffError(f"Cannot read diff file: {e}")

    if not content.strip():
        return DiffError("Diff file is empty.")

    if "diff --git" not in content and "---" not in content:
        return DiffError("Malformed diff: no unified diff headers found.")

    return content


def split_by_file(diff_text: str) -> list[FileChunk] | DiffError:
    if not diff_text.strip():
        return DiffError("Cannot split an empty diff.")

    lines = diff_text.splitlines(keepends=True)
    chunks: list[FileChunk] = []
    current_file: str | None = None
    current_lines: list[str] = []

    def _flush() -> None:
        if current_file is not None:
            chunks.append(FileChunk(file=current_file, content="".join(current_lines)))

    for line in lines:
        if line.startswith("diff --git"):
            _flush()
            parts = line.strip().split()
            current_file = parts[-1].removeprefix("b/") if len(parts) >= 4 else "unknown"
            current_lines = [line]
        elif current_file is not None:
            current_lines.append(line)
        elif line.startswith("---"):
            _flush()
            current_file = line.split("\t")[0].removeprefix("--- ").removeprefix("a/") or "unknown"
            current_lines = [line]
        elif current_file is None and line.startswith("+++"):
            continue
        else:
            if current_file is None:
                current_file = "unknown"
                current_lines = [line]
            else:
                current_lines.append(line)

    _flush()

    if not chunks:
        return DiffError("Malformed diff: no per-file sections detected.")

    return chunks
