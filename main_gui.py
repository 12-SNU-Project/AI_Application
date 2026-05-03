from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from PIL import Image, ImageOps, ImageTk

from Practice3.story_models import StoryRequest
from Practice3.story_service import DEFAULT_STORY_MODEL, StoryGenerator
from Practice4.chat_models import ChatTurn
from Practice4.historical_chatbot import DEFAULT_CHAT_MODEL, HistoricalChatbot
from Practice4.historical_figures import (
    DEFAULT_FIGURE_NAME,
    HISTORICAL_FIGURES,
    HistoricalFigure,
    get_figure,
)
from Practice5.image_search_models import DEFAULT_INDEX_PATH, ImageSearchIndex, SearchResult
from Practice5.image_search_service import (
    DEFAULT_CAPTION_MODEL,
    DEFAULT_EMBEDDING_MODEL,
    SemanticImageSearchService,
)
from Practice6.paper_cluster_models import DEFAULT_CLUSTER_PLOT_PATH, PaperClusteringResult
from Practice6.paper_cluster_service import DEFAULT_PAPER_EMBEDDING_MODEL, PaperClusteringService
from openai_client import create_openai_client


APP_BG = "#f3eee4"
SURFACE_BG = "#fffaf2"
PANEL_BG = "#f7f1e7"
ACCENT = "#1f5f5b"
ACCENT_SOFT = "#d9ebe7"
TEXT_COLOR = "#203238"
MUTED_TEXT = "#6b7573"
BORDER_COLOR = "#d7cebe"
STATUS_BG = "#ece2d1"
FIGURE_ACCENT = "#8f5b34"

RESAMPLE = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS


@dataclass
class ThumbnailCard:
    card: tk.Frame
    bg_widgets: tuple[tk.Widget, ...]
    order_label: tk.Label
    name_label: tk.Label
    meta_label: tk.Label


