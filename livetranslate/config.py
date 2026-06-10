"""配置加载：首次运行时在项目根目录生成 config.yaml，之后从该文件读取。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"

DEFAULT_CONFIG_YAML = """\
# livetranslate-mac 配置文件
audio:
  device: null          # 输入设备名称或序号，null 表示系统默认麦克风（--list-devices 查看）
  sample_rate: 16000

vad:
  threshold: 0.5        # Silero VAD 语音判定阈值
  min_silence_ms: 500   # 静音超过该时长则切断一句
  max_utterance_s: 12   # 单句最长秒数，超过强制切断
  min_speech_ms: 250    # 短于该时长的语音片段丢弃

asr:
  model: small          # faster-whisper 模型：tiny/base/small/medium/large-v3
  compute_type: int8    # Apple Silicon CPU 推荐 int8
  languages: [zh, en]   # 限定自动检测的语言范围，留空 [] 表示不限

translation:
  enabled: true
  base_url: http://localhost:11434/v1   # OpenAI 兼容接口；默认指向本机 Ollama
  api_key: ollama                        # Ollama 随意填；商业 API 填真实 key 或设 LT_API_KEY 环境变量
  model: qwen2.5:3b
  timeout_s: 60

overlay:
  enabled: true
  font_size: 22
  width: 900
  opacity: 0.85
"""


@dataclass
class AudioConfig:
    device: str | int | None = None
    sample_rate: int = 16000


@dataclass
class VadConfig:
    threshold: float = 0.5
    min_silence_ms: int = 500
    max_utterance_s: float = 12.0
    min_speech_ms: int = 250


@dataclass
class AsrConfig:
    model: str = "small"
    compute_type: str = "int8"
    languages: list[str] = field(default_factory=lambda: ["zh", "en"])


@dataclass
class TranslationConfig:
    enabled: bool = True
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    model: str = "qwen2.5:3b"
    timeout_s: float = 60.0


@dataclass
class OverlayConfig:
    enabled: bool = True
    font_size: int = 22
    width: int = 900
    opacity: float = 0.85


@dataclass
class Config:
    audio: AudioConfig = field(default_factory=AudioConfig)
    vad: VadConfig = field(default_factory=VadConfig)
    asr: AsrConfig = field(default_factory=AsrConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)


def load_config(path: Path | None = None) -> Config:
    path = path or DEFAULT_CONFIG_PATH
    if not path.exists():
        path.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    cfg = Config(
        audio=AudioConfig(**raw.get("audio", {})),
        vad=VadConfig(**raw.get("vad", {})),
        asr=AsrConfig(**raw.get("asr", {})),
        translation=TranslationConfig(**raw.get("translation", {})),
        overlay=OverlayConfig(**raw.get("overlay", {})),
    )
    env_key = os.environ.get("LT_API_KEY")
    if env_key:
        cfg.translation.api_key = env_key
    return cfg
