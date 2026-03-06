import abc
from datetime import datetime
from pathlib import Path


class StorageBackend(abc.ABC):
    @abc.abstractmethod
    async def save_file(self, category: str, filename: str, data: bytes) -> str:
        """Save file and return its relative path."""

    @abc.abstractmethod
    async def get_file(self, relative_path: str) -> bytes:
        """Read file by relative path."""

    @abc.abstractmethod
    async def delete_file(self, relative_path: str) -> None:
        """Delete file by relative path."""

    @abc.abstractmethod
    async def get_absolute_path(self, relative_path: str) -> Path:
        """Return the absolute filesystem path for a relative path."""

    @abc.abstractmethod
    async def file_exists(self, relative_path: str) -> bool:
        """Check if file exists."""


class LocalStorage(StorageBackend):
    def __init__(self, base_path: Path):
        self.base_path = base_path

    def _build_path(self, category: str, filename: str) -> tuple[str, Path]:
        month_dir = datetime.utcnow().strftime("%Y-%m")
        relative = f"{category}/{month_dir}/{filename}"
        absolute = self.base_path / relative
        absolute.parent.mkdir(parents=True, exist_ok=True)
        return relative, absolute

    async def save_file(self, category: str, filename: str, data: bytes) -> str:
        relative, absolute = self._build_path(category, filename)
        absolute.write_bytes(data)
        return relative

    async def get_file(self, relative_path: str) -> bytes:
        path = self.base_path / relative_path
        return path.read_bytes()

    async def delete_file(self, relative_path: str) -> None:
        path = self.base_path / relative_path
        if path.exists():
            path.unlink()

    async def get_absolute_path(self, relative_path: str) -> Path:
        return self.base_path / relative_path

    async def file_exists(self, relative_path: str) -> bool:
        return (self.base_path / relative_path).exists()