class StoryTab(tk.Frame):
    def __init__(self, master: tk.Misc, generator: StoryGenerator) -> None:
        super().__init__(master, bg=APP_BG)
        self.generator = generator

        self.selected_paths: list[Path] = []
        self.selected_preview_index: Optional[int] = None
        self.is_generating = False
        self.thumbnail_cards: list[ThumbnailCard] = []
        self.thumbnail_photo_refs: list[Optional[ImageTk.PhotoImage]] = []
        self.preview_photo: Optional[ImageTk.PhotoImage] = None

        self.sentiment_var = tk.StringVar(value="행복")
        self.language_var = tk.StringVar(value="한국어")
        self.length_var = tk.StringVar(value="짧게")
        self.status_var = tk.StringVar(value="이미지를 선택한 뒤 이야기를 생성하세요.")
        self.selection_summary_var = tk.StringVar(
            value="장면 순서를 유지할 이미지를 여러 장 선택하면, 아래에서 미리보기를 바로 확인할 수 있습니다."
        )
        self.preview_title_var = tk.StringVar(value="대표 미리보기")
        self.preview_meta_var = tk.StringVar(
            value="선택한 이미지의 썸네일과 큰 화면 미리보기가 이곳에 표시됩니다."
        )
        self.result_meta_var = tk.StringVar(value="생성된 이야기는 이 영역에 정리되어 표시됩니다.")

        self._build_ui()
        self._set_output(
            "이야기 결과가 여기에 표시됩니다.\n\n"
            "이미지를 여러 장 선택하고 분위기를 고른 뒤 '이야기 생성' 버튼을 눌러보세요."
        )
        self._refresh_gallery()
        self._update_action_states()

    def _build_ui(self) -> None:
        main_frame = tk.Frame(self, bg=APP_BG, padx=8, pady=14)
        main_frame.pack(fill="both", expand=True)

        header_frame = tk.Frame(main_frame, bg=APP_BG)
        header_frame.pack(fill="x", pady=(0, 16))

        tk.Label(
            header_frame,
            text="그림 순서 + 감정 기반 이야기 생성",
            bg=APP_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 21, "bold"),
        ).pack(anchor="w")

        tk.Label(
            header_frame,
            text="썸네일 갤러리로 장면 흐름을 먼저 확인하고, 선택한 분위기에 맞춰 한 편의 짧은 이야기를 만듭니다.",
            bg=APP_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 11),
        ).pack(anchor="w", pady=(6, 0))

        controls_card = tk.Frame(
            main_frame,
            bg=SURFACE_BG,
            padx=18,
            pady=16,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        controls_card.pack(fill="x", pady=(0, 18))

        self.select_button = ttk.Button(
            controls_card,
            text="이미지 선택",
            style="Secondary.TButton",
            command=self.select_images,
        )
        self.select_button.grid(row=0, column=0, padx=(0, 8), pady=4, sticky="w")

        self.clear_button = ttk.Button(
            controls_card,
            text="선택 초기화",
            style="Secondary.TButton",
            command=self.clear_images,
        )
        self.clear_button.grid(row=0, column=1, padx=(0, 18), pady=4, sticky="w")

        self._add_control_label(controls_card, "감정", 2)
        self.sentiment_combo = ttk.Combobox(
            controls_card,
            textvariable=self.sentiment_var,
            values=["행복", "슬픔", "긴장감", "신비로움", "따뜻함", "우울함", "희망", "공포"],
            state="readonly",
            width=12,
        )
        self.sentiment_combo.grid(row=0, column=3, padx=(0, 14), pady=4, sticky="w")

        self._add_control_label(controls_card, "언어", 4)
        self.language_combo = ttk.Combobox(
            controls_card,
            textvariable=self.language_var,
            values=["한국어", "English"],
            state="readonly",
            width=10,
        )
        self.language_combo.grid(row=0, column=5, padx=(0, 14), pady=4, sticky="w")

        self._add_control_label(controls_card, "분량", 6)
        self.length_combo = ttk.Combobox(
            controls_card,
            textvariable=self.length_var,
            values=["짧게", "조금 길게"],
            state="readonly",
            width=10,
        )
        self.length_combo.grid(row=0, column=7, padx=(0, 18), pady=4, sticky="w")

        self.generate_button = ttk.Button(
            controls_card,
            text="이야기 생성",
            style="Primary.TButton",
            command=self.generate_story,
        )
        self.generate_button.grid(row=0, column=8, sticky="e")

        controls_card.grid_columnconfigure(8, weight=1)

        tk.Label(
            controls_card,
            textvariable=self.selection_summary_var,
            bg=SURFACE_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
        ).grid(row=1, column=0, columnspan=9, sticky="w", pady=(12, 0))

        content_frame = tk.Frame(main_frame, bg=APP_BG)
        content_frame.pack(fill="both", expand=True)
        content_frame.grid_columnconfigure(0, weight=5)
        content_frame.grid_columnconfigure(1, weight=7)
        content_frame.grid_rowconfigure(0, weight=1)

        left_panel = tk.Frame(content_frame, bg=APP_BG)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        right_panel = tk.Frame(content_frame, bg=APP_BG)
        right_panel.grid(row=0, column=1, sticky="nsew")

        self._build_preview_panel(left_panel)
        self._build_result_panel(right_panel)

        tk.Label(
            main_frame,
            textvariable=self.status_var,
            bg=STATUS_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 10),
            anchor="w",
            padx=12,
            pady=10,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        ).pack(fill="x", pady=(16, 0))

    def _build_preview_panel(self, parent: tk.Frame) -> None:
        preview_card = tk.Frame(
            parent,
            bg=SURFACE_BG,
            padx=16,
            pady=16,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        preview_card.pack(fill="both", expand=True)

        tk.Label(
            preview_card,
            textvariable=self.preview_title_var,
            bg=SURFACE_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 15, "bold"),
        ).pack(anchor="w")

        tk.Label(
            preview_card,
            textvariable=self.preview_meta_var,
            bg=SURFACE_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
        ).pack(anchor="w", pady=(4, 12))

        self.preview_holder = tk.Frame(preview_card, bg=PANEL_BG, height=320)
        self.preview_holder.pack(fill="both", expand=False)
        self.preview_holder.pack_propagate(False)

        self.preview_image_label = tk.Label(
            self.preview_holder,
            bg=PANEL_BG,
            fg=MUTED_TEXT,
            text="이미지를 선택하면 여기에서 크게 볼 수 있습니다.",
            font=("Helvetica", 12),
            justify="center",
            wraplength=360,
        )
        self.preview_image_label.pack(fill="both", expand=True, padx=18, pady=18)

        tk.Label(
            preview_card,
            text="장면 썸네일",
            bg=SURFACE_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 13, "bold"),
        ).pack(anchor="w", pady=(16, 0))

        tk.Label(
            preview_card,
            text="썸네일을 클릭하면 위쪽 대표 미리보기가 바뀝니다.",
            bg=SURFACE_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
        ).pack(anchor="w", pady=(4, 10))

        gallery_frame = tk.Frame(preview_card, bg=SURFACE_BG)
        gallery_frame.pack(fill="both", expand=True)

        self.thumbnail_canvas = tk.Canvas(gallery_frame, bg=SURFACE_BG, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(gallery_frame, orient="vertical", command=self.thumbnail_canvas.yview)
        self.thumbnail_canvas.configure(yscrollcommand=scrollbar.set)

        self.thumbnail_list = tk.Frame(self.thumbnail_canvas, bg=SURFACE_BG)
        self.thumbnail_window = self.thumbnail_canvas.create_window((0, 0), window=self.thumbnail_list, anchor="nw")

        self.thumbnail_list.bind("<Configure>", self._sync_thumbnail_scrollregion)
        self.thumbnail_canvas.bind("<Configure>", self._resize_thumbnail_window)

        self.thumbnail_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _build_result_panel(self, parent: tk.Frame) -> None:
        result_card = tk.Frame(
            parent,
            bg=SURFACE_BG,
            padx=16,
            pady=16,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        result_card.pack(fill="both", expand=True)

        tk.Label(
            result_card,
            text="생성 결과",
            bg=SURFACE_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 15, "bold"),
        ).pack(anchor="w")

        tk.Label(
            result_card,
            textvariable=self.result_meta_var,
            bg=SURFACE_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
        ).pack(anchor="w", pady=(4, 12))

        self.output_text = scrolledtext.ScrolledText(
            result_card,
            wrap=tk.WORD,
            font=("Helvetica", 11),
            bg="#fffdfa",
            fg=TEXT_COLOR,
            insertbackground=TEXT_COLOR,
            relief="flat",
            highlightthickness=0,
            padx=14,
            pady=14,
            spacing1=2,
            spacing3=6,
        )
        self.output_text.pack(fill="both", expand=True)

    def _add_control_label(self, parent: tk.Frame, text: str, column: int) -> None:
        tk.Label(
            parent,
            text=text,
            bg=SURFACE_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 10, "bold"),
        ).grid(row=0, column=column, padx=(0, 8), pady=4, sticky="e")

    def _sync_thumbnail_scrollregion(self, _event: tk.Event) -> None:
        self.thumbnail_canvas.configure(scrollregion=self.thumbnail_canvas.bbox("all"))

    def _resize_thumbnail_window(self, event: tk.Event) -> None:
        self.thumbnail_canvas.itemconfigure(self.thumbnail_window, width=event.width)

    def select_images(self) -> None:
        file_paths = filedialog.askopenfilenames(
            title="이야기에 사용할 이미지 선택",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.webp *.gif"),
                ("All files", "*.*"),
            ],
        )

        if not file_paths:
            return

        self.selected_paths = [Path(path) for path in file_paths]
        self.selected_preview_index = 0 if self.selected_paths else None
        self._refresh_gallery()
        self._update_selection_summary()
        self._update_action_states()
        self.status_var.set(f"총 {len(self.selected_paths)}개의 이미지를 선택했습니다.")

    def clear_images(self) -> None:
        self.selected_paths = []
        self.selected_preview_index = None
        self._refresh_gallery()
        self._update_selection_summary()
        self._update_action_states()
        self.status_var.set("선택한 이미지를 초기화했습니다.")

    def generate_story(self) -> None:
        if self.is_generating:
            return

        try:
            request = StoryRequest(
                image_paths=self.selected_paths,
                sentiment=self.sentiment_var.get(),
                language=self.language_var.get(),
                story_length=self.length_var.get(),
            )
            request.validate()
        except Exception as exc:
            self.status_var.set("입력을 확인하세요.")
            messagebox.showerror("입력 오류", str(exc))
            return

        self.is_generating = True
        self._update_action_states()
        self.result_meta_var.set("선택한 이미지 순서를 기준으로 OpenAI 모델이 이야기를 구성하고 있습니다.")
        self.status_var.set("이야기 생성 중입니다. 이미지 수가 많으면 조금 더 걸릴 수 있습니다.")
        self._set_output("이야기를 생성하고 있습니다...\n잠시만 기다려 주세요.")

        worker = threading.Thread(target=self._generate_story_worker, args=(request,), daemon=True)
        worker.start()

    def _generate_story_worker(self, request: StoryRequest) -> None:
        try:
            result = self.generator.generate(request)
        except Exception as exc:
            self.after(0, self._handle_story_error, str(exc))
            return

        self.after(0, self._apply_story_result, result)

    def _apply_story_result(self, result) -> None:
        self._set_output(
            f"[모델: {result.used_model}]\n"
            f"[이미지 수: {result.image_count}]\n"
            f"[감정: {result.sentiment}]\n\n"
            f"{result.story_text}\n"
        )
        self.result_meta_var.set(
            f"{result.image_count}장의 이미지 흐름을 바탕으로 '{result.sentiment}' 분위기의 이야기를 생성했습니다."
        )
        self.status_var.set("이야기 생성이 완료되었습니다.")
        self.is_generating = False
        self._update_action_states()

    def _handle_story_error(self, error_message: str) -> None:
        self.is_generating = False
        self._update_action_states()
        self.status_var.set("오류가 발생했습니다.")
        self.result_meta_var.set("생성 중 오류가 발생했습니다. 입력 이미지와 환경 설정을 다시 확인해 주세요.")
        messagebox.showerror("오류", error_message)

    def _update_selection_summary(self) -> None:
        if not self.selected_paths:
            self.selection_summary_var.set(
                "장면 순서를 유지할 이미지를 여러 장 선택하면, 아래에서 미리보기를 바로 확인할 수 있습니다."
            )
            return

        self.selection_summary_var.set(
            f"총 {len(self.selected_paths)}장의 이미지를 선택했습니다. 썸네일을 클릭해서 대표 미리보기를 바꿔가며 장면 흐름을 점검할 수 있습니다."
        )

    def _refresh_gallery(self) -> None:
        for child in self.thumbnail_list.winfo_children():
            child.destroy()

        self.thumbnail_cards.clear()
        self.thumbnail_photo_refs.clear()

        if not self.selected_paths:
            self._clear_preview()
            tk.Label(
                self.thumbnail_list,
                text="선택한 이미지가 없습니다.\n상단의 '이미지 선택' 버튼으로 장면을 불러오세요.",
                bg=SURFACE_BG,
                fg=MUTED_TEXT,
                font=("Helvetica", 11),
                justify="center",
                pady=24,
            ).pack(fill="x")
            return

        for index, path in enumerate(self.selected_paths):
            self._add_thumbnail_card(index, path)

        if self.selected_preview_index is None or self.selected_preview_index >= len(self.selected_paths):
            self.selected_preview_index = 0

        self._select_preview(self.selected_preview_index)

    def _add_thumbnail_card(self, index: int, path: Path) -> None:
        photo, metadata = self._create_thumbnail(path, (104, 104))
        self.thumbnail_photo_refs.append(photo)

        card = tk.Frame(
            self.thumbnail_list,
            bg=PANEL_BG,
            padx=10,
            pady=10,
            cursor="hand2",
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        card.pack(fill="x", pady=(0, 10))
        card.grid_columnconfigure(1, weight=1)

        image_box = tk.Frame(card, bg=PANEL_BG, width=104, height=104)
        image_box.grid(row=0, column=0, rowspan=3, sticky="nw")
        image_box.pack_propagate(False)

        image_label = tk.Label(
            image_box,
            bg=PANEL_BG,
            image=photo,
            text="" if photo is not None else "미리보기\n불가",
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
            justify="center",
        )
        image_label.pack(fill="both", expand=True)

        text_frame = tk.Frame(card, bg=PANEL_BG)
        text_frame.grid(row=0, column=1, sticky="nsew", padx=(12, 0))

        order_label = tk.Label(
            text_frame,
            text=f"Scene {index + 1}",
            bg=PANEL_BG,
            fg=ACCENT,
            font=("Helvetica", 9, "bold"),
        )
        order_label.pack(anchor="w")

        name_label = tk.Label(
            text_frame,
            text=path.name,
            bg=PANEL_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 11, "bold"),
            wraplength=220,
            justify="left",
        )
        name_label.pack(anchor="w", pady=(6, 4))

        meta_label = tk.Label(
            text_frame,
            text=metadata,
            bg=PANEL_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
        )
        meta_label.pack(anchor="w")

        card_widgets = (card, image_box, image_label, text_frame, order_label, name_label, meta_label)
        for widget in card_widgets:
            widget.bind("<Button-1>", lambda _event, idx=index: self._select_preview(idx))

        self.thumbnail_cards.append(
            ThumbnailCard(
                card=card,
                bg_widgets=card_widgets,
                order_label=order_label,
                name_label=name_label,
                meta_label=meta_label,
            )
        )

    def _select_preview(self, index: int) -> None:
        if not self.selected_paths:
            self._clear_preview()
            return

        self.selected_preview_index = index
        image_path = self.selected_paths[index]
        preview_photo, metadata = self._create_preview(image_path)

        self.preview_photo = preview_photo
        if preview_photo is not None:
            self.preview_image_label.configure(image=preview_photo, text="")
        else:
            self.preview_image_label.configure(image="", text="이 이미지는 미리보기를 표시할 수 없습니다.")
        self.preview_title_var.set(f"{index + 1}번째 장면 미리보기")
        self.preview_meta_var.set(f"{image_path.name}  |  {metadata}")
        self._update_thumbnail_selection_styles()

    def _clear_preview(self) -> None:
        self.preview_photo = None
        self.preview_image_label.configure(
            image="",
            text="이미지를 선택하면 여기에서 크게 볼 수 있습니다.",
        )
        self.preview_title_var.set("대표 미리보기")
        self.preview_meta_var.set("선택한 이미지의 썸네일과 큰 화면 미리보기가 이곳에 표시됩니다.")

    def _update_thumbnail_selection_styles(self) -> None:
        for index, thumbnail_card in enumerate(self.thumbnail_cards):
            is_active = index == self.selected_preview_index
            bg_color = ACCENT_SOFT if is_active else PANEL_BG
            border_color = ACCENT if is_active else BORDER_COLOR
            meta_color = TEXT_COLOR if is_active else MUTED_TEXT

            thumbnail_card.card.configure(
                bg=bg_color,
                highlightbackground=border_color,
                highlightcolor=border_color,
            )
            for widget in thumbnail_card.bg_widgets:
                widget.configure(bg=bg_color)

            thumbnail_card.order_label.configure(fg=ACCENT)
            thumbnail_card.name_label.configure(fg=TEXT_COLOR)
            thumbnail_card.meta_label.configure(fg=meta_color)

    def _create_thumbnail(self, image_path: Path, max_size: tuple[int, int]) -> tuple[Optional[ImageTk.PhotoImage], str]:
        try:
            image = self._open_image(image_path)
            original_width, original_height = image.size
            image.thumbnail(max_size, RESAMPLE)
            return ImageTk.PhotoImage(image), self._format_image_metadata(image_path, original_width, original_height)
        except Exception:
            return None, "미리보기를 불러올 수 없는 이미지"

    def _create_preview(self, image_path: Path) -> tuple[Optional[ImageTk.PhotoImage], str]:
        try:
            image = self._open_image(image_path)
            original_width, original_height = image.size
            holder_width = max(self.preview_holder.winfo_width() - 36, 360)
            holder_height = max(self.preview_holder.winfo_height() - 36, 280)
            image.thumbnail((holder_width, holder_height), RESAMPLE)
            return ImageTk.PhotoImage(image), self._format_image_metadata(image_path, original_width, original_height)
        except Exception:
            return None, "미리보기를 불러올 수 없는 이미지"

    def _open_image(self, image_path: Path) -> Image.Image:
        with Image.open(image_path) as image:
            normalized = ImageOps.exif_transpose(image)
            if normalized.mode not in ("RGB", "RGBA"):
                normalized = normalized.convert("RGBA")
            return normalized.copy()

    def _format_image_metadata(self, image_path: Path, width: int, height: int) -> str:
        extension = image_path.suffix.replace(".", "").upper() or "IMG"
        file_size = self._format_file_size(image_path.stat().st_size)
        return f"{width} x {height}px  |  {extension}  |  {file_size}"

    def _format_file_size(self, size_in_bytes: int) -> str:
        size_in_kb = size_in_bytes / 1024
        if size_in_kb < 1024:
            return f"{size_in_kb:.0f} KB"
        return f"{size_in_kb / 1024:.1f} MB"

    def _set_output(self, text: str) -> None:
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, text)
        self.output_text.configure(state="disabled")

    def _update_action_states(self) -> None:
        button_state = "disabled" if self.is_generating else "normal"
        combo_state = "disabled" if self.is_generating else "readonly"

        self.select_button.configure(state=button_state)
        self.clear_button.configure(state="disabled" if self.is_generating or not self.selected_paths else "normal")
        self.generate_button.configure(state="disabled" if self.is_generating or not self.selected_paths else "normal")
        self.sentiment_combo.configure(state=combo_state)
        self.language_combo.configure(state=combo_state)
        self.length_combo.configure(state=combo_state)


