"""悬浮字幕条：PyQt6 无边框半透明置顶窗口。

- 冷色磨砂玻璃样式：上行原文（带语言标签）、下行译文，可拖动
- 右上角「历史」打开/关闭历史记录窗口，✕ 退出
- 历史窗口可滚动、可复制文本
"""

from __future__ import annotations

from html import escape

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .config import OverlayConfig

# 冷色调色板：纸白 / 冰蓝 / 冰川蓝 / 主蓝 / 墨色
PAPER = "#F6F9FB"
ICE = "#E6EEF3"
GLACIER = "#9DBCCD"
BLUE = "#3D6D8B"
SLATE = "#5E7F94"
INK = "#1C2832"

# 中英文都清楚的无衬线字体，按平台依次回退
FONT_FAMILIES = ["PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei",
                 "Noto Sans CJK SC", "Segoe UI", "Helvetica Neue"]


def lang_tag(lang: str) -> str:
    """语言标签：替代国旗 emoji（Windows 上国旗 emoji 只显示成字母）。"""
    return "中 → EN" if lang == "zh" else "EN → 中"


def make_font(point_size: int, weight: QFont.Weight) -> QFont:
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSize(point_size)
    font.setWeight(weight)
    return font


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
        self.browser.setFont(make_font(13, QFont.Weight.Normal))
        self.browser.setStyleSheet(
            f"QTextBrowser {{ background: {PAPER}; color: {INK}; border: none;"
            f" padding: 14px 18px; selection-background-color: {GLACIER}; }}"
        )
        self.setStyleSheet(f"background: {PAPER};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
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
            parts.append(
                f"<p style='margin:0 0 14px 0'>"
                f"<span style='color:{BLUE}; font-size:11px; font-weight:600'>{lang_tag(e['lang'])}</span><br>"
                f"<span style='color:{SLATE}'>{escape(e['text'])}</span><br>"
                f"<span style='color:{INK}; font-weight:600'>{escape(e['trans'] or '…')}</span></p>"
            )
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

        # 顶部一行：左侧语言标签，右侧 历史 + 关闭
        self.lbl_tag = QLabel("")
        self.lbl_tag.setFont(make_font(max(9, round(cfg.font_size * 0.5)), QFont.Weight.DemiBold))
        self.lbl_tag.setStyleSheet(
            f"color: {BLUE}; background: {ICE}; border: 1px solid rgba(157, 188, 205, 140);"
            " border-radius: 9px; padding: 1px 8px;"
        )
        self.lbl_tag.hide()

        btn_history = QPushButton("历史")
        btn_close = QPushButton("✕")
        for btn in (btn_history, btn_close):
            btn.setFixedHeight(24)
            btn.setFont(make_font(12, QFont.Weight.Medium))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ color: {SLATE}; background: transparent; border: none;"
                " border-radius: 12px; padding: 0 9px; }"
                f"QPushButton:hover {{ color: {INK}; background: rgba(61, 109, 139, 26); }}"
            )
        btn_close.setFixedWidth(26)
        btn_history.setToolTip("查看历史记录")
        btn_close.setToolTip("退出")
        btn_history.clicked.connect(self._toggle_history)
        btn_close.clicked.connect(QApplication.instance().quit)

        topbar = QHBoxLayout()
        topbar.setSpacing(2)
        topbar.addWidget(self.lbl_tag)
        topbar.addStretch(1)
        topbar.addWidget(btn_history)
        topbar.addWidget(btn_close)

        self.lbl_original = QLabel("已启动，请开始说话…")
        self.lbl_translation = QLabel("")
        for lbl, color, size, weight in (
            (self.lbl_original, SLATE, max(10, round(cfg.font_size * 0.8)), QFont.Weight.Normal),
            (self.lbl_translation, INK, cfg.font_size, QFont.Weight.DemiBold),
        ):
            lbl.setWordWrap(True)
            lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lbl.setFont(make_font(size, weight))
            lbl.setStyleSheet(f"color: {color}; background: transparent;")

        container = QFrame(self)
        container.setObjectName("glass")
        container.setStyleSheet(
            "QFrame#glass { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 rgba(250, 252, 253, 245), stop:1 rgba(236, 243, 247, 240));"
            " border: 1px solid rgba(157, 188, 205, 170); border-radius: 16px; }"
        )
        shadow = QGraphicsDropShadowEffect(container)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(34, 70, 92, 60))
        container.setGraphicsEffect(shadow)

        inner = QVBoxLayout(container)
        inner.setContentsMargins(18, 10, 12, 16)
        inner.setSpacing(6)
        inner.addLayout(topbar)
        inner.addWidget(self.lbl_original)
        inner.addWidget(self.lbl_translation)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 10, 16, 22)  # 给柔和阴影留出位置
        outer.addWidget(container)

        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(cfg.width, 150)
        self.move((screen.width() - cfg.width) // 2, screen.height() - 250)

        bridge.original.connect(self._on_original)
        bridge.translation.connect(self._on_translation)

    def _fit(self):
        """宽度不变，高度贴合换行后的文字（避免字幕条下方留出空白）。"""
        layout = self.layout()
        width = self.width()
        height = layout.heightForWidth(width) if layout.hasHeightForWidth() else -1
        self.resize(width, height if height > 0 else self.sizeHint().height())

    def _toggle_history(self):
        if self.history.isVisible():
            self.history.hide()
        else:
            self.history.show()
            self.history.raise_()

    def _on_original(self, seq: int, text: str, lang: str):
        self._latest_seq = seq
        self.lbl_tag.setText(lang_tag(lang))
        self.lbl_tag.show()
        self.lbl_original.setText(text)
        self.lbl_translation.setText("…")
        self._fit()
        self.history.add_original(seq, text, lang)

    def _on_translation(self, seq: int, text: str):
        # 只把最新一句的译文显示在字幕条上，旧句的译文进历史
        if seq == self._latest_seq:
            self.lbl_translation.setText(text)
            self._fit()
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
