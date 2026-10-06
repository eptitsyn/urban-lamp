from pathlib import Path
from tempfile import NamedTemporaryFile


def read_utf8(path: Path) -> str:
    # No universal-newline translation: every offset uses the original text.
    return path.read_bytes().decode("utf-8")


def write_utf8_atomic(path: Path, payload: str) -> None:
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload + "\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
