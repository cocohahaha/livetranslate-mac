"""faster-whisper 语音识别：自动检测中/英（支持逐句语言切换）。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from faster_whisper import WhisperModel

from .config import AsrConfig

# 把 Whisper 可能给出的近邻语言归并到中文，避免粤语/日语误判导致翻译方向错乱
_ZH_ALIASES = {"zh", "yue"}


@dataclass
class AsrResult:
    text: str
    language: str  # "zh" / "en" / 其他 ISO 代码
    probability: float


class Recognizer:
    def __init__(self, cfg: AsrConfig):
        self.cfg = cfg
        self.model = WhisperModel(cfg.model, device="cpu", compute_type=cfg.compute_type)

    def transcribe(self, audio: np.ndarray) -> AsrResult | None:
        segments, info = self.model.transcribe(
            audio,
            language=None,
            beam_size=1,
            initial_prompt="以下是简体中文普通话或英文的办公对话。",
            condition_on_previous_text=False,
            vad_filter=False,
        )
        text = "".join(seg.text for seg in segments).strip()
        if not text:
            return None
        lang = info.language
        if lang in _ZH_ALIASES:
            lang = "zh"
        # 中英场景下以文本字符为准做二次校正：CJK 字符占比高即视为中文，
        # 比 Whisper 的声学语言检测在中英混说时更稳
        if set(self.cfg.languages) == {"zh", "en"}:
            cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
            lang = "zh" if cjk >= max(1, len(text) * 0.2) else "en"
        elif self.cfg.languages and lang not in self.cfg.languages:
            lang = self.cfg.languages[0]
        return AsrResult(text=text, language=lang, probability=info.language_probability)