class HistoricalChatTab(tk.Frame):
    def __init__(self, master: tk.Misc, chatbot: HistoricalChatbot) -> None:
        super().__init__(master, bg=APP_BG)
        self.chatbot = chatbot

        self.chat_history: list[ChatTurn] = []
        self.is_generating = False

        self.figure_var = tk.StringVar(value=DEFAULT_FIGURE_NAME)
        self.figure_name_var = tk.StringVar()
        self.figure_years_var = tk.StringVar()
        self.figure_identity_var = tk.StringVar()
        self.figure_style_var = tk.StringVar()
        self.figure_examples_var = tk.StringVar()
        self.status_var = tk.StringVar(value="역사적 인물을 고르고 질문을 입력하세요.")
        self.chat_meta_var = tk.StringVar(
            value="대화는 같은 인물 안에서 누적되어 다음 응답에 계속 반영됩니다."
        )

        self._build_ui()
        self._refresh_figure_profile()
        self._reset_chat(announce=False)
        self._update_action_states()
        self.chat_input.focus_set()

    def _build_ui(self) -> None:
        main_frame = tk.Frame(self, bg=APP_BG, padx=8, pady=14)
        main_frame.pack(fill="both", expand=True)

        header_frame = tk.Frame(main_frame, bg=APP_BG)
        header_frame.pack(fill="x", pady=(0, 16))

        tk.Label(
            header_frame,
            text="유명한 역사 인물과 대화하기",
            bg=APP_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 21, "bold"),
        ).pack(anchor="w")

        tk.Label(
            header_frame,
            text="선택한 인물의 말투와 성격을 반영한 답변을 생성하고, 이전 대화를 누적해 자연스럽게 이어갑니다.",
            bg=APP_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 11),
        ).pack(anchor="w", pady=(6, 0))

        controls_card = tk.Frame(
            main_frame,
            bg=SURFACE_BG,
            padx=18,
            pady=16,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        controls_card.pack(fill="x", pady=(0, 18))

        tk.Label(
            controls_card,
            text="대화 인물",
            bg=SURFACE_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 10, "bold"),
        ).grid(row=0, column=0, padx=(0, 8), pady=4, sticky="e")

        self.figure_combo = ttk.Combobox(
            controls_card,
            textvariable=self.figure_var,
            values=list(HISTORICAL_FIGURES.keys()),
            state="readonly",
            width=22,
        )
        self.figure_combo.grid(row=0, column=1, padx=(0, 18), pady=4, sticky="w")
        self.figure_combo.bind("<<ComboboxSelected>>", self.on_figure_changed)

        self.reset_button = ttk.Button(
            controls_card,
            text="새 대화 시작",
            style="Secondary.TButton",
            command=self.reset_chat,
        )
        self.reset_button.grid(row=0, column=2, padx=(0, 10), pady=4, sticky="w")

        tk.Label(
            controls_card,
            text="아래 질문 입력창에 자유롭게 질문하세요. Enter는 전송, Shift+Enter는 줄바꿈입니다.",
            bg=SURFACE_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(12, 0))

        content_frame = tk.Frame(main_frame, bg=APP_BG)
        content_frame.pack(fill="both", expand=True)
        content_frame.grid_columnconfigure(0, weight=4)
        content_frame.grid_columnconfigure(1, weight=8)
        content_frame.grid_rowconfigure(0, weight=1)

        profile_panel = tk.Frame(content_frame, bg=APP_BG)
        profile_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        chat_panel = tk.Frame(content_frame, bg=APP_BG)
        chat_panel.grid(row=0, column=1, sticky="nsew")

        self._build_profile_panel(profile_panel)
        self._build_chat_panel(chat_panel)

        tk.Label(
            main_frame,
            textvariable=self.status_var,
            bg=STATUS_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 10),
            anchor="w",
            padx=12,
            pady=10,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        ).pack(fill="x", pady=(16, 0))

    def _build_profile_panel(self, parent: tk.Frame) -> None:
        profile_card = tk.Frame(
            parent,
            bg=SURFACE_BG,
            padx=16,
            pady=16,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        profile_card.pack(fill="both", expand=True)

        tk.Label(
            profile_card,
            text="인물 프로필",
            bg=SURFACE_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 15, "bold"),
        ).pack(anchor="w")

        tk.Label(
            profile_card,
            text="현재 선택한 역사 인물의 배경과 대화 스타일을 요약해 보여줍니다.",
            bg=SURFACE_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
        ).pack(anchor="w", pady=(4, 14))

        tk.Label(
            profile_card,
            textvariable=self.figure_name_var,
            bg=SURFACE_BG,
            fg=FIGURE_ACCENT,
            font=("Helvetica", 18, "bold"),
        ).pack(anchor="w")

        tk.Label(
            profile_card,
            textvariable=self.figure_years_var,
            bg=SURFACE_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
        ).pack(anchor="w", pady=(4, 12))

        tk.Label(
            profile_card,
            textvariable=self.figure_identity_var,
            bg=SURFACE_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 11),
            justify="left",
            wraplength=300,
        ).pack(anchor="w")

        info_box = tk.Frame(
            profile_card,
            bg=PANEL_BG,
            padx=14,
            pady=14,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        info_box.pack(fill="x", pady=(16, 14))

        tk.Label(
            info_box,
            text="말투와 관점",
            bg=PANEL_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 11, "bold"),
        ).pack(anchor="w")

        tk.Label(
            info_box,
            textvariable=self.figure_style_var,
            bg=PANEL_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
            justify="left",
            wraplength=280,
        ).pack(anchor="w", pady=(8, 0))

        example_box = tk.Frame(
            profile_card,
            bg=PANEL_BG,
            padx=14,
            pady=14,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        example_box.pack(fill="both", expand=True)

        tk.Label(
            example_box,
            text="질문 예시",
            bg=PANEL_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 11, "bold"),
        ).pack(anchor="w")

        tk.Label(
            example_box,
            textvariable=self.figure_examples_var,
            bg=PANEL_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
            justify="left",
            wraplength=280,
        ).pack(anchor="w", pady=(8, 0))

    def _build_chat_panel(self, parent: tk.Frame) -> None:
        chat_card = tk.Frame(
            parent,
            bg=SURFACE_BG,
            padx=16,
            pady=16,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        chat_card.pack(fill="both", expand=True)
        chat_card.grid_columnconfigure(0, weight=1)
        chat_card.grid_rowconfigure(1, weight=1)

        tk.Label(
            chat_card,
            text="대화 기록",
            bg=SURFACE_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 15, "bold"),
        ).grid(row=0, column=0, sticky="w")

        tk.Label(
            chat_card,
            textvariable=self.chat_meta_var,
            bg=SURFACE_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
        ).grid(row=0, column=1, sticky="e")

        self.chat_transcript = scrolledtext.ScrolledText(
            chat_card,
            wrap=tk.WORD,
            font=("Helvetica", 11),
            bg="#fffdfa",
            fg=TEXT_COLOR,
            insertbackground=TEXT_COLOR,
            relief="flat",
            highlightthickness=0,
            padx=14,
            pady=14,
            spacing1=2,
            spacing3=6,
        )
        self.chat_transcript.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(12, 14))
        self._configure_chat_transcript_tags()

        composer_card = tk.Frame(
            chat_card,
            bg=PANEL_BG,
            padx=12,
            pady=12,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        composer_card.grid(row=2, column=0, columnspan=2, sticky="ew")
        composer_card.grid_columnconfigure(0, weight=1)

        tk.Label(
            composer_card,
            text="질문 입력창",
            bg=PANEL_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 11, "bold"),
        ).grid(row=0, column=0, sticky="w")

        self.chat_input = tk.Text(
            composer_card,
            height=5,
            wrap=tk.WORD,
            font=("Helvetica", 11),
            bg="#fffdfa",
            fg=TEXT_COLOR,
            insertbackground=TEXT_COLOR,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            padx=10,
            pady=10,
        )
        self.chat_input.grid(row=1, column=0, sticky="ew", pady=(8, 0), padx=(0, 10))
        self.chat_input.bind("<Return>", self.on_chat_input_return)

        self.send_button = ttk.Button(
            composer_card,
            text="질문 보내기",
            style="Primary.TButton",
            command=self.send_chat_message,
        )
        self.send_button.grid(row=1, column=1, sticky="se")

    def current_figure(self) -> HistoricalFigure:
        return get_figure(self.figure_var.get())

    def _refresh_figure_profile(self) -> None:
        figure = self.current_figure()
        self.figure_name_var.set(figure.name)
        self.figure_years_var.set(figure.years)
        self.figure_identity_var.set(figure.identity)
        self.figure_style_var.set(
            f"말투와 성격: {figure.speaking_style}\n\n핵심 관점: {figure.perspective}"
        )
        self.figure_examples_var.set("\n".join(f"- {question}" for question in figure.starter_questions))

    def on_figure_changed(self, _event: tk.Event) -> None:
        if self.is_generating:
            return

        self._refresh_figure_profile()
        self._reset_chat(announce=False)
        self.status_var.set(f"대화 상대를 {self.current_figure().name}(으)로 변경했습니다. 이전 대화를 초기화했습니다.")

    def reset_chat(self) -> None:
        self._reset_chat(announce=True)

    def _reset_chat(self, announce: bool) -> None:
        figure = self.current_figure()
        self.chat_history.clear()
        self.chat_input.delete("1.0", tk.END)
        self._clear_chat_transcript()
        self._append_chat_notice(
            f"{figure.name} ({figure.years})와의 새 대화를 시작합니다.\n"
            f"{figure.identity}\n"
            f"이 인물은 대체로 다음과 같은 어조를 보입니다: {figure.speaking_style}"
        )
        self.chat_meta_var.set(
            "대화는 같은 인물 안에서 누적되어 다음 응답에 계속 반영됩니다. 인물을 바꾸면 맥락은 초기화됩니다."
        )
        if announce:
            self.status_var.set(f"{figure.name}와의 대화를 새로 시작했습니다.")
        else:
            self.status_var.set(f"{figure.name}에게 질문할 준비가 되었습니다.")

    def _clear_chat_transcript(self) -> None:
        self.chat_transcript.configure(state="normal")
        self.chat_transcript.delete("1.0", tk.END)
        self.chat_transcript.configure(state="disabled")

    def _configure_chat_transcript_tags(self) -> None:
        self.chat_transcript.tag_configure("notice_title", foreground=ACCENT, font=("Helvetica", 11, "bold"))
        self.chat_transcript.tag_configure("notice_body", foreground=MUTED_TEXT, spacing3=12)
        self.chat_transcript.tag_configure("user_name", foreground=ACCENT, font=("Helvetica", 10, "bold"))
        self.chat_transcript.tag_configure("figure_name", foreground=FIGURE_ACCENT, font=("Helvetica", 10, "bold"))
        self.chat_transcript.tag_configure("message_body", foreground=TEXT_COLOR, spacing3=12)
        self.chat_transcript.configure(state="disabled")

    def _append_chat_notice(self, text: str) -> None:
        self.chat_transcript.configure(state="normal")
        self.chat_transcript.insert(tk.END, "대화 준비\n", "notice_title")
        self.chat_transcript.insert(tk.END, f"{text}\n\n", "notice_body")
        self.chat_transcript.configure(state="disabled")
        self.chat_transcript.see(tk.END)

    def _append_chat_message(self, speaker: str, text: str, is_user: bool) -> None:
        speaker_tag = "user_name" if is_user else "figure_name"
        self.chat_transcript.configure(state="normal")
        self.chat_transcript.insert(tk.END, f"{speaker}\n", speaker_tag)
        self.chat_transcript.insert(tk.END, f"{text.strip()}\n\n", "message_body")
        self.chat_transcript.configure(state="disabled")
        self.chat_transcript.see(tk.END)

    def send_chat_message(self) -> None:
        if self.is_generating:
            return

        user_message = self.chat_input.get("1.0", tk.END).strip()
        if not user_message:
            self.status_var.set("질문 입력창에 내용을 작성하세요.")
            self.chat_input.focus_set()
            return

        figure = self.current_figure()
        history_snapshot = list(self.chat_history)

        self.chat_input.delete("1.0", tk.END)
        self._append_chat_message("사용자", user_message, is_user=True)
        self.is_generating = True
        self._update_action_states()
        self.chat_meta_var.set("이전 대화 맥락과 선택한 인물의 성격을 반영해 답변을 생성하고 있습니다.")
        self.status_var.set(f"{figure.name}의 말투로 답변을 생성 중입니다.")

        worker = threading.Thread(
            target=self._generate_chat_reply_worker,
            args=(figure, history_snapshot, user_message),
            daemon=True,
        )
        worker.start()

    def _generate_chat_reply_worker(
        self,
        figure: HistoricalFigure,
        history_snapshot: list[ChatTurn],
        user_message: str,
    ) -> None:
        try:
            reply = self.chatbot.generate_reply(figure, history_snapshot, user_message)
        except Exception as exc:
            self.after(0, self._handle_chat_error, str(exc), user_message)
            return

        self.after(0, self._apply_chat_reply, figure, user_message, reply.reply_text)

    def _apply_chat_reply(self, figure: HistoricalFigure, user_message: str, reply_text: str) -> None:
        self.chat_history.append(ChatTurn(role="user", text=user_message))
        self.chat_history.append(ChatTurn(role="assistant", text=reply_text))
        self._append_chat_message(figure.name, reply_text, is_user=False)
        self.chat_meta_var.set(
            f"현재까지 {len(self.chat_history) // 2}개의 질문이 누적되어 다음 답변에 반영됩니다."
        )
        self.status_var.set(f"{figure.name}의 답변이 도착했습니다.")
        self.is_generating = False
        self._update_action_states()
        self.chat_input.focus_set()

    def _handle_chat_error(self, error_message: str, user_message: str) -> None:
        self.is_generating = False
        self._update_action_states()
        self.chat_input.delete("1.0", tk.END)
        self.chat_input.insert("1.0", user_message)
        self._append_chat_notice("답변 생성 중 오류가 발생했습니다. 방금 입력한 질문은 아래 입력창에 다시 넣어두었습니다.")
        self.chat_meta_var.set("답변 생성 중 오류가 발생했습니다. 질문을 수정하거나 다시 보내 주세요.")
        self.status_var.set("오류가 발생했습니다.")
        self.chat_input.focus_set()
        messagebox.showerror("오류", error_message)

    def _update_action_states(self) -> None:
        button_state = "disabled" if self.is_generating else "normal"
        figure_state = "disabled" if self.is_generating else "readonly"

        self.figure_combo.configure(state=figure_state)
        self.reset_button.configure(state=button_state)
        self.send_button.configure(state=button_state)
        if self.is_generating:
            self.chat_input.configure(state="disabled")
        else:
            self.chat_input.configure(state="normal")

    def on_chat_input_return(self, event: tk.Event) -> Optional[str]:
        if event.state & 0x0001:
            return None

        self.send_chat_message()
        return "break"


