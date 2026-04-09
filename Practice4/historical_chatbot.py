from __future__ import annotations

from openai import OpenAI

from .chat_models import ChatReply, ChatTurn
from .historical_figures import HistoricalFigure


DEFAULT_CHAT_MODEL = "gpt-4.1-mini"


class HistoricalChatPromptBuilder:
    def build_input(
        self,
        figure: HistoricalFigure,
        history: list[ChatTurn],
        user_message: str,
    ) -> list[dict]:
        history_block = self._format_history(figure, history)
        prompt = f"""
너는 유명한 역사적 인물과 대화하는 시뮬레이션 챗봇이다.
아래 인물의 말투, 성격, 가치관을 반영해 자연스럽게 답해야 한다.

인물 정보:
- 이름: {figure.name}
- 시대: {figure.years}
- 인물 설명: {figure.identity}
- 말투와 성격: {figure.speaking_style}
- 핵심 관점: {figure.perspective}

응답 규칙:
1. 반드시 {figure.name}의 1인칭 관점과 어조를 유지한다.
2. 사용자의 질문 언어를 우선 따라 답한다.
3. 이전 질문과 답변의 맥락을 이어서 자연스럽게 반응한다.
4. 실제 역사적 사실을 함부로 꾸며내지 말고, 확신이 없으면 솔직히 한계를 밝힌다.
5. 자신의 사후 사건이나 현대 기술에 대해서는 직접 경험하지 못했다는 점을 밝힌 뒤, 인물의 철학에 맞는 의견만 조심스럽게 덧붙인다.
6. 지나치게 해설문처럼 쓰지 말고 실제 대화처럼 답한다.
7. 답변은 보통 4~8문장 정도로 하되, 질문이 짧으면 더 간결하게 답할 수 있다.

지금까지의 대화:
{history_block}

새 질문:
사용자: {user_message.strip()}

이제 {figure.name}로서 답하라.
""".strip()

        return [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            }
        ]

    def _format_history(self, figure: HistoricalFigure, history: list[ChatTurn]) -> str:
        if not history:
            return "이전 대화 없음."

        lines: list[str] = []
        for turn in history:
            speaker = "사용자" if turn.role == "user" else figure.name
            lines.append(f"{speaker}: {turn.text.strip()}")
        return "\n".join(lines)


class HistoricalChatbot:
    def __init__(self, client: OpenAI, model: str = DEFAULT_CHAT_MODEL) -> None:
        self.client = client
        self.model = model

    def generate_reply(
        self,
        figure: HistoricalFigure,
        history: list[ChatTurn],
        user_message: str,
    ) -> ChatReply:
        message = user_message.strip()
        if not message:
            raise ValueError("질문을 입력해야 합니다.")

        response = self.client.responses.create(
            model=self.model,
            input=HistoricalChatPromptBuilder().build_input(figure, history, message),
        )

        reply_text = (response.output_text or "").strip()
        if not reply_text:
            raise RuntimeError("모델이 빈 응답을 반환했습니다.")

        return ChatReply(
            reply_text=reply_text,
            figure_name=figure.name,
            used_model=self.model,
        )
