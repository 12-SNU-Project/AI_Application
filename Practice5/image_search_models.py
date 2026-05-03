from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from project_paths import IMAGE_SEARCH_INDEX_PATH


SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
DEFAULT_INDEX_PATH = IMAGE_SEARCH_INDEX_PATH


@dataclass
class ImageSearchEntry:
    image_path: str
    file_name: str
    caption: str
    embedding: list[float]

    @property
    def path(self) -> Path:
        return Path(self.image_path)

    def to_dict(self) -> dict:
        return {
            "image_path": self.image_path,
            "file_name": self.file_name,
            "caption": self.caption,
            "embedding": self.embedding,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ImageSearchEntry":
        return cls(
            image_path=str(data["image_path"]),
            file_name=str(data["file_name"]),
            caption=str(data["caption"]),
            embedding=[float(value) for value in data["embedding"]],
        )


@dataclass
class ImageSearchIndex:
    entries: list[ImageSearchEntry]
    caption_model: str
    embedding_model: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "entries": [entry.to_dict() for entry in self.entries],
            "caption_model": self.caption_model,
            "embedding_model": self.embedding_model,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ImageSearchIndex":
        return cls(
            entries=[ImageSearchEntry.from_dict(item) for item in data.get("entries", [])],
            caption_model=str(data.get("caption_model", "")),
            embedding_model=str(data.get("embedding_model", "")),
            created_at=str(data.get("created_at", "")),
        )


@dataclass
class SearchResult:
    entry: ImageSearchEntry
    score: float
