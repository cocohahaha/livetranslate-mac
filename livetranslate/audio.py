"""麦克风采集：sounddevice 回调推送 float32 单声道音频块到队列。"""

from __future__ import annotations

import queue

import numpy as np
import sounddevice as sd

from .config import AudioConfig


def list_input_devices() -> str:
    lines = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            mark = " (默认)" if idx == sd.default.device[0] else ""
            lines.append(f"  [{idx}] {dev['name']}{mark}")
    return "\n".join(lines)


class MicCapture:
    def __init__(self, cfg: AudioConfig, block_ms: int = 32):
        self.cfg = cfg
        self.blocksize = int(cfg.sample_rate * block_ms / 1000)
        self.chunks: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: sd.InputStream | None = None

    def _callback(self, indata, frames, time_info, status):
        self.chunks.put(indata[:, 0].copy())

    def start(self):
        device = self.cfg.device
        if isinstance(device, str) and device.isdigit():
            device = int(device)
        self._stream = sd.InputStream(
            device=device,
            channels=1,
            samplerate=self.cfg.sample_rate,
            blocksize=self.blocksize,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
