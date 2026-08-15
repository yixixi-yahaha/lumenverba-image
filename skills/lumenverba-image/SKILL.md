---
name: lumenverba-image
description: Use when the user asks to generate images with Lumenverba, including text-to-image, reference-image generation, Chinese posters, characters, illustrations, or images containing specified readable text.
---

# Lumenverba 绘图

使用本技能同级 `scripts/lumenverba_image.py` 直接调用 Lumenverba 图像 API。执行前先从当前 `SKILL.md` 的实际位置推导技能目录；不得使用固定的本机绝对路径，也不调用旧 MCP 服务。

## 专用边界

- 仅在用户明确要求使用 Lumenverba 时调用本技能；通用绘图请求使用原生 Image-Gen。
- 透明背景、抠图或 Alpha 通道验证需求使用原生 Image-Gen，不为本技能增加后处理流程。

## 调用规则

- 先从当前 `SKILL.md` 推导技能目录和同级脚本路径；此阶段不得联网。
- 先确认 `python --version` 可执行且不低于 3.11；否则在 Codex Desktop 调用 `load_workspace_dependencies`，使用其返回的 Python executable。不得读取脚本源码或猜测替代命令。
- 确定子命令、`--model`、`--size`、`--quality`、数量和 `--output-dir` 后，才为该最终命令申请一次联网权限。
- 文生图使用 `generate --prompt`。
- 参考图生图使用 `edit --prompt --reference <绝对图片路径>`；可重复传入多个 `--reference`。
- 指定文字生图使用 `text --text --description`，并把文字语言、位置和样式传给 `--language`、`--position`、`--style`。
- 直接执行同级 `scripts/lumenverba_image.py`；不得使用 `python -c`、内联 Python 或动态拼接 Python 源码。
- 在 PowerShell 中，把提示词、指定文字和描述等动态文本参数放在单引号内；参数内容中的单引号写成两个单引号。例如 `--text 'O''Reilly 夏日$特惠'`。`$`、反引号和双引号在这种写法中会按原文传入。
- 文字生图固定使用 `text` 子命令，不要手动为指定文字添加引号；脚本会在 `build_text_prompt()` 中构造逐字准确约束。
- 执行时以技能目录中的 `scripts/lumenverba_image.py` 为脚本路径。脚本成功时 stdout 只返回生成 PNG 的绝对路径；失败诊断和重试提示写入 stderr。脚本仅对 `DNS 解析失败`、`TLS 连接失败`、`连接被拒绝`、`代理连接失败`自动重试 1 次；`网络连接超时`、连接中途关闭、通用网络失败和生成状态未知不自动重试。

## 快速执行

- 用户在同一条指令中明确要求多张图片，即构成整批生成授权；不得逐张重复确认。
- 同一提示词生成多个版本时，在 `generate`、`text` 或 `edit` 后传 `--count 1..10`。
- 多个不同提示词使用一次 `batch` 命令，并为每项重复传入 `--prompt`；每批最多 4 项。
- 普通文生图与参考图编辑原样传递用户提示词，不复述、不扩写、不补充创意元素。
- `text` 只由脚本追加固定的逐字准确约束。
- 参数和输出目录确定后直接执行一个最终命令，不先描述构图方案。

## 结果交付

- 仅在命令进程退出且已取得完整 stdout、stderr 后，才能判断生成数量、批次状态或失败原因。
- 未取得命令完成输出时，只回复“当前命令的完成输出尚未取得，执行状态未知，正在等待该命令结束。”；不得扫描输出目录、按文件数量或时间戳推断成功数，也不得报告部分失败。
- 成功图片只以 stdout 中的 PNG 绝对路径为准。命令完成后，stdout 路径数少于请求数量或退出码非零时，才依据 stderr 简要报告部分失败或失败原因。
- stdout 中的每一行都是成功 PNG 的绝对路径；逐张用 Markdown 图片链接展示。
- 若 stderr 包含 `RETRY_NOTICE:` 且 stdout 包含成功 PNG，先展示全部成功图片，再附注“首次失败原因：<安全分类>；自动重试一次后成功。”；不得把该提示当作批次失败。
- stderr 中的批次项错误只做简要报告；部分失败时仍展示全部成功图片。
- 只校验返回数量、PNG、绝对路径和批次状态，不得进行视觉检查。
- 不得自动调整提示词、重新生成、在脚本之外重试创建请求或把单请求多图改为并发单图。

## 参数选择

用户明确指定的 `model`、`size`、`quality` 优先，原样传递。未指定时按以下规则选择：

| 参数 | 默认 | 关键词与场景 |
| --- | --- | --- |
| `model` | `gpt-image-2` | 默认模型；可选 `gpt-image-1`、`gpt-image-1.5`、`gpt-image-2`。 |
| `size` | `1536x1024` | `1024x1024` 用于方图、1:1、头像、单品、图标；`1536x1024` 用于横图、宽幅、风景、场景、多人、电影感；`1024x1536` 用于竖图、竖版、海报、全身、手机壁纸、书封。 |
| `quality` | `standard` | `low` 用于草图、快速、分镜、试构图；`standard` 用于常规、通用、日常；`high` 用于高质量、精细、主视觉、细节、文字清晰。 |

`1536x1024` 为 3:2，不是严格的 16:9。用户只要求 16:9 而未给出实际 `size` 时，说明该可选尺寸中最接近的是 `1536x1024`。

## 缺少密钥

若脚本返回“未设置 LUMENVERBA_API_KEY 环境变量”，不要让用户在聊天中粘贴密钥，也不要显示或记录密钥。只回复以下 PowerShell 代码块，并提示用户完全退出并重新打开 Codex 后重试：

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$secureKey = Read-Host "请输入 Lumenverba API 密钥" -AsSecureString
$plainKey = [System.Net.NetworkCredential]::new("", $secureKey).Password
[Environment]::SetEnvironmentVariable("LUMENVERBA_API_KEY", $plainKey, "User")
Remove-Variable plainKey
Write-Host "配置完成。请完全退出并重新打开 Codex，然后重新发送生图请求。"
```

API 地址固定为 `https://api.lumenverba.cc/v1`，不要求用户配置 URL。
