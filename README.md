<p><img src="packaging/icon.png" width="88" alt="LiveTranslate 图标"></p>

# livetranslate-mac

![悬浮字幕条：上行英文原文，下行中文译文](docs/hero.jpg)

<sub>示例字幕：法拉第《蜡烛的化学史》第一讲（1860，公有领域）。</sub>

macOS 本地实时双语字幕小工具：办公室与外籍同事面对面交流时，麦克风实时拾音，自动识别中文/英文（支持逐句语言切换），互译后以悬浮字幕条显示在屏幕上，帮双方对齐不理解的词汇。

架构复刻自 [TheDeathDragon/LiveTranslate](https://github.com/TheDeathDragon/LiveTranslate)（Windows 实时翻译工具，2026-06 发布），并针对 macOS 与"面对面中英对话"场景重新实现：

```
麦克风 (32ms 块) → Silero VAD 断句 → SenseVoice 本地识别（中文优化，0.1s/句，自动中英检测；可切换 whisper）
                → LLM 翻译（OpenAI 兼容接口，默认本机 Ollama）→ 悬浮字幕条 (PyQt6)
```

## 特点

- **纯本地可用**：识别默认用阿里 SenseVoice-small（中文准确率显著高于 whisper-small，M1 Pro 上 5 秒语音约 0.1 秒识别完），翻译默认走本机 Ollama（默认 `qwen2.5:3b`，小而快、中英互译质量好；不要用 qwen3 等思考型模型，实时翻译会被思考 token 拖垮），无需联网、无隐私顾虑；也可改配置接 DeepSeek/OpenAI 等任意 OpenAI 兼容 API。
- **中英自动互译**：逐句检测语言——说中文显示英文译文，说英文显示中文译文，对话中随时切换。
- **悬浮字幕条**：冷色磨砂玻璃样式的无边框置顶窗口，上行原文（带 `EN → 中` / `中 → EN` 语言标签）、下行译文，可拖动；右上角「历史」查看本次全部字幕，✕ 退出。
- **终端模式**：`--no-overlay` 仅在终端打印，适合留记录。

## 安装

```bash
git clone https://github.com/cocohahaha/livetranslate-mac.git
cd livetranslate-mac
uv venv --python 3.12 .venv
uv pip install -e . --python .venv
```

翻译默认使用本机 Ollama：

```bash
brew install ollama
ollama pull qwen2.5:3b
ollama serve   # 保持运行
```

## 使用

**非技术用户：双击项目里的 `启动实时字幕.command`（或桌面快捷方式）即可**——它会自动拉起本地翻译服务并显示悬浮字幕条；不用时右键字幕条选"退出"或关闭终端窗口。

命令行方式：

```bash
.venv/bin/livetranslate                 # 启动悬浮字幕
.venv/bin/livetranslate --no-overlay    # 仅终端输出
.venv/bin/livetranslate --list-devices  # 查看麦克风设备
.venv/bin/livetranslate --model base    # 换更小/更大的识别模型
.venv/bin/livetranslate --file demo.wav # 离线识别+翻译音频文件（测试）
```

- 首次运行会自动下载 SenseVoice 识别模型（约 250MB），HuggingFace 直连失败时自动改走 hf-mirror 镜像。配置 `asr.engine: whisper` 可切回 faster-whisper。
- macOS 首次拾音需在 **系统设置 → 隐私与安全性 → 麦克风** 中给终端授权。
- 所有参数在首次运行生成的 `config.yaml` 中调整（设备、模型、翻译接口、字幕样式等）；商业 API 的 key 也可用环境变量 `LT_API_KEY` 注入。

## 分发给同事（免安装包）

GitHub Actions 会自动打包三个平台的版本（仓库 Actions 页面手动触发 `build`，或打 `v*` tag 自动发 Release）：

| 包 | 适用 |
|---|---|
| `LiveTranslate-mac-apple-silicon.zip` | M1/M2/M3/M4 芯片的 Mac |
| `LiveTranslate-mac-intel.zip` | 2020 年以前的老款 Intel Mac |
| `LiveTranslate-windows.zip` | Windows 10/11 |

同事拿到 zip 后解压双击即可，无需装 Python。注意事项：

- **macOS**：未签名应用首次打开需 右键 → 打开（或 系统设置→隐私与安全性 里允许）；首次使用需授权麦克风。
- **Windows**：SmartScreen 提示时点"更多信息 → 仍要运行"。
- **翻译功能**：识别字幕开箱即用（首次自动下载识别模型，国内网络走 hf-mirror 镜像）；译文需要本机装 [Ollama](https://ollama.com/download)（装好后 `ollama pull qwen2.5:3b`），或在 `~/.livetranslate/config.yaml` 里填任意 OpenAI 兼容 API。没配翻译时只显示原文字幕。

## 调研背景（2026-06）

近期口碑较好的同类工具：

| 工具 | 平台 | 说明 |
|---|---|---|
| [LiveCaptions-Translator](https://github.com/SakiRinn/LiveCaptions-Translator) | Windows | 基于 Windows LiveCaptions + LLM 翻译，星数最高但依赖 Windows 系统能力 |
| [LiveTranslate](https://github.com/TheDeathDragon/LiveTranslate) | Windows | VAD + faster-whisper/SenseVoice + LLM 翻译 + 悬浮字幕，2026-06-08 最新发布，本项目的复刻蓝本 |
| [v2s](https://github.com/franklioxygen/v2s) | macOS | Apple Speech + Apple Translation 菜单栏工具，纯本地但功能较简单 |

选择复刻 LiveTranslate：架构清晰、组件全部可在 macOS 复现、翻译质量靠 LLM 保证、社区反馈最好。

## License

MIT
