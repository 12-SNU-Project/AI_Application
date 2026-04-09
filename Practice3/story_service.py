from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from openai import OpenAI

from .story_models import StoryRequest, StoryResult


DEFAULT_STORY_MODEL = "gpt-4.1-mini"


class ImageEncoder:
    @staticmethod
    def encode_to_data_url(image_path: Path) -> str:
        mime_type, _ = mimetypes.guess_type(str(image_path))
        if mime_type is None:
            mime_type = "image/jpeg"

        with image_path.open("rb") as file_obj:
            base64_image = base64.b64encode(file_obj.read()).decode("utf-8")

        return f"data:{mime_type};base64,{base64_image}"


class StoryPromptBuilder:
    def build_input(self, request: StoryRequest) -> list[dict]:
        content = [
            {
                "type": "input_text",
                "text": self._build_instruction(request),
            }
        ]

        for index, image_path in enumerate(request.image_paths, start=1):
            content.append(
                {
                    "type": "input_text",
                    "text": f"다음은 {index}번째 그림입니다. 이 순서를 유지해서 이야기를 구성하세요.",
                }
            )
            content.append(
                {
                    "type": "input_image",
                    "image_url": ImageEncoder.encode_to_data_url(image_path),
                    "detail": "high",
                }
            )

        return [{"role": "user", "content": content}]

    @staticmethod
    def _build_instruction(request: StoryRequest) -> str:
        return f"""
당신은 그림 여러 장을 보고 하나의 짧은 이야기를 만드는 스토리텔러입니다.

요구사항:
1. 반드시 입력된 그림의 순서를 따라 사건이 진행되어야 합니다.
2. 전체 분위기는 '{request.sentiment}' 감정을 강하게 반영해야 합니다.
3. 출력 언어는 {request.language}로 작성하세요.
4. 분량은 {request.story_length} 작성하세요. 대략 5~8문장 내외면 충분합니다.
5. 각 그림의 장면이 자연스럽게 이어지도록 연결 문장을 넣으세요.
6. 단순 나열이 아니라 하나의 작은 서사처럼 작성하세요.
7. 마지막에는 이야기 전체를 한 줄로 요약한 '한줄 요약:'을 추가하세요.

출력 형식:
[이야기]
(여기에 최종 이야기)

한줄 요약: ...
""".strip()


class StoryGenerator:
    def __init__(self, client: OpenAI, model: str = DEFAULT_STORY_MODEL) -> None:
        self.client = client
        self.model = model

    def generate(self, request: StoryRequest) -> StoryResult:
        request.validate()
        response = self.client.responses.create(
            model=self.model,
            input=StoryPromptBuilder().build_input(request),
        )

        story_text = (response.output_text or "").strip()
        if not story_text:
            raise RuntimeError("모델이 빈 응답을 반환했습니다.")

        return StoryResult(
            story_text=story_text,
            used_model=self.model,
            image_count=len(request.image_paths),
            sentiment=request.sentiment,
        )
