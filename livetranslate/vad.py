"""基于 Silero VAD（faster-whisper 内置 ONNX 模型）的流式断句器。

维护一个滚动音频缓冲区，周期性地在整段缓冲上跑 VAD：
- 末尾静音超过 min_silence_ms → 把已检出的语音区间切成一句话发出；
- 语音持续超过 max_utterance_s → 强制切断，避免长句迟迟不出字幕。
"""

from __future__ import annotations

import numpy as np
from faster_whisper.vad import VadOptions, get_speech_timestamps

from .config import VadConfig

SAMPLE_RATE = 16000
PAD_SAMPLES = int(0.15 * SAMPLE_RATE)  # 切句时前后各留 150ms，避免吞字


class StreamingSegmenter:
    def __init__(self, cfg: VadConfig):
        self.cfg = cfg
        self.buffer = np.zeros(0, dtype=np.float32)
        self._since_check = 0
        self._check_every = int(0.25 * SAMPLE_RATE)
        self._vad_options = VadOptions(
            threshold=cfg.threshold,
            min_speech_duration_ms=cfg.min_speech_ms,
            min_silence_duration_ms=min(cfg.min_silence_ms, 400),
        )

    def feed(self, chunk: np.ndarray) -> list[np.ndarray]:
        """喂入一块音频，返回零个或多个完整句子的音频片段。"""
        self.buffer = np.concatenate([self.buffer, chunk])
        self._since_check += len(chunk)
        if self._since_check < self._check_every:
            return []
        self._since_check = 0
        return self._scan()

    def _scan(self) -> list[np.ndarray]:
        buf_len = len(self.buffer)
        segments = get_speech_timestamps(self.buffer, vad_options=self._vad_options)
        if not segments:
            # 无语音：只保留尾部 1 秒，防止缓冲无限增长
            keep = SAMPLE_RATE
            if buf_len > keep:
                self.buffer = self.buffer[-keep:]
            return []

        min_silence = int(self.cfg.min_silence_ms / 1000 * SAMPLE_RATE)
        max_utt = int(self.cfg.max_utterance_s * SAMPLE_RATE)
        first_start = segments[0]["start"]
        last_end = segments[-1]["end"]

        ended = (buf_len - last_end) >= min_silence
        too_long = (buf_len - first_start) >= max_utt
        if not (ended or too_long):
            return []

        start = max(0, first_start - PAD_SAMPLES)
        end = min(buf_len, last_end + PAD_SAMPLES)
        utterance = self.buffer[start:end].copy()
        self.buffer = self.buffer[end:]
        return [utterance]
