"""语音识别引擎。

- sensevoice（默认）：阿里 SenseVoice-small（sherpa-onnx 运行时），中文准确率
  显著高于 whisper-small，CPU 上速度快一个数量级，支持中英及语种自动检测。
- whisper：faster-whisper，模型可选 tiny~large，多语言场景的兜底。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

from .config import AsrConfig

# 把近邻语言归并到中文，避免粤语误判导致翻译方向错乱
_ZH_ALIASES = {"zh", "yue"}

_SENSEVOICE_REPO = "csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"


def _hf_download(repo: str, patterns: list[str] | None = None) -> str:
    """模型托管在 HuggingFace：先直连，失败再走国内镜像 hf-mirror。"""
    from huggingface_hub import snapshot_download

    try:
        return snapshot_download(repo, allow_patterns=patterns)
    except Exception:
        print("[init] HuggingFace 直连失败，改用 hf-mirror 镜像重试…")
        return snapshot_download(repo, allow_patterns=patterns, endpoint="https://hf-mirror.com")


@dataclass
class AsrResult:
    text: str
    language: str  # "zh" / "en" / 其他 ISO 代码
    probability: float


def _correct_language(text: str, lang: str, languages: list[str]) -> str:
    if lang in _ZH_ALIASES:
        lang = "zh"
    # 中英场景下以文本字符为准做二次校正：CJK 字符占比高即视为中文，
    # 比声学语言检测在中英混说时更稳
    if set(languages) == {"zh", "en"}:
        cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
        return "zh" if cjk >= max(1, len(text) * 0.2) else "en"
    if languages and lang not in languages:
        return languages[0]
    return lang


class WhisperRecognizer:
    def __init__(self, cfg: AsrConfig):
        from faster_whisper import WhisperModel

        self.cfg = cfg
        threads = max(4, (os.cpu_count() or 8) // 2)
        try:
            self.model = WhisperModel(
                cfg.model, device="cpu", compute_type=cfg.compute_type, cpu_threads=threads
            )
        except Exception:
            path = _hf_download(f"Systran/faster-whisper-{cfg.model}")
            self.model = WhisperModel(
                path, device="cpu", compute_type=cfg.compute_type, cpu_threads=threads
            )

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
        lang = _correct_language(text, info.language, self.cfg.languages)
        return AsrResult(text=text, language=lang, probability=info.language_probability)


class SenseVoiceRecognizer:
    def __init__(self, cfg: AsrConfig):
        import sherpa_onnx

        self.cfg = cfg
        model_dir = self._ensure_model()
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(model_dir / "model.int8.onnx"),
            tokens=str(model_dir / "tokens.txt"),
            num_threads=max(4, (os.cpu_count() or 8) // 2),
            use_itn=True,
            language="auto",
        )

    @staticmethod
    def _ensure_model():
        from pathlib import Path

        return Path(_hf_download(_SENSEVOICE_REPO, ["model.int8.onnx", "tokens.txt"]))

    def transcribe(self, audio: np.ndarray) -> AsrResult | None:
        stream = self.recognizer.create_stream()
        stream.accept_waveform(16000, audio)
        self.recognizer.decode_stream(stream)
        text = stream.result.text.strip()
        if not text:
            return None
        lang = stream.result.lang.strip("<|>") or "zh"
        lang = _correct_language(text, lang, self.cfg.languages)
        return AsrResult(text=text, language=lang, probability=1.0)


def make_recognizer(cfg: AsrConfig):
    if cfg.engine == "whisper":
        return WhisperRecognizer(cfg)
    return SenseVoiceRecognizer(cfg)
