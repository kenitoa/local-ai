from pathlib import Path


SECRETS_DIR = Path("/run/secrets")


def read_secret(name: str) -> str | None:
    path = SECRETS_DIR / name
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        return value or None
    return None


def has_secret(name: str) -> bool:
    return read_secret(name) is not None
