"""悬浮字幕条：PyQt6 无边框半透明置顶窗口，上行原文、下行译文，可拖动。"""

from __future__ import annotations

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QVBoxLayout, QWidget

from .config import OverlayConfig


class SubtitleBridge(QObject):
    """跨线程更新字幕用的信号桥（worker 线程 emit，主线程刷新 UI）。"""

    original = pyqtSignal(str, str)  # (text, lang)
    translation = pyqtSignal(str)


class SubtitleOverlay(QWidget):
    def __init__(self, cfg: OverlayConfig, bridge: SubtitleBridge):
        super().__init__()
        self.cfg = cfg
        self._drag_pos = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(cfg.opacity)

        self.lbl_original = QLabel("🎤 livetranslate-mac 已启动，请开始说话…")
        self.lbl_translation = QLabel("")
        for lbl, color, weight in (
            (self.lbl_original, "#c8c8c8", QFont.Weight.Normal),
            (self.lbl_translation, "#ffffff", QFont.Weight.Bold),
        ):
            lbl.setWordWrap(True)
            lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            font = QFont()
            font.setPointSize(cfg.font_size)
            font.setWeight(weight)
            lbl.setFont(font)
            lbl.setStyleSheet(f"color: {color}; background: transparent;")

        container = QWidget(self)
        container.setStyleSheet("background: rgba(20, 20, 24, 200); border-radius: 14px;")
        inner = QVBoxLayout(container)
        inner.setContentsMargins(24, 14, 24, 14)
        inner.addWidget(self.lbl_original)
        inner.addWidget(self.lbl_translation)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(cfg.width, 120)
        self.move((screen.width() - cfg.width) // 2, screen.height() - 220)

        bridge.original.connect(self._on_original)
        bridge.translation.connect(self._on_translation)

    def _on_original(self, text: str, lang: str):
        flag = "🇨🇳" if lang == "zh" else "🇬🇧"
        self.lbl_original.setText(f"{flag} {text}")
        self.lbl_translation.setText("…")
        self.adjustSize()

    def _on_translation(self, text: str):
        self.lbl_translation.setText(text)
        self.adjustSize()

    # --- 拖动与右键菜单 ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)
        menu.exec(event.globalPos())
