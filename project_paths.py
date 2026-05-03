from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
ROOT_ENV_PATH = PROJECT_ROOT / ".env"
INDEX_DIR = PROJECT_ROOT / "index"
IMAGE_SEARCH_INDEX_PATH = INDEX_DIR / "image_search_index.json"
