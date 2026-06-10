"""翻译：OpenAI 兼容接口（DeepSeek/OpenAI 等），或本机 Ollama 原生接口。

中文 → 英文，其他语言 → 中文。
检测到 Ollama 时走原生 /api/chat 并传 think:false —— qwen3 等推理模型在
OpenAI 兼容接口下无法关闭思考模式，一句翻译会偷偷生成数千推理 token。
"""

from __future__ import annotations

import re

import requests

from .config import TranslationConfig

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

_SYSTEM_PROMPT = (
    "You are a professional simultaneous interpreter for office conversations. "
    "Translate the user's sentence: if it is Chinese, translate to natural English; "
    "otherwise translate to natural Simplified Chinese. "
    "Keep technical terms accurate. Output ONLY the translation, nothing else."
)


class Translator:
    def __init__(self, cfg: TranslationConfig):
        self.cfg = cfg
        self.session = requests.Session()
        self._root = cfg.base_url.rstrip("/").removesuffix("/v1")
        self._is_ollama: bool | None = None

    def _detect_ollama(self) -> bool:
        if self._is_ollama is None:
            try:
                resp = self.session.get(self._root, timeout=3)
                self._is_ollama = "ollama" in resp.text.lower()
            except Exception:
                self._is_ollama = False
        return self._is_ollama

    def _messages(self, text: str, source_lang: str) -> list[dict]:
        target = "English" if source_lang == "zh" else "Simplified Chinese"
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Translate to {target}:\n{text}"},
        ]

    def translate(self, text: str, source_lang: str) -> str | None:
        try:
            if self._detect_ollama():
                content = self._call_ollama(self._messages(text, source_lang))
            else:
                content = self._call_openai(self._messages(text, source_lang))
            return _THINK_RE.sub("", content).strip()
        except Exception as exc:  # 网络/接口异常不应中断字幕流
            return f"[翻译失败: {exc.__class__.__name__}]"

    def _call_ollama(self, messages: list[dict]) -> str:
        resp = self.session.post(
            f"{self._root}/api/chat",
            json={
                "model": self.cfg.model,
                "messages": messages,
                "think": False,
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout=self.cfg.timeout_s,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def _call_openai(self, messages: list[dict]) -> str:
        resp = self.session.post(
            f"{self.cfg.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.cfg.api_key}"},
            json={
                "model": self.cfg.model,
                "messages": messages,
                "temperature": 0.2,
                "stream": False,
            },
            timeout=self.cfg.timeout_s,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def warmup(self):
        """预加载翻译模型（Ollama 冷启动可能要 1-2 分钟），后台静默执行。"""
        try:
            self.translate("你好", "zh")
            print("[init] 翻译模型预热完成")
        except Exception:
            pass

    def check(self) -> bool:
        """启动时连通性自检；本机 Ollama 没在运行时尝试自动拉起。"""
        try:
            if self._detect_ollama():
                return True
            resp = self.session.get(
                f"{self.cfg.base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {self.cfg.api_key}"},
                timeout=5,
            )
            return resp.ok
        except Exception:
            pass
        if self._try_start_ollama():
            self._is_ollama = None
            return self._detect_ollama()
        return False

    def _try_start_ollama(self) -> bool:
        """配置指向本机 Ollama 端口但服务没起来时，替用户启动它。"""
        import os
        import shutil
        import subprocess
        import time

        if "localhost:11434" not in self.cfg.base_url and "127.0.0.1:11434" not in self.cfg.base_url:
            return False
        exe = shutil.which("ollama") or next(
            (p for p in ("/opt/homebrew/bin/ollama", "/usr/local/bin/ollama") if os.path.exists(p)),
            None,
        )
        if not exe:
            return False
        print("[init] 正在自动启动 Ollama 翻译服务…")
        subprocess.Popen(
            [exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        for _ in range(15):
            time.sleep(1)
            try:
                if self.session.get(self._root, timeout=2).ok:
                    return True
            except Exception:
                continue
        return False
