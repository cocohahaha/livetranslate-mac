"""主程序：麦克风 → VAD 断句 → ASR → 翻译 → 悬浮字幕 / 终端输出。"""

from __future__ import annotations

import argparse
import queue
import signal
import sys
import threading
import time
from pathlib import Path

from .asr import Recognizer
from .audio import MicCapture, list_input_devices
from .config import Config, load_config
from .translator import Translator
from .vad import StreamingSegmenter


class Pipeline:
    """识别与翻译两条线程解耦：翻译慢时不阻塞下一句话的识别。"""

    def __init__(self, cfg: Config, on_original, on_translation):
        self.cfg = cfg
        self.on_original = on_original  # (seq, text, lang)
        self.on_translation = on_translation  # (seq, text)
        print(f"[init] 加载 faster-whisper 模型 {cfg.asr.model}（首次运行会自动下载）…")
        self.recognizer = Recognizer(cfg.asr)
        self.translator = Translator(cfg.translation) if cfg.translation.enabled else None
        if self.translator:
            if self.translator.check():
                threading.Thread(target=self.translator.warmup, daemon=True).start()
            else:
                print(
                    f"[warn] 翻译接口 {cfg.translation.base_url} 连不通，"
                    "本次运行只显示识别字幕（本机 Ollama 请先执行 `ollama serve`）"
                )
                self.translator = None
        self.capture = MicCapture(cfg.audio)
        self.segmenter = StreamingSegmenter(cfg.vad)
        self._stop = threading.Event()
        self._seq = 0
        self._translate_queue: queue.Queue = queue.Queue()

    def handle_utterance(self, audio):
        result = self.recognizer.transcribe(audio)
        if result is None:
            return
        self._seq += 1
        seq = self._seq
        self.on_original(seq, result.text, result.language)
        print(f"[{result.language}] {result.text}")
        if self.translator:
            self._translate_queue.put((seq, result.text, result.language))

    def _asr_worker(self):
        while not self._stop.is_set():
            try:
                chunk = self.capture.chunks.get(timeout=0.5)
            except queue.Empty:
                continue
            for utterance in self.segmenter.feed(chunk):
                self.handle_utterance(utterance)

    def _translate_worker(self):
        while not self._stop.is_set():
            try:
                seq, text, lang = self._translate_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            translated = self.translator.translate(text, lang)
            if translated:
                self.on_translation(seq, translated)
                print(f"  ↳ {translated}")

    def start(self):
        self.capture.start()
        threading.Thread(target=self._asr_worker, daemon=True).start()
        if self.translator:
            threading.Thread(target=self._translate_worker, daemon=True).start()
        print("[ready] 开始拾音（macOS 首次运行需在 系统设置→隐私与安全性→麦克风 中授权终端）")

    def stop(self):
        self._stop.set()
        self.capture.stop()


def run_file_mode(cfg: Config, path: str):
    """离线模式：识别并翻译一个音频文件，用于测试与验证。"""
    from faster_whisper.audio import decode_audio

    audio = decode_audio(path, sampling_rate=16000)
    print(f"[file] {path}（{len(audio) / 16000:.1f}s）")
    done = threading.Event()
    pipeline = Pipeline(
        cfg,
        on_original=lambda *a: None if pipeline.translator else done.set(),
        on_translation=lambda *a: done.set(),
    )
    if pipeline.translator:
        threading.Thread(target=pipeline._translate_worker, daemon=True).start()
    pipeline.handle_utterance(audio)
    if pipeline.translator:
        done.wait(timeout=cfg.translation.timeout_s + 5)


def run_terminal(cfg: Config):
    pipeline = Pipeline(cfg, on_original=lambda *a: None, on_translation=lambda *a: None)
    pipeline.start()
    try:
        # 不用 signal.pause()：多线程下 SIGINT 可能落在非主线程，
        # pause() 永远不会醒；sleep 循环能让解释器及时检查信号标志
        while True:
            time.sleep(0.3)
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.stop()


def run_overlay(cfg: Config):
    from PyQt6.QtWidgets import QApplication

    from .overlay import SubtitleBridge, SubtitleOverlay

    app = QApplication(sys.argv)
    bridge = SubtitleBridge()
    overlay = SubtitleOverlay(cfg.overlay, bridge)

    pipeline = Pipeline(
        cfg,
        on_original=lambda seq, text, lang: bridge.original.emit(seq, text, lang),
        on_translation=lambda seq, text: bridge.translation.emit(seq, text),
    )
    overlay.show()
    pipeline.start()
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    # Qt 事件循环在 C 层阻塞，需要周期性回到解释器才能处理 Python 信号处理器
    from PyQt6.QtCore import QTimer

    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(200)
    code = app.exec()
    pipeline.stop()
    sys.exit(code)


def main():
    # 打包成 .app/.exe 后没有控制台，stdout 不存在时把日志写到用户目录
    if sys.stdout is None or sys.stderr is None:
        (Path.home() / ".livetranslate").mkdir(exist_ok=True)
        log = open(Path.home() / ".livetranslate" / "app.log", "a", encoding="utf-8")
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log
    sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(
        prog="livetranslate",
        description="macOS 本地实时双语字幕：中英自动识别 + 互译，悬浮字幕条显示",
    )
    parser.add_argument("--config", type=Path, default=None, help="配置文件路径（默认项目根目录 config.yaml）")
    parser.add_argument("--list-devices", action="store_true", help="列出可用的输入设备")
    parser.add_argument("--no-overlay", action="store_true", help="不显示悬浮字幕，仅终端输出")
    parser.add_argument("--no-translate", action="store_true", help="只识别不翻译")
    parser.add_argument("--device", default=None, help="输入设备名称或序号")
    parser.add_argument("--model", default=None, help="覆盖 faster-whisper 模型，如 base/small/medium")
    parser.add_argument("--file", default=None, help="离线识别+翻译一个音频文件（测试用）")
    args = parser.parse_args()

    if args.list_devices:
        print(list_input_devices())
        return

    cfg = load_config(args.config)
    if args.device is not None:
        cfg.audio.device = args.device
    if args.model is not None:
        cfg.asr.model = args.model
    if args.no_translate:
        cfg.translation.enabled = False

    if args.file:
        run_file_mode(cfg, args.file)
    elif args.no_overlay or not cfg.overlay.enabled:
        run_terminal(cfg)
    else:
        run_overlay(cfg)


if __name__ == "__main__":
    main()
