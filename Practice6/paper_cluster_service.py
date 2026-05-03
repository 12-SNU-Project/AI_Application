from __future__ import annotations

import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from openai import OpenAI
from pypdf import PdfReader
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

from .paper_cluster_models import (
    DEFAULT_CLUSTER_PLOT_PATH,
    PaperClusteringResult,
    PaperDocument,
    SUPPORTED_PDF_EXTENSIONS,
)


DEFAULT_PAPER_EMBEDDING_MODEL = "text-embedding-3-small"
MAX_EMBEDDING_CHARS = 12000


class PaperClusteringService:
    def __init__(self, client: OpenAI, embedding_model: str = DEFAULT_PAPER_EMBEDDING_MODEL) -> None:
        self.client = client
        self.embedding_model = embedding_model

    def discover_pdfs_in_directory(self, directory: Path) -> list[Path]:
        if not directory.exists() or not directory.is_dir():
            raise ValueError(f"유효한 PDF 폴더가 아닙니다: {directory}")

        pdf_paths = [
            path
            for path in sorted(directory.iterdir())
            if path.is_file() and path.suffix.lower() in SUPPORTED_PDF_EXTENSIONS
        ]
        return pdf_paths

    def normalize_pdf_paths(self, pdf_paths: list[Path]) -> list[Path]:
        normalized: list[Path] = []
        seen: set[Path] = set()

        for raw_path in pdf_paths:
            resolved = raw_path.expanduser().resolve()
            if resolved in seen:
                continue
            if not resolved.exists():
                raise ValueError(f"PDF 파일을 찾을 수 없습니다: {resolved}")
            if resolved.suffix.lower() not in SUPPORTED_PDF_EXTENSIONS:
                raise ValueError(f"지원하지 않는 파일 형식입니다: {resolved.name}")
            seen.add(resolved)
            normalized.append(resolved)

        if not normalized:
            raise ValueError("최소 1개 이상의 PDF 논문을 선택해야 합니다.")

        return normalized

    def cluster_papers(
        self,
        pdf_paths: list[Path],
        cluster_count: int,
        plot_path: Path = DEFAULT_CLUSTER_PLOT_PATH,
    ) -> PaperClusteringResult:
        normalized_paths = self.normalize_pdf_paths(pdf_paths)
        if cluster_count < 1:
            raise ValueError("클러스터 수는 1 이상이어야 합니다.")
        if cluster_count > len(normalized_paths):
            raise ValueError("클러스터 수는 선택한 논문 수보다 클 수 없습니다.")

        documents = [self._build_document(pdf_path) for pdf_path in normalized_paths]
        embedding_inputs = [self._build_embedding_text(document) for document in documents]
        embeddings = self._embed_texts(embedding_inputs)

        for document, embedding in zip(documents, embeddings):
            document.embedding = embedding

        labels = self._cluster_embeddings(embeddings, cluster_count)
        for document, label in zip(documents, labels):
            document.cluster_label = int(label)

        plot_output = self._create_cluster_plot(documents, plot_path) if len(documents) >= 2 else None

        documents.sort(key=lambda item: ((item.cluster_label or 0), item.title.lower(), item.file_name.lower()))

        return PaperClusteringResult(
            documents=documents,
            cluster_count=cluster_count,
            embedding_model=self.embedding_model,
            plot_path=str(plot_output) if plot_output is not None else None,
        )

    def _build_document(self, pdf_path: Path) -> PaperDocument:
        extracted_text = self.extract_text_from_pdf(pdf_path)
        title = self.extract_title(extracted_text, pdf_path)
        return PaperDocument(
            pdf_path=str(pdf_path),
            file_name=pdf_path.name,
            title=title,
            extracted_text=extracted_text,
            embedding=[],
        )

    def extract_text_from_pdf(self, pdf_path: Path) -> str:
        reader = PdfReader(str(pdf_path))
        pages: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            cleaned = self._normalize_page_text(page_text)
            if cleaned:
                pages.append(cleaned)

        if not pages:
            raise ValueError(f"PDF에서 텍스트를 추출하지 못했습니다: {pdf_path.name}")

        return "\n".join(pages)

    def extract_title(self, extracted_text: str, pdf_path: Path) -> str:
        lines = [line.strip() for line in extracted_text.splitlines() if line.strip()]
        for line in lines[:20]:
            if self._looks_like_title(line):
                return line
        return pdf_path.stem.replace("_", " ").strip()

    def _looks_like_title(self, line: str) -> bool:
        if len(line) < 8 or len(line) > 180:
            return False
        if re.fullmatch(r"[0-9 .-]+", line):
            return False
        return True

    def _build_embedding_text(self, document: PaperDocument) -> str:
        compact_text = self._normalize_text(document.extracted_text)
        excerpt = compact_text[:MAX_EMBEDDING_CHARS]
        return (
            f"논문 제목: {document.title}\n"
            f"파일명: {document.file_name}\n"
            f"논문 본문 요약용 발췌: {excerpt}"
        )

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=self.embedding_model,
            input=texts,
        )
        return [list(item.embedding) for item in response.data]

    def _cluster_embeddings(self, embeddings: list[list[float]], cluster_count: int) -> list[int]:
        if len(embeddings) == 1:
            return [0]

        model = KMeans(n_clusters=cluster_count, random_state=42, n_init=10)
        return [int(label) for label in model.fit_predict(embeddings)]

    def _create_cluster_plot(self, documents: list[PaperDocument], plot_path: Path) -> Path | None:
        if len(documents) < 2:
            return None

        embeddings = [document.embedding for document in documents]
        n_components = 2
        reduced_points = PCA(n_components=n_components).fit_transform(embeddings).tolist()

        plot_path.parent.mkdir(parents=True, exist_ok=True)
        plt.figure(figsize=(8.5, 6))

        unique_labels = sorted({document.cluster_label or 0 for document in documents})
        for label in unique_labels:
            cluster_points = [
                reduced_points[index]
                for index, document in enumerate(documents)
                if document.cluster_label == label
            ]
            x_values = [point[0] for point in cluster_points]
            y_values = [point[1] for point in cluster_points]
            plt.scatter(x_values, y_values, label=f"Cluster {label + 1}", s=90)

        for point, document in zip(reduced_points, documents):
            plt.annotate(
                self._truncate_label(document.title, 28),
                (point[0], point[1]),
                textcoords="offset points",
                xytext=(5, 4),
                fontsize=8,
            )

        plt.title("PDF Paper Clustering (PCA 2D)")
        plt.xlabel("PCA 1")
        plt.ylabel("PCA 2")
        plt.legend()
        plt.tight_layout()
        plt.savefig(plot_path, dpi=160)
        plt.close()
        return plot_path

    def _truncate_label(self, text: str, max_length: int) -> str:
        if len(text) <= max_length:
            return text
        return text[: max_length - 3].rstrip() + "..."

    def _normalize_text(self, text: str) -> str:
        compact = re.sub(r"\s+", " ", text or "").strip()
        return compact

    def _normalize_page_text(self, text: str) -> str:
        lines = [re.sub(r"\s+", " ", line).strip() for line in (text or "").splitlines()]
        non_empty_lines = [line for line in lines if line]
        return "\n".join(non_empty_lines)
