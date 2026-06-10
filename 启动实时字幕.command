#!/bin/zsh
# 双击此文件即可启动实时字幕（屏幕下方出现悬浮字幕条）
# 退出方式：右键点击字幕条选"退出"，或直接关闭这个终端窗口

export PATH="/opt/homebrew/bin:$PATH"
cd "$(dirname "${0:A}")"

echo "================================"
echo "  实时中英双语字幕 启动中…"
echo "================================"

# 翻译服务（Ollama）没在运行就拉起来
if ! curl -s --max-time 2 http://localhost:11434 >/dev/null; then
  echo "正在启动本地翻译服务，请稍候…"
  nohup ollama serve >/dev/null 2>&1 &
  for i in {1..30}; do
    curl -s --max-time 1 http://localhost:11434 >/dev/null && break
    sleep 1
  done
fi

echo "字幕条即将出现在屏幕下方，请开始对话。"
echo "（第一句话的翻译可能要等十几秒预热，之后就是秒级响应）"
exec .venv/bin/livetranslate
