from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


@dataclass
class StoryRequest:
    image_paths: list[Path]
    sentiment: str
    language: str = "한국어"
    story_length: str = "짧게"

    def validate(self) -> None:
        if not self.image_paths:
            raise ValueError("최소 1개 이상의 이미지를 선택해야 합니다.")

        invalid_files = [path.name for path in self.image_paths if path.suffix.lower() not in SUPPORTED_EXTENSIONS]
        if invalid_files:
            raise ValueError(
                "지원하지 않는 이미지 형식이 포함되어 있습니다: " + ", ".join(invalid_files)
            )

        if not self.sentiment.strip():
            raise ValueError("이야기 감정을 선택해야 합니다.")


@dataclass
class StoryResult:
    story_text: str
    used_model: str
    image_count: int
    sentiment: str
