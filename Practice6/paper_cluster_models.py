from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


SUPPORTED_PDF_EXTENSIONS = {".pdf"}
DEFAULT_CLUSTER_PLOT_PATH = Path(__file__).resolve().parent / "paper_clusters.png"


@dataclass
class PaperDocument:
    pdf_path: str
    file_name: str
    title: str
    extracted_text: str
    embedding: list[float]
    cluster_label: int | None = None

    @property
    def path(self) -> Path:
        return Path(self.pdf_path)

    @property
    def preview_text(self) -> str:
        cleaned = self.extracted_text.strip()
        if len(cleaned) <= 260:
            return cleaned
        return cleaned[:257].rstrip() + "..."


@dataclass
class PaperClusteringResult:
    documents: list[PaperDocument]
    cluster_count: int
    embedding_model: str
    plot_path: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
