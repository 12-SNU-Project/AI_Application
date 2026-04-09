from __future__ import annotations

import base64
import json
import math
import mimetypes
from pathlib import Path

from openai import OpenAI

from .image_search_models import (
    DEFAULT_INDEX_PATH,
    ImageSearchEntry,
    ImageSearchIndex,
    SearchResult,
    SUPPORTED_IMAGE_EXTENSIONS,
)


DEFAULT_CAPTION_MODEL = "gpt-4.1-mini"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


class SemanticImageSearchService:
    def __init__(
        self,
        client: OpenAI,
        caption_model: str = DEFAULT_CAPTION_MODEL,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        self.client = client
        self.caption_model = caption_model
        self.embedding_model = embedding_model

    def discover_images_in_directory(self, directory: Path) -> list[Path]:
        if not directory.exists() or not directory.is_dir():
            raise ValueError(f"유효한 이미지 폴더가 아닙니다: {directory}")

        images = [
            path
            for path in sorted(directory.iterdir())
            if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
        ]
        return images

    def normalize_image_paths(self, image_paths: list[Path]) -> list[Path]:
        normalized: list[Path] = []
        seen: set[Path] = set()

        for raw_path in image_paths:
            resolved = raw_path.expanduser().resolve()
            if resolved in seen:
                continue
            if not resolved.exists():
                raise ValueError(f"이미지 파일을 찾을 수 없습니다: {resolved}")
            if resolved.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
                raise ValueError(f"지원하지 않는 이미지 형식입니다: {resolved.name}")
            seen.add(resolved)
            normalized.append(resolved)

        if not normalized:
            raise ValueError("최소 1개 이상의 이미지를 선택해야 합니다.")

        return normalized

    def build_and_save_index(
        self,
        image_paths: list[Path],
        index_path: Path = DEFAULT_INDEX_PATH,
    ) -> ImageSearchIndex:
        index = self.build_index(image_paths)
        self.save_index(index, index_path)
        return index

    def build_index(self, image_paths: list[Path]) -> ImageSearchIndex:
        normalized_paths = self.normalize_image_paths(image_paths)
        captions = [self.generate_caption(image_path) for image_path in normalized_paths]
        embeddings = self._embed_texts(captions)

        entries = [
            ImageSearchEntry(
                image_path=str(image_path),
                file_name=image_path.name,
                caption=caption,
                embedding=embedding,
            )
            for image_path, caption, embedding in zip(normalized_paths, captions, embeddings)
        ]

        return ImageSearchIndex(
            entries=entries,
            caption_model=self.caption_model,
            embedding_model=self.embedding_model,
        )

    def search(
        self,
        query: str,
        index: ImageSearchIndex,
        top_k: int = 3,
    ) -> list[SearchResult]:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ValueError("검색어를 입력해야 합니다.")
        if not index.entries:
            raise ValueError("검색할 이미지 인덱스가 비어 있습니다.")

        query_embedding = self._embed_texts([cleaned_query])[0]
        ranked_results = [
            SearchResult(entry=entry, score=self._cosine_similarity(query_embedding, entry.embedding))
            for entry in index.entries
        ]
        ranked_results.sort(key=lambda item: item.score, reverse=True)
        return ranked_results[: max(1, top_k)]

    def save_index(self, index: ImageSearchIndex, index_path: Path = DEFAULT_INDEX_PATH) -> None:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(
            json.dumps(index.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_index(self, index_path: Path = DEFAULT_INDEX_PATH) -> ImageSearchIndex:
        if not index_path.exists():
            raise FileNotFoundError(f"인덱스 파일이 없습니다: {index_path}")

        data = json.loads(index_path.read_text(encoding="utf-8"))
        index = ImageSearchIndex.from_dict(data)
        if not index.entries:
            raise ValueError("인덱스 파일은 존재하지만 이미지 항목이 비어 있습니다.")
        return index

    def generate_caption(self, image_path: Path) -> str:
        response = self.client.responses.create(
            model=self.caption_model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "이 이미지를 텍스트 기반 이미지 검색용으로 설명하세요. "
                                "한국어로만 작성하고, 추측을 줄이며 눈에 보이는 사실 중심으로 설명하세요. "
                                "형식은 다음과 같습니다.\n"
                                "장면: ...\n"
                                "주요 객체: ...\n"
                                "분위기: ...\n"
                                "세부: ...\n"
                                "전체 길이는 120자 안팎이면 충분합니다."
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": self._encode_to_data_url(image_path),
                            "detail": "high",
                        },
                    ],
                }
            ],
        )

        caption = (response.output_text or "").strip()
        if not caption:
            raise RuntimeError(f"이미지 설명 생성에 실패했습니다: {image_path.name}")
        return caption

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=self.embedding_model,
            input=texts,
        )
        return [list(item.embedding) for item in response.data]

    def _encode_to_data_url(self, image_path: Path) -> str:
        mime_type, _ = mimetypes.guess_type(str(image_path))
        if mime_type is None:
            mime_type = "image/jpeg"

        with image_path.open("rb") as file_obj:
            encoded = base64.b64encode(file_obj.read()).decode("utf-8")

        return f"data:{mime_type};base64,{encoded}"

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        numerator = sum(left_value * right_value for left_value, right_value in zip(left, right))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)