class ImageSearchTab(tk.Frame):
    def __init__(self, master: tk.Misc, search_service: SemanticImageSearchService) -> None:
        super().__init__(master, bg=APP_BG)
        self.search_service = search_service

        self.selected_paths: list[Path] = []
        self.index: Optional[ImageSearchIndex] = None
        self.result_photo: Optional[ImageTk.PhotoImage] = None
        self.is_indexing = False
        self.is_searching = False

        self.query_var = tk.StringVar()
        self.selection_summary_var = tk.StringVar(
            value=(
                "아직 인덱싱할 이미지가 선택되지 않았습니다. "
                f"새 인덱스를 생성하면 {DEFAULT_INDEX_PATH.name} 파일로 저장됩니다."
            )
        )
        self.index_meta_var = tk.StringVar(value="저장된 인덱스를 확인하는 중입니다.")
        self.status_var = tk.StringVar(value="이미지를 선택해 인덱스를 생성한 뒤 검색하세요.")
        self.result_title_var = tk.StringVar(value="검색 결과 미리보기")
        self.result_meta_var = tk.StringVar(value="텍스트 쿼리를 입력하면 가장 유사한 이미지를 이곳에 표시합니다.")
        self.result_caption_var = tk.StringVar(
            value="이미지 캡션과 유사도 점수가 여기에 표시됩니다."
        )

        self._build_ui()
        self._set_index_overview(
            "인덱싱된 이미지 목록이 여기에 표시됩니다.\n\n"
            "먼저 이미지를 선택하고 '인덱스 생성'을 실행하세요."
        )
        self._set_ranking_text(
            "검색 결과 순위가 여기에 표시됩니다.\n\n"
            "인덱스를 만든 뒤 텍스트 쿼리를 입력해 검색을 실행하세요."
        )
        self._clear_result_preview()
        self._load_saved_index_if_exists()
        self._update_action_states()

    def _build_ui(self) -> None:
        main_frame = tk.Frame(self, bg=APP_BG, padx=8, pady=14)
        main_frame.pack(fill="both", expand=True)

        header_frame = tk.Frame(main_frame, bg=APP_BG)
        header_frame.pack(fill="x", pady=(0, 16))

        tk.Label(
            header_frame,
            text="텍스트-이미지 유사도 검색",
            bg=APP_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 21, "bold"),
        ).pack(anchor="w")

        tk.Label(
            header_frame,
            text="Vision API로 이미지 설명을 만들고 임베딩을 저장한 뒤, 텍스트 쿼리와 가장 가까운 이미지를 찾아 반환합니다.",
            bg=APP_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 11),
        ).pack(anchor="w", pady=(6, 0))

        controls_card = tk.Frame(
            main_frame,
            bg=SURFACE_BG,
            padx=18,
            pady=16,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        controls_card.pack(fill="x", pady=(0, 18))

        self.select_images_button = ttk.Button(
            controls_card,
            text="이미지 선택",
            style="Secondary.TButton",
            command=self.select_images,
        )
        self.select_images_button.grid(row=0, column=0, padx=(0, 8), pady=4, sticky="w")

        self.select_folder_button = ttk.Button(
            controls_card,
            text="폴더 불러오기",
            style="Secondary.TButton",
            command=self.select_folder,
        )
        self.select_folder_button.grid(row=0, column=1, padx=(0, 8), pady=4, sticky="w")

        self.clear_selection_button = ttk.Button(
            controls_card,
            text="선택 초기화",
            style="Secondary.TButton",
            command=self.clear_selection,
        )
        self.clear_selection_button.grid(row=0, column=2, padx=(0, 18), pady=4, sticky="w")

        self.build_index_button = ttk.Button(
            controls_card,
            text="인덱스 생성",
            style="Primary.TButton",
            command=self.build_index,
        )
        self.build_index_button.grid(row=0, column=3, padx=(0, 0), pady=4, sticky="w")

        tk.Label(
            controls_card,
            textvariable=self.selection_summary_var,
            bg=SURFACE_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(12, 0))

        search_card = tk.Frame(
            main_frame,
            bg=SURFACE_BG,
            padx=18,
            pady=16,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        search_card.pack(fill="x", pady=(0, 18))
        search_card.grid_columnconfigure(1, weight=1)

        tk.Label(
            search_card,
            text="텍스트 쿼리",
            bg=SURFACE_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 10, "bold"),
        ).grid(row=0, column=0, padx=(0, 10), pady=4, sticky="w")

        self.query_entry = ttk.Entry(search_card, textvariable=self.query_var)
        self.query_entry.grid(row=0, column=1, sticky="ew", pady=4)
        self.query_entry.bind("<Return>", self.on_query_return)

        self.search_button = ttk.Button(
            search_card,
            text="유사 이미지 검색",
            style="Primary.TButton",
            command=self.search_images,
        )
        self.search_button.grid(row=0, column=2, padx=(12, 0), pady=4, sticky="e")

        tk.Label(
            search_card,
            text=f"인덱스는 {DEFAULT_INDEX_PATH} 경로에 JSON으로 저장됩니다.",
            bg=SURFACE_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 0))

        content_frame = tk.Frame(main_frame, bg=APP_BG)
        content_frame.pack(fill="both", expand=True)
        content_frame.grid_columnconfigure(0, weight=5)
        content_frame.grid_columnconfigure(1, weight=7)
        content_frame.grid_rowconfigure(0, weight=1)

        left_panel = tk.Frame(content_frame, bg=APP_BG)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        right_panel = tk.Frame(content_frame, bg=APP_BG)
        right_panel.grid(row=0, column=1, sticky="nsew")

        self._build_index_panel(left_panel)
        self._build_result_panel(right_panel)

        tk.Label(
            main_frame,
            textvariable=self.status_var,
            bg=STATUS_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 10),
            anchor="w",
            padx=12,
            pady=10,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        ).pack(fill="x", pady=(16, 0))

    def _build_index_panel(self, parent: tk.Frame) -> None:
        index_card = tk.Frame(
            parent,
            bg=SURFACE_BG,
            padx=16,
            pady=16,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        index_card.pack(fill="both", expand=True)

        tk.Label(
            index_card,
            text="인덱스된 이미지",
            bg=SURFACE_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 15, "bold"),
        ).pack(anchor="w")

        tk.Label(
            index_card,
            textvariable=self.index_meta_var,
            bg=SURFACE_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
            justify="left",
            wraplength=360,
        ).pack(anchor="w", pady=(4, 12))

        self.index_overview = scrolledtext.ScrolledText(
            index_card,
            wrap=tk.WORD,
            font=("Helvetica", 10),
            bg="#fffdfa",
            fg=TEXT_COLOR,
            relief="flat",
            highlightthickness=0,
            padx=12,
            pady=12,
            spacing1=2,
            spacing3=6,
        )
        self.index_overview.pack(fill="both", expand=True)

    def _build_result_panel(self, parent: tk.Frame) -> None:
        preview_card = tk.Frame(
            parent,
            bg=SURFACE_BG,
            padx=16,
            pady=16,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        preview_card.pack(fill="both", expand=False)

        tk.Label(
            preview_card,
            textvariable=self.result_title_var,
            bg=SURFACE_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 15, "bold"),
        ).pack(anchor="w")

        tk.Label(
            preview_card,
            textvariable=self.result_meta_var,
            bg=SURFACE_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
            justify="left",
            wraplength=520,
        ).pack(anchor="w", pady=(4, 12))

        self.result_image_holder = tk.Frame(preview_card, bg=PANEL_BG, height=320)
        self.result_image_holder.pack(fill="both", expand=False)
        self.result_image_holder.pack_propagate(False)

        self.result_image_label = tk.Label(
            self.result_image_holder,
            bg=PANEL_BG,
            fg=MUTED_TEXT,
            text="검색 결과 이미지가 여기에 표시됩니다.",
            font=("Helvetica", 12),
            justify="center",
            wraplength=480,
        )
        self.result_image_label.pack(fill="both", expand=True, padx=18, pady=18)

        tk.Label(
            preview_card,
            textvariable=self.result_caption_var,
            bg=SURFACE_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 10),
            justify="left",
            wraplength=520,
        ).pack(anchor="w", pady=(14, 0))

        ranking_card = tk.Frame(
            parent,
            bg=SURFACE_BG,
            padx=16,
            pady=16,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        ranking_card.pack(fill="both", expand=True, pady=(12, 0))

        tk.Label(
            ranking_card,
            text="검색 결과 순위",
            bg=SURFACE_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 15, "bold"),
        ).pack(anchor="w")

        tk.Label(
            ranking_card,
            text="상위 매칭 이미지들의 점수와 캡션 요약을 확인할 수 있습니다.",
            bg=SURFACE_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
        ).pack(anchor="w", pady=(4, 12))

        self.ranking_text = scrolledtext.ScrolledText(
            ranking_card,
            wrap=tk.WORD,
            font=("Helvetica", 10),
            bg="#fffdfa",
            fg=TEXT_COLOR,
            relief="flat",
            highlightthickness=0,
            padx=12,
            pady=12,
            spacing1=2,
            spacing3=6,
        )
        self.ranking_text.pack(fill="both", expand=True)

    def select_images(self) -> None:
        file_paths = filedialog.askopenfilenames(
            title="검색 인덱스를 만들 이미지 선택",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.webp *.gif"),
                ("All files", "*.*"),
            ],
        )
        if not file_paths:
            return

        self.selected_paths = [Path(path) for path in file_paths]
        self._update_selection_summary()
        self.status_var.set(f"인덱싱할 이미지 {len(self.selected_paths)}장을 선택했습니다.")
        self._update_action_states()

    def select_folder(self) -> None:
        directory = filedialog.askdirectory(title="검색 인덱스를 만들 이미지 폴더 선택")
        if not directory:
            return

        try:
            paths = self.search_service.discover_images_in_directory(Path(directory))
            if not paths:
                raise ValueError("선택한 폴더 안에 지원되는 이미지가 없습니다.")
        except Exception as exc:
            self.status_var.set("폴더 선택 중 오류가 발생했습니다.")
            messagebox.showerror("오류", str(exc))
            return

        self.selected_paths = paths
        self._update_selection_summary()
        self.status_var.set(f"폴더에서 이미지 {len(self.selected_paths)}장을 불러왔습니다.")
        self._update_action_states()

    def clear_selection(self) -> None:
        self.selected_paths = []
        self._update_selection_summary()
        self.status_var.set("인덱싱할 이미지 선택을 초기화했습니다.")
        self._update_action_states()

    def build_index(self) -> None:
        if self._is_busy():
            return
        if not self.selected_paths:
            self.status_var.set("먼저 인덱싱할 이미지를 선택하세요.")
            messagebox.showerror("입력 오류", "이미지 또는 이미지 폴더를 먼저 선택하세요.")
            return

        image_paths_snapshot = list(self.selected_paths)
        self.is_indexing = True
        self._update_action_states()
        self.index_meta_var.set(
            "선택한 이미지들에 대해 Vision 설명 생성과 임베딩 계산을 진행하고 있습니다. 이미지 수에 따라 시간이 걸릴 수 있습니다."
        )
        self.status_var.set("인덱스를 생성 중입니다...")
        self._set_index_overview("캡션과 임베딩을 생성 중입니다.\n잠시만 기다려 주세요.")
        self._set_ranking_text("새 인덱스를 생성하는 동안 검색 결과가 잠시 비활성화됩니다.")
        self._clear_result_preview()

        worker = threading.Thread(
            target=self._build_index_worker,
            args=(image_paths_snapshot,),
            daemon=True,
        )
        worker.start()

    def _build_index_worker(self, image_paths: list[Path]) -> None:
        try:
            index = self.search_service.build_and_save_index(image_paths, DEFAULT_INDEX_PATH)
        except Exception as exc:
            self.after(0, self._handle_index_error, str(exc))
            return

        self.after(0, self._apply_index_result, index)

    def _apply_index_result(self, index: ImageSearchIndex) -> None:
        self.index = index
        self.is_indexing = False
        self._refresh_index_overview()
        self._set_ranking_text(
            "인덱스 생성이 완료되었습니다.\n\n"
            "이제 텍스트 쿼리를 입력하고 '유사 이미지 검색' 버튼을 눌러 결과를 확인하세요."
        )
        self.status_var.set(f"이미지 {len(index.entries)}장에 대한 인덱스 생성이 완료되었습니다.")
        self._update_action_states()

    def _handle_index_error(self, error_message: str) -> None:
        self.is_indexing = False
        self._update_action_states()
        self.status_var.set("인덱스 생성 중 오류가 발생했습니다.")
        self.index_meta_var.set("인덱스 생성에 실패했습니다. 선택한 이미지와 API 설정을 다시 확인해 주세요.")
        self._set_index_overview("인덱스 생성에 실패했습니다.")
        messagebox.showerror("오류", error_message)

    def search_images(self) -> None:
        if self._is_busy():
            return

        query = self.query_var.get().strip()
        if not query:
            self.status_var.set("검색어를 입력하세요.")
            self.query_entry.focus_set()
            return

        if self.index is None:
            try:
                self.index = self.search_service.load_index(DEFAULT_INDEX_PATH)
                self._refresh_index_overview()
            except Exception as exc:
                self.status_var.set("검색 가능한 인덱스가 없습니다.")
                messagebox.showerror("오류", str(exc))
                return

        self.is_searching = True
        self._update_action_states()
        self.status_var.set(f"'{query}'와 가장 유사한 이미지를 검색 중입니다.")
        self.result_meta_var.set("저장된 이미지 설명 임베딩과 텍스트 쿼리 임베딩의 유사도를 계산하고 있습니다.")
        self._set_ranking_text("유사도 계산 중입니다.\n잠시만 기다려 주세요.")

        worker = threading.Thread(
            target=self._search_worker,
            args=(query, self.index),
            daemon=True,
        )
        worker.start()

    def _search_worker(self, query: str, index: ImageSearchIndex) -> None:
        try:
            results = self.search_service.search(query, index, top_k=5)
        except Exception as exc:
            self.after(0, self._handle_search_error, str(exc))
            return

        self.after(0, self._apply_search_results, query, results)

    def _apply_search_results(self, query: str, results: list[SearchResult]) -> None:
        self.is_searching = False
        self._update_action_states()

        if not results:
            self.status_var.set("검색 결과가 없습니다.")
            self._clear_result_preview()
            self._set_ranking_text("검색 결과가 없습니다.")
            return

        best_result = results[0]
        self._show_result_preview(best_result, query)
        self._set_ranking_text(self._format_results(results))
        self.status_var.set(
            f"'{query}'와 가장 유사한 이미지로 {best_result.entry.file_name}을(를) 찾았습니다."
        )

    def _handle_search_error(self, error_message: str) -> None:
        self.is_searching = False
        self._update_action_states()
        self.status_var.set("검색 중 오류가 발생했습니다.")
        self.result_meta_var.set("검색 중 오류가 발생했습니다. 쿼리와 인덱스를 다시 확인해 주세요.")
        self._set_ranking_text("검색에 실패했습니다.")
        messagebox.showerror("오류", error_message)

    def _show_result_preview(self, result: SearchResult, query: str) -> None:
        image_path = result.entry.path
        preview_photo = self._create_preview_photo(image_path)
        self.result_photo = preview_photo

        if preview_photo is not None:
            self.result_image_label.configure(image=preview_photo, text="")
        else:
            self.result_image_label.configure(image="", text="이 이미지는 미리보기를 표시할 수 없습니다.")

        self.result_title_var.set(f"Best Match: {result.entry.file_name}")
        self.result_meta_var.set(
            f"쿼리: '{query}'\n유사도 점수: {result.score:.4f}\n경로: {image_path}"
        )
        self.result_caption_var.set(f"저장된 이미지 설명:\n{result.entry.caption}")

    def _clear_result_preview(self) -> None:
        self.result_photo = None
        self.result_image_label.configure(
            image="",
            text="검색 결과 이미지가 여기에 표시됩니다.",
        )
        self.result_title_var.set("검색 결과 미리보기")
        self.result_meta_var.set("텍스트 쿼리를 입력하면 가장 유사한 이미지를 이곳에 표시합니다.")
        self.result_caption_var.set("이미지 캡션과 유사도 점수가 여기에 표시됩니다.")

    def _create_preview_photo(self, image_path: Path) -> Optional[ImageTk.PhotoImage]:
        try:
            with Image.open(image_path) as image:
                normalized = ImageOps.exif_transpose(image)
                if normalized.mode not in ("RGB", "RGBA"):
                    normalized = normalized.convert("RGBA")
                copied = normalized.copy()
        except Exception:
            return None

        copied.thumbnail((520, 300), RESAMPLE)
        return ImageTk.PhotoImage(copied)

    def _refresh_index_overview(self) -> None:
        if self.index is None or not self.index.entries:
            self.index_meta_var.set("저장된 인덱스가 없습니다.")
            self._set_index_overview("아직 인덱싱된 이미지가 없습니다.")
            return

        self.index_meta_var.set(
            f"총 {len(self.index.entries)}장의 이미지가 인덱싱되어 있습니다.\n"
            f"캡션 모델: {self.index.caption_model} | 임베딩 모델: {self.index.embedding_model}\n"
            f"저장 파일: {DEFAULT_INDEX_PATH}"
        )
        lines: list[str] = []
        for index_number, entry in enumerate(self.index.entries, start=1):
            lines.append(f"{index_number}. {entry.file_name}")
            lines.append(f"경로: {entry.image_path}")
            lines.append(f"설명: {entry.caption}")
            lines.append("")
        self._set_index_overview("\n".join(lines).strip())

    def _set_index_overview(self, text: str) -> None:
        self.index_overview.configure(state="normal")
        self.index_overview.delete("1.0", tk.END)
        self.index_overview.insert(tk.END, text)
        self.index_overview.configure(state="disabled")

    def _set_ranking_text(self, text: str) -> None:
        self.ranking_text.configure(state="normal")
        self.ranking_text.delete("1.0", tk.END)
        self.ranking_text.insert(tk.END, text)
        self.ranking_text.configure(state="disabled")

    def _format_results(self, results: list[SearchResult]) -> str:
        lines: list[str] = []
        for rank, result in enumerate(results, start=1):
            lines.append(f"{rank}. {result.entry.file_name}  |  score={result.score:.4f}")
            lines.append(f"설명: {result.entry.caption}")
            lines.append(f"경로: {result.entry.image_path}")
            lines.append("")
        return "\n".join(lines).strip()

    def _update_selection_summary(self) -> None:
        if not self.selected_paths:
            self.selection_summary_var.set(
                "아직 인덱싱할 이미지가 선택되지 않았습니다. "
                f"새 인덱스를 생성하면 {DEFAULT_INDEX_PATH.name} 파일로 저장됩니다."
            )
            return

        self.selection_summary_var.set(
            f"현재 {len(self.selected_paths)}장의 이미지가 인덱싱 대상으로 선택되어 있습니다. "
            "인덱스 생성 시 각 이미지 설명과 임베딩이 저장됩니다."
        )

    def _load_saved_index_if_exists(self) -> None:
        if not DEFAULT_INDEX_PATH.exists():
            self.index = None
            self.index_meta_var.set(
                f"저장된 인덱스가 없습니다. 새로 생성하면 {DEFAULT_INDEX_PATH} 경로에 저장됩니다."
            )
            self.status_var.set("이미지를 선택해 인덱스를 생성한 뒤 검색하세요.")
            return

        try:
            self.index = self.search_service.load_index(DEFAULT_INDEX_PATH)
        except Exception as exc:
            self.index = None
            self.index_meta_var.set(f"저장된 인덱스를 불러오지 못했습니다: {exc}")
            self.status_var.set("저장된 인덱스를 읽지 못했습니다. 새 인덱스를 생성해 주세요.")
            self._set_index_overview("저장된 인덱스를 읽지 못했습니다.")
            return

        self._refresh_index_overview()
        self.status_var.set(f"저장된 이미지 인덱스 {len(self.index.entries)}장을 불러왔습니다.")

    def _is_busy(self) -> bool:
        return self.is_indexing or self.is_searching

    def _update_action_states(self) -> None:
        busy = self._is_busy()
        button_state = "disabled" if busy else "normal"

        self.select_images_button.configure(state=button_state)
        self.select_folder_button.configure(state=button_state)
        self.clear_selection_button.configure(
            state="disabled" if busy or not self.selected_paths else "normal"
        )
        self.build_index_button.configure(
            state="disabled" if busy or not self.selected_paths else "normal"
        )
        self.search_button.configure(
            state="disabled" if busy or self.index is None else "normal"
        )
        self.query_entry.configure(state="disabled" if busy else "normal")

    def on_query_return(self, _event: tk.Event) -> str:
        self.search_images()
        return "break"


