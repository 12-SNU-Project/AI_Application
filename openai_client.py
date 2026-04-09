from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parent
ENV_CANDIDATES = (
    PROJECT_ROOT / ".env",
    PROJECT_ROOT / "Practice3" / ".env",
    PROJECT_ROOT / "Practice4" / ".env",
)


def load_project_env() -> None:
    loaded_any = False
    for env_path in ENV_CANDIDATES:
        if env_path.exists():
            load_dotenv(env_path, override=False)
            loaded_any = True

    if not loaded_any:
        load_dotenv(override=False)


def create_openai_client() -> OpenAI:
    load_project_env()
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY가 설정되지 않았습니다. 루트 또는 Practice3/.env 파일에 OPENAI_API_KEY=... 형식으로 추가하세요."
        )

    return OpenAI(api_key=api_key)
