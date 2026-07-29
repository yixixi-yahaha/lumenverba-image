---
name: lumenverba-image
description: Use when the user asks to generate images with Lumenverba, including text-to-image, reference-image generation, Chinese posters, characters, illustrations, or images containing specified readable text.
---

# Lumenverba 绘图

使用本技能同级 `scripts/lumenverba_image.py` 直接调用 Lumenverba 图像 API。执行前先从当前 `SKILL.md` 的实际位置推导技能目录；不得使用固定的本机绝对路径，也不调用旧 MCP 服务。

## 调用规则

- 文生图使用 `generate --prompt`。
- 参考图生图使用 `edit --prompt --reference <绝对图片路径>`；可重复传入多个 `--reference`。
- 指定文字生图使用 `text --text --description`，并把文字语言、位置和样式传给 `--language`、`--position`、`--style`。
- 直接执行同级 `scripts/lumenverba_image.py`；不得使用 `python -c`、内联 Python 或动态拼接 Python 源码。
- 在 PowerShell 中，把提示词、指定文字和描述等动态文本参数放在单引号内；参数内容中的单引号写成两个单引号。例如 `--text 'O''Reilly 夏日$特惠'`。`$`、反引号和双引号在这种写法中会按原文传入。
- 文字生图固定使用 `text` 子命令，不要手动为指定文字添加引号；脚本会在 `build_text_prompt()` 中构造逐字准确约束。
- 执行时以技能目录中的 `scripts/lumenverba_image.py` 为脚本路径。将生成图片的绝对路径作为结果返回，并用 Markdown 图片链接展示。

## 联网权限

- 生图前必须通过命令执行工具以 `sandbox_permissions: "require_escalated"` 申请联网权限，并在说明中告知用户该请求会访问 `https://api.lumenverba.cc/v1` 生成图片。
- 用户批准联网权限后再运行脚本；不要先在受限沙箱中调用并等待失败后才请求授权。
- 若用户拒绝授权或脚本返回 `WinError 10013`，说明请求在本机网络策略中被拦截、尚未到达 Lumenverba API。明确提示用户在允许联网的 Codex 会话中重试；不要要求更换或粘贴密钥。

## 参数选择

用户明确指定的 `model`、`size`、`quality` 优先，原样传递。未指定时按以下规则选择：

| 参数 | 默认 | 关键词与场景 |
| --- | --- | --- |
| `model` | `gpt-image-2` | 默认模型；可选 `gpt-image-1`、`gpt-image-1.5`、`gpt-image-2`。 |
| `size` | `1536x1024` | `1024x1024` 用于方图、1:1、头像、单品、图标；`1536x1024` 用于横图、宽幅、风景、场景、多人、电影感；`1024x1536` 用于竖图、竖版、海报、全身、手机壁纸、书封。 |
| `quality` | `standard` | `low` 用于草图、快速、分镜、试构图；`standard` 用于常规、通用、日常；`high` 用于高质量、精细、主视觉、细节、文字清晰。 |

`1536x1024` 为 3:2，不是严格的 16:9。用户只要求 16:9 而未给出实际 `size` 时，说明该可选尺寸中最接近的是 `1536x1024`。

## 提示词

提示词应包含主体、场景、媒介或风格、构图、光线和限制。除非用户另有要求，加入“无水印、无标志、无界面”。

文字生图必须写明文字内容需要逐字准确、清晰可读、完整显示，且不得添加未要求的文字。脚本会加入这一约束；对于正式海报或包含大量文字的画面，优先选择 `high`。

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