class PaperClusterTab(tk.Frame):
    def __init__(self, master: tk.Misc, clustering_service: PaperClusteringService) -> None:
        super().__init__(master, bg=APP_BG)
        self.clustering_service = clustering_service

        self.selected_paths: list[Path] = []
        self.result: Optional[PaperClusteringResult] = None
        self.plot_photo: Optional[ImageTk.PhotoImage] = None
        self.is_clustering = False

        self.cluster_count_var = tk.IntVar(value=2)
        self.selection_summary_var = tk.StringVar(
            value="PDF 논문을 선택하면 제목 추정, 임베딩 생성, K-Means 클러스터링을 진행합니다."
        )
        self.cluster_meta_var = tk.StringVar(
            value="아직 클러스터링 결과가 없습니다. PDF를 선택하고 클러스터 수를 지정하세요."
        )
        self.plot_title_var = tk.StringVar(value="클러스터 시각화")
        self.plot_meta_var = tk.StringVar(
            value="PCA 2D 시각화가 생성되면 이 영역에서 군집 분포를 확인할 수 있습니다."
        )
        self.status_var = tk.StringVar(value="PDF 논문을 선택한 뒤 클러스터링을 실행하세요.")

        self._build_ui()
        self._set_cluster_output(
            "클러스터 결과가 여기에 표시됩니다.\n\n"
            "왼쪽에는 클러스터별 논문 목록과 제목이, 오른쪽 아래에는 논문별 요약 미리보기가 표시됩니다."
        )
        self._set_document_output(
            "논문별 세부 정보가 여기에 표시됩니다.\n\n"
            "클러스터링이 완료되면 각 논문의 제목, 파일명, 추출 텍스트 일부를 확인할 수 있습니다."
        )
        self._clear_plot_preview()
        self._update_action_states()

    def _build_ui(self) -> None:
        main_frame = tk.Frame(self, bg=APP_BG, padx=8, pady=14)
        main_frame.pack(fill="both", expand=True)

        header_frame = tk.Frame(main_frame, bg=APP_BG)
        header_frame.pack(fill="x", pady=(0, 16))

        tk.Label(
            header_frame,
            text="PDF 논문 의미 기반 클러스터링",
            bg=APP_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 21, "bold"),
        ).pack(anchor="w")

        tk.Label(
            header_frame,
            text="PDF에서 텍스트를 추출하고 임베딩을 만든 뒤, 의미적으로 비슷한 논문끼리 클러스터링합니다.",
            bg=APP_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 11),
        ).pack(anchor="w", pady=(6, 0))

        controls_card = tk.Frame(
            main_frame,
            bg=SURFACE_BG,
            padx=18,
            pady=16,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        controls_card.pack(fill="x", pady=(0, 18))

        self.select_pdfs_button = ttk.Button(
            controls_card,
            text="PDF 선택",
            style="Secondary.TButton",
            command=self.select_pdfs,
        )
        self.select_pdfs_button.grid(row=0, column=0, padx=(0, 8), pady=4, sticky="w")

        self.select_folder_button = ttk.Button(
            controls_card,
            text="폴더 불러오기",
            style="Secondary.TButton",
            command=self.select_folder,
        )
        self.select_folder_button.grid(row=0, column=1, padx=(0, 8), pady=4, sticky="w")

        self.clear_button = ttk.Button(
            controls_card,
            text="선택 초기화",
            style="Secondary.TButton",
            command=self.clear_selection,
        )
        self.clear_button.grid(row=0, column=2, padx=(0, 18), pady=4, sticky="w")

        tk.Label(
            controls_card,
            text="클러스터 수",
            bg=SURFACE_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 10, "bold"),
        ).grid(row=0, column=3, padx=(0, 8), pady=4, sticky="e")

        self.cluster_spinbox = tk.Spinbox(
            controls_card,
            from_=1,
            to=20,
            textvariable=self.cluster_count_var,
            width=6,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            bg="#fffdfa",
            fg=TEXT_COLOR,
        )
        self.cluster_spinbox.grid(row=0, column=4, padx=(0, 18), pady=4, sticky="w")

        self.cluster_button = ttk.Button(
            controls_card,
            text="클러스터링 실행",
            style="Primary.TButton",
            command=self.run_clustering,
        )
        self.cluster_button.grid(row=0, column=5, pady=4, sticky="w")

        tk.Label(
            controls_card,
            textvariable=self.selection_summary_var,
            bg=SURFACE_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
            justify="left",
            wraplength=900,
        ).grid(row=1, column=0, columnspan=6, sticky="w", pady=(12, 0))

        content_frame = tk.Frame(main_frame, bg=APP_BG)
        content_frame.pack(fill="both", expand=True)
        content_frame.grid_columnconfigure(0, weight=6)
        content_frame.grid_columnconfigure(1, weight=6)
        content_frame.grid_rowconfigure(0, weight=1)

        left_panel = tk.Frame(content_frame, bg=APP_BG)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        right_panel = tk.Frame(content_frame, bg=APP_BG)
        right_panel.grid(row=0, column=1, sticky="nsew")

        self._build_cluster_result_panel(left_panel)
        self._build_plot_panel(right_panel)
        self._build_document_panel(right_panel)

        tk.Label(
            main_frame,
            textvariable=self.status_var,
            bg=STATUS_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 10),
            anchor="w",
            padx=12,
            pady=10,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        ).pack(fill="x", pady=(16, 0))

    def _build_cluster_result_panel(self, parent: tk.Frame) -> None:
        result_card = tk.Frame(
            parent,
            bg=SURFACE_BG,
            padx=16,
            pady=16,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        result_card.pack(fill="both", expand=True)

        tk.Label(
            result_card,
            text="클러스터 결과",
            bg=SURFACE_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 15, "bold"),
        ).pack(anchor="w")

        tk.Label(
            result_card,
            textvariable=self.cluster_meta_var,
            bg=SURFACE_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
            justify="left",
            wraplength=440,
        ).pack(anchor="w", pady=(4, 12))

        self.cluster_output = scrolledtext.ScrolledText(
            result_card,
            wrap=tk.WORD,
            font=("Helvetica", 10),
            bg="#fffdfa",
            fg=TEXT_COLOR,
            relief="flat",
            highlightthickness=0,
            padx=12,
            pady=12,
            spacing1=2,
            spacing3=6,
        )
        self.cluster_output.pack(fill="both", expand=True)

    def _build_plot_panel(self, parent: tk.Frame) -> None:
        plot_card = tk.Frame(
            parent,
            bg=SURFACE_BG,
            padx=16,
            pady=16,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        plot_card.pack(fill="both", expand=False)

        tk.Label(
            plot_card,
            textvariable=self.plot_title_var,
            bg=SURFACE_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 15, "bold"),
        ).pack(anchor="w")

        tk.Label(
            plot_card,
            textvariable=self.plot_meta_var,
            bg=SURFACE_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
            justify="left",
            wraplength=520,
        ).pack(anchor="w", pady=(4, 12))

        self.plot_holder = tk.Frame(plot_card, bg=PANEL_BG, height=320)
        self.plot_holder.pack(fill="both", expand=False)
        self.plot_holder.pack_propagate(False)

        self.plot_label = tk.Label(
            self.plot_holder,
            bg=PANEL_BG,
            fg=MUTED_TEXT,
            text="클러스터 시각화 이미지가 여기에 표시됩니다.",
            font=("Helvetica", 12),
            justify="center",
            wraplength=480,
        )
        self.plot_label.pack(fill="both", expand=True, padx=18, pady=18)

    def _build_document_panel(self, parent: tk.Frame) -> None:
        document_card = tk.Frame(
            parent,
            bg=SURFACE_BG,
            padx=16,
            pady=16,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        document_card.pack(fill="both", expand=True, pady=(12, 0))

        tk.Label(
            document_card,
            text="논문별 세부 정보",
            bg=SURFACE_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 15, "bold"),
        ).pack(anchor="w")

        tk.Label(
            document_card,
            text=f"시각화 파일은 {DEFAULT_CLUSTER_PLOT_PATH} 경로에 저장됩니다.",
            bg=SURFACE_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 10),
        ).pack(anchor="w", pady=(4, 12))

        self.document_output = scrolledtext.ScrolledText(
            document_card,
            wrap=tk.WORD,
            font=("Helvetica", 10),
            bg="#fffdfa",
            fg=TEXT_COLOR,
            relief="flat",
            highlightthickness=0,
            padx=12,
            pady=12,
            spacing1=2,
            spacing3=6,
        )
        self.document_output.pack(fill="both", expand=True)

    def select_pdfs(self) -> None:
        file_paths = filedialog.askopenfilenames(
            title="클러스터링할 PDF 논문 선택",
            filetypes=[
                ("PDF files", "*.pdf"),
                ("All files", "*.*"),
            ],
        )
        if not file_paths:
            return

        self.selected_paths = [Path(path) for path in file_paths]
        self._update_selection_summary()
        self.status_var.set(f"클러스터링할 PDF 논문 {len(self.selected_paths)}편을 선택했습니다.")
        self._update_action_states()

    def select_folder(self) -> None:
        directory = filedialog.askdirectory(title="PDF 논문 폴더 선택")
        if not directory:
            return

        try:
            paths = self.clustering_service.discover_pdfs_in_directory(Path(directory))
            if not paths:
                raise ValueError("선택한 폴더 안에 PDF 논문이 없습니다.")
        except Exception as exc:
            self.status_var.set("폴더 선택 중 오류가 발생했습니다.")
            messagebox.showerror("오류", str(exc))
            return

        self.selected_paths = paths
        self._update_selection_summary()
        self.status_var.set(f"폴더에서 PDF 논문 {len(self.selected_paths)}편을 불러왔습니다.")
        self._update_action_states()

    def clear_selection(self) -> None:
        self.selected_paths = []
        self._update_selection_summary()
        self.status_var.set("선택한 PDF 논문 목록을 초기화했습니다.")
        self._update_action_states()

    def run_clustering(self) -> None:
        if self.is_clustering:
            return

        if not self.selected_paths:
            self.status_var.set("먼저 PDF 논문을 선택하세요.")
            messagebox.showerror("입력 오류", "PDF 논문 파일이나 폴더를 먼저 선택하세요.")
            return

        try:
            cluster_count = int(self.cluster_count_var.get())
        except Exception:
            self.status_var.set("클러스터 수를 확인하세요.")
            messagebox.showerror("입력 오류", "클러스터 수는 정수여야 합니다.")
            return

        if cluster_count < 1 or cluster_count > len(self.selected_paths):
            self.status_var.set("클러스터 수를 다시 지정하세요.")
            messagebox.showerror(
                "입력 오류",
                f"클러스터 수는 1 이상, 선택한 논문 수({len(self.selected_paths)}) 이하여야 합니다.",
            )
            return

        pdf_paths_snapshot = list(self.selected_paths)
        self.is_clustering = True
        self._update_action_states()
        self.cluster_meta_var.set(
            "PDF 텍스트 추출, 임베딩 생성, K-Means 클러스터링을 순서대로 진행하고 있습니다."
        )
        self.status_var.set("논문 클러스터링을 실행 중입니다...")
        self._set_cluster_output("논문 텍스트를 추출하고 임베딩을 생성 중입니다.\n잠시만 기다려 주세요.")
        self._set_document_output("논문 정보를 준비 중입니다.")
        self._clear_plot_preview()

        worker = threading.Thread(
            target=self._cluster_worker,
            args=(pdf_paths_snapshot, cluster_count),
            daemon=True,
        )
        worker.start()

    def _cluster_worker(self, pdf_paths: list[Path], cluster_count: int) -> None:
        try:
            result = self.clustering_service.cluster_papers(
                pdf_paths=pdf_paths,
                cluster_count=cluster_count,
                plot_path=DEFAULT_CLUSTER_PLOT_PATH,
            )
        except Exception as exc:
            self.after(0, self._handle_clustering_error, str(exc))
            return

        self.after(0, self._apply_clustering_result, result)

    def _apply_clustering_result(self, result: PaperClusteringResult) -> None:
        self.result = result
        self.is_clustering = False
        self._update_action_states()
        self.cluster_meta_var.set(
            f"총 {len(result.documents)}편의 논문을 {result.cluster_count}개 클러스터로 분류했습니다.\n"
            f"임베딩 모델: {result.embedding_model}"
        )
        self._set_cluster_output(self._format_cluster_output(result))
        self._set_document_output(self._format_document_output(result))
        self._show_plot_preview(result.plot_path)
        self.status_var.set(
            f"논문 {len(result.documents)}편의 클러스터링이 완료되었습니다."
        )

    def _handle_clustering_error(self, error_message: str) -> None:
        self.is_clustering = False
        self._update_action_states()
        self.cluster_meta_var.set("클러스터링 중 오류가 발생했습니다. PDF 파일과 환경 설정을 다시 확인해 주세요.")
        self.status_var.set("클러스터링 중 오류가 발생했습니다.")
        self._set_cluster_output("클러스터링에 실패했습니다.")
        self._set_document_output("논문 정보를 표시할 수 없습니다.")
        messagebox.showerror("오류", error_message)

    def _format_cluster_output(self, result: PaperClusteringResult) -> str:
        cluster_map: dict[int, list[str]] = {}
        for document in result.documents:
            label = document.cluster_label or 0
            cluster_map.setdefault(label, []).append(document.title)

        lines: list[str] = [
            f"[클러스터 수] {result.cluster_count}",
            f"[문서 수] {len(result.documents)}",
            "",
        ]
        for label in sorted(cluster_map):
            lines.append(f"Cluster {label + 1}")
            for title in cluster_map[label]:
                lines.append(f"- {title}")
            lines.append("")
        return "\n".join(lines).strip()

    def _format_document_output(self, result: PaperClusteringResult) -> str:
        lines: list[str] = []
        for index, document in enumerate(result.documents, start=1):
            label = (document.cluster_label or 0) + 1
            lines.append(f"{index}. {document.title}")
            lines.append(f"클러스터: Cluster {label}")
            lines.append(f"파일명: {document.file_name}")
            lines.append(f"경로: {document.pdf_path}")
            lines.append(f"미리보기: {document.preview_text}")
            lines.append("")
        return "\n".join(lines).strip()

    def _show_plot_preview(self, plot_path: str | None) -> None:
        if not plot_path:
            self._clear_plot_preview()
            self.plot_meta_var.set(
                "시각화를 만들 수 있는 조건이 충분하지 않아 텍스트 결과만 표시했습니다."
            )
            return

        try:
            with Image.open(plot_path) as image:
                copied = image.copy()
        except Exception:
            self._clear_plot_preview()
            self.plot_meta_var.set("시각화 파일을 불러오지 못했습니다.")
            return

        copied.thumbnail((520, 300), RESAMPLE)
        self.plot_photo = ImageTk.PhotoImage(copied)
        self.plot_label.configure(image=self.plot_photo, text="")
        self.plot_title_var.set("클러스터 시각화")
        self.plot_meta_var.set(f"PCA 2D 시각화 결과를 표시합니다.\n파일: {plot_path}")

    def _clear_plot_preview(self) -> None:
        self.plot_photo = None
        self.plot_label.configure(
            image="",
            text="클러스터 시각화 이미지가 여기에 표시됩니다.",
        )
        self.plot_title_var.set("클러스터 시각화")
        self.plot_meta_var.set(
            "PCA 2D 시각화가 생성되면 이 영역에서 군집 분포를 확인할 수 있습니다."
        )

    def _set_cluster_output(self, text: str) -> None:
        self.cluster_output.configure(state="normal")
        self.cluster_output.delete("1.0", tk.END)
        self.cluster_output.insert(tk.END, text)
        self.cluster_output.configure(state="disabled")

    def _set_document_output(self, text: str) -> None:
        self.document_output.configure(state="normal")
        self.document_output.delete("1.0", tk.END)
        self.document_output.insert(tk.END, text)
        self.document_output.configure(state="disabled")

    def _update_selection_summary(self) -> None:
        if not self.selected_paths:
            self.selection_summary_var.set(
                "PDF 논문을 선택하면 제목 추정, 임베딩 생성, K-Means 클러스터링을 진행합니다."
            )
            return

        self.selection_summary_var.set(
            f"현재 {len(self.selected_paths)}편의 PDF 논문이 선택되어 있습니다. "
            "클러스터 수를 지정한 뒤 실행하면 논문 제목과 클러스터 결과를 함께 출력합니다."
        )

    def _update_action_states(self) -> None:
        button_state = "disabled" if self.is_clustering else "normal"

        self.select_pdfs_button.configure(state=button_state)
        self.select_folder_button.configure(state=button_state)
        self.clear_button.configure(
            state="disabled" if self.is_clustering or not self.selected_paths else "normal"
        )
        self.cluster_button.configure(
            state="disabled" if self.is_clustering or not self.selected_paths else "normal"
        )
        self.cluster_spinbox.configure(state="disabled" if self.is_clustering else "normal")


