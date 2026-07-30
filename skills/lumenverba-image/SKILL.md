---
name: lumenverba-image
description: Use when the user asks to generate images with Lumenverba, including text-to-image, reference-image generation, Chinese posters, characters, illustrations, or images containing specified readable text.
---

# Lumenverba 绘图

使用本技能同级 `scripts/lumenverba_image.py` 直接调用 Lumenverba 图像 API。执行前先从当前 `SKILL.md` 的实际位置推导技能目录，再得到脚本路径；不得使用固定的本机绝对路径，也不调用旧 MCP 服务。

先在离线环境检查系统 Python 是否为 3.11 或更高版本。系统 Python 不可用时，调用 `load_workspace_dependencies`，使用其返回的 Python 解释器执行该脚本。不得猜测解释器路径。

## 专用边界

- 仅在用户明确要求使用 Lumenverba 时调用本技能；通用绘图请求使用原生 Image-Gen。
- 透明背景、抠图或 Alpha 通道验证需求使用原生 Image-Gen，不为本技能增加后处理流程。
- 多个不同素材不批量提交；每项均需逐项确认和生成，避免未确认的计费请求。
## 调用规则

- 文生图使用 `generate --prompt`。
- 参考图生图使用 `edit --prompt --reference <绝对图片路径>`；可重复传入多个 `--reference`。
- 指定文字生图使用 `text --text --description`，并把文字语言、位置和样式传给 `--language`、`--position`、`--style`。
- 直接执行同级 `scripts/lumenverba_image.py`；不得使用 `python -c`、内联 Python 或动态拼接 Python 源码。
- 在 PowerShell 中，把提示词、指定文字和描述等动态文本参数放在单引号内；参数内容中的单引号写成两个单引号。例如 `--text 'O''Reilly 夏日$特惠'`。`$`、反引号和双引号在这种写法中会按原文传入。
- 文字生图固定使用 `text` 子命令，不要手动为指定文字添加引号；脚本会在 `build_text_prompt()` 中构造逐字准确约束。
- 执行时以技能目录中的 `scripts/lumenverba_image.py` 为脚本路径。
- 先完成提示词、`generate`、`edit` 或 `text` 子命令，以及 `--output-dir` 的确定；仅在最终命令已经确定后，申请一次联网权限并执行。不使用 `require_escalated` 参数或为其提供任何指导。
- 成功时 stdout 只能输出生成 PNG 的绝对路径；失败时仅向 stderr 输出错误并以非零状态退出。将该绝对 PNG 路径作为结果返回，并用 Markdown 图片链接展示。

## 参考图与编辑

- 对每张参考图先明确其角色：编辑目标、风格参考或构图参考；把角色和用途写入提示词，不把它们当作 API 参数。
- `edit` 请求只改变用户指定的部分，并把人物身份、姿势、服装、主体边缘、构图等需要保留的内容逐项写为不变量；缺少改动范围或保持范围时先询问用户。
## 联网权限

- 最终命令确定后才申请一次联网权限，并在说明中告知用户该请求会访问 `https://api.lumenverba.cc/v1` 生成图片。
- 用户批准联网权限后再运行脚本；不要先在受限环境中调用并等待失败后才请求授权。
- 若用户拒绝授权或脚本返回 `WinError 10013`，说明请求在本机网络策略中被拦截、尚未到达 Lumenverba API。明确提示用户在允许联网的 Codex 会话中重试；不要要求更换或粘贴密钥。
- 若出现网络异常，脚本会报告安全的原因类别和“生成状态未知”。请提示用户直接回复“允许联网”，然后重新发送该请求；不得自动重试 POST 请求。已接受的 `202` 图像任务会继续按任务地址轮询。

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

## 提示词与验收

- 请求信息不足时，使用主体、场景、风格、构图、光线、准确文字和限制补足提示词；用户已明确的内容只做结构化表达，不擅自添加创意元素。
- 始终校验返回文件为 PNG 且路径为绝对路径。指定文字、参考图编辑或明确视觉约束的请求，还应视觉检查结果是否满足文字可读性和编辑不变量。
- 首次结果不满足时，报告结果和绝对路径，等待用户明确要求调整或重试；不得自动再次生成。
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
