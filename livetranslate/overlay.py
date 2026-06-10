"""悬浮字幕条：PyQt6 无边框半透明置顶窗口。

- 上行原文、下行译文，可拖动
- 右上角 ✕ 退出、🕘 打开/关闭历史记录窗口
- 历史窗口可滚动、可复制文本
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .config import OverlayConfig


class SubtitleBridge(QObject):
    """跨线程更新字幕用的信号桥（worker 线程 emit，主线程刷新 UI）。"""

    original = pyqtSignal(int, str, str)  # (seq, text, lang)
    translation = pyqtSignal(int, str)  # (seq, text)


class HistoryWindow(QWidget):
    """字幕历史：普通窗口（自带标题栏和关闭按钮），可滚动、可复制。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("字幕历史")
        self.resize(560, 480)
        self.browser = QTextBrowser()
        self.browser.setStyleSheet("font-size: 14px;")
        layout = QVBoxLayout(self)
        layout.addWidget(self.browser)
        self.entries: dict[int, dict] = {}

    def add_original(self, seq: int, text: str, lang: str):
        self.entries[seq] = {"lang": lang, "text": text, "trans": None}
        self._render()

    def add_translation(self, seq: int, text: str):
        if seq in self.entries:
            self.entries[seq]["trans"] = text
            self._render()

    def _render(self):
        parts = []
        for seq in sorted(self.entries):
            e = self.entries[seq]
            flag = "🇨🇳" if e["lang"] == "zh" else "🇬🇧"
            parts.append(f"<p style='margin:6px 0'>{flag} {e['text']}<br>"
                         f"<b style='color:#0a5'>↳ {e['trans'] or '…'}</b></p>")
        self.browser.setHtml("".join(parts))
        self.browser.verticalScrollBar().setValue(
            self.browser.verticalScrollBar().maximum()
        )


class SubtitleOverlay(QWidget):
    def __init__(self, cfg: OverlayConfig, bridge: SubtitleBridge):
        super().__init__()
        self.cfg = cfg
        self._drag_pos = None
        self._latest_seq = 0
        self.history = HistoryWindow()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(cfg.opacity)

        # 顶部按钮行：历史 + 关闭
        btn_history = QPushButton("🕘")
        btn_close = QPushButton("✕")
        for btn in (btn_history, btn_close):
            btn.setFixedSize(26, 26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { color: #aaa; background: transparent; border: none;"
                " font-size: 15px; }"
                "QPushButton:hover { color: #fff; background: rgba(255,255,255,40);"
                " border-radius: 13px; }"
            )
        btn_history.setToolTip("查看历史记录")
        btn_close.setToolTip("退出")
        btn_history.clicked.connect(self._toggle_history)
        btn_close.clicked.connect(QApplication.instance().quit)

        topbar = QHBoxLayout()
        topbar.addStretch(1)
        topbar.addWidget(btn_history)
        topbar.addWidget(btn_close)

        self.lbl_original = QLabel("🎤 已启动，请开始说话…")
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
        inner.setContentsMargins(18, 6, 18, 14)
        inner.addLayout(topbar)
        inner.addWidget(self.lbl_original)
        inner.addWidget(self.lbl_translation)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(cfg.width, 130)
        self.move((screen.width() - cfg.width) // 2, screen.height() - 230)

        bridge.original.connect(self._on_original)
        bridge.translation.connect(self._on_translation)

    def _toggle_history(self):
        if self.history.isVisible():
            self.history.hide()
        else:
            self.history.show()
            self.history.raise_()

    def _on_original(self, seq: int, text: str, lang: str):
        self._latest_seq = seq
        flag = "🇨🇳" if lang == "zh" else "🇬🇧"
        self.lbl_original.setText(f"{flag} {text}")
        self.lbl_translation.setText("…")
        self.adjustSize()
        self.history.add_original(seq, text, lang)

    def _on_translation(self, seq: int, text: str):
        # 只把最新一句的译文显示在字幕条上，旧句的译文进历史
        if seq == self._latest_seq:
            self.lbl_translation.setText(text)
            self.adjustSize()
        self.history.add_translation(seq, text)

    # --- 拖动 ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def closeEvent(self, event):
        QApplication.instance().quit()
