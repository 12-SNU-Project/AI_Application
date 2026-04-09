from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChatTurn:
    role: str
    text: str


@dataclass
class ChatReply:
    reply_text: str
    figure_name: str
    used_model: str
