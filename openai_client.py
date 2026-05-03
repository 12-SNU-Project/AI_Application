from __future__ import annotations

import os

from dotenv import load_dotenv
from openai import OpenAI

from project_paths import ROOT_ENV_PATH


def load_project_env() -> None:
    load_dotenv(ROOT_ENV_PATH, override=False)


def create_openai_client() -> OpenAI:
    load_project_env()
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY가 설정되지 않았습니다. 루트 .env 파일에 OPENAI_API_KEY=... 형식으로 추가하세요."
        )

    return OpenAI(api_key=api_key)