class CreativeStudioApp:
    def __init__(
        self,
        root: tk.Tk,
        story_generator: StoryGenerator,
        historical_chatbot: HistoricalChatbot,
        image_search_service: SemanticImageSearchService,
        paper_clustering_service: PaperClusteringService,
    ) -> None:
        self.root = root
        self.story_generator = story_generator
        self.historical_chatbot = historical_chatbot
        self.image_search_service = image_search_service
        self.paper_clustering_service = paper_clustering_service

        self.root.title("이미지 스토리 & 역사 인물 대화 스튜디오")
        self.root.geometry("1280x840")
        self.root.minsize(1120, 760)
        self.root.configure(bg=APP_BG)

        self._configure_styles()
        self._build_ui()

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", font=("Helvetica", 11))
        style.configure(
            "Primary.TButton",
            font=("Helvetica", 11, "bold"),
            padding=(16, 11),
            foreground="white",
            background=ACCENT,
            borderwidth=0,
        )
        style.map(
            "Primary.TButton",
            background=[("disabled", "#b9c9c5"), ("active", "#174845")],
            foreground=[("disabled", "#f7f7f7")],
        )
        style.configure(
            "Secondary.TButton",
            font=("Helvetica", 11, "bold"),
            padding=(14, 10),
            foreground=TEXT_COLOR,
            background=ACCENT_SOFT,
            borderwidth=0,
        )
        style.map(
            "Secondary.TButton",
            background=[("disabled", "#ebe5da"), ("active", "#c9e1dc")],
            foreground=[("disabled", "#9ba4a2")],
        )
        style.configure("TCombobox", padding=6)
        style.configure("App.TNotebook", background=APP_BG, borderwidth=0)
        style.configure(
            "App.TNotebook.Tab",
            font=("Helvetica", 11, "bold"),
            padding=(18, 10),
            background=ACCENT_SOFT,
            foreground=TEXT_COLOR,
        )
        style.map(
            "App.TNotebook.Tab",
            background=[("selected", SURFACE_BG), ("active", "#e7efec")],
            foreground=[("selected", ACCENT)],
        )

    def _build_ui(self) -> None:
        main_frame = tk.Frame(self.root, bg=APP_BG, padx=24, pady=22)
        main_frame.pack(fill="both", expand=True)

        header_frame = tk.Frame(main_frame, bg=APP_BG)
        header_frame.pack(fill="x", pady=(0, 16))

        tk.Label(
            header_frame,
            text="이미지 스토리 & 역사 인물 대화 스튜디오",
            bg=APP_BG,
            fg=TEXT_COLOR,
            font=("Helvetica", 24, "bold"),
        ).pack(anchor="w")

        tk.Label(
            header_frame,
            text="Practice3, Practice4, Practice5, Practice6 과제를 하나의 탭형 GUI에서 실행할 수 있도록 통합했습니다.",
            bg=APP_BG,
            fg=MUTED_TEXT,
            font=("Helvetica", 11),
        ).pack(anchor="w", pady=(6, 0))

        notebook = ttk.Notebook(main_frame, style="App.TNotebook")
        notebook.pack(fill="both", expand=True)

        story_tab = StoryTab(notebook, self.story_generator)
        chat_tab = HistoricalChatTab(notebook, self.historical_chatbot)
        image_search_tab = ImageSearchTab(notebook, self.image_search_service)
        paper_cluster_tab = PaperClusterTab(notebook, self.paper_clustering_service)

        notebook.add(story_tab, text="이미지 스토리")
        notebook.add(chat_tab, text="역사 인물 챗봇")
        notebook.add(image_search_tab, text="이미지 검색")
        notebook.add(paper_cluster_tab, text="논문 클러스터링")


def main() -> None:
    root = tk.Tk()
    try:
        client = create_openai_client()
        story_generator = StoryGenerator(client=client, model=DEFAULT_STORY_MODEL)
        historical_chatbot = HistoricalChatbot(client=client, model=DEFAULT_CHAT_MODEL)
        image_search_service = SemanticImageSearchService(
            client=client,
            caption_model=DEFAULT_CAPTION_MODEL,
            embedding_model=DEFAULT_EMBEDDING_MODEL,
        )
        paper_clustering_service = PaperClusteringService(
            client=client,
            embedding_model=DEFAULT_PAPER_EMBEDDING_MODEL,
        )
    except Exception as exc:
        root.withdraw()
        messagebox.showerror("환경 설정 오류", str(exc))
        root.destroy()
        return

    CreativeStudioApp(
        root,
        story_generator,
        historical_chatbot,
        image_search_service,
        paper_clustering_service,
    )
    root.mainloop()


if __name__ == "__main__":
    main()
