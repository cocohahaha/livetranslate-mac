#!/bin/zsh
# 离线全链路自测：用 macOS `say` 合成中英文语音 → 识别 → 翻译
# 用法: tests/run_e2e.sh
set -e
cd "$(dirname "$0")/.."
TMP=$(mktemp -d)
say -o "$TMP/en.aiff" "Our deployment pipeline failed because the staging environment ran out of disk space."
say -v "Flo (Chinese (China mainland))" -o "$TMP/zh.aiff" "这个需求的优先级比较高，我们需要在这个迭代里完成灰度发布。"
for f in en zh; do
  echo "=== $f ==="
  .venv/bin/livetranslate --file "$TMP/$f.aiff"
done
rm -rf "$TMP"
