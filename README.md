# Lumenverba 绘图

可安装的 Codex 技能，使用 Lumenverba 图像 API 生成图片。技能包内置仅依赖 Python 标准库的客户端，不依赖 MCP 常驻服务、本机固定路径或额外 Python 包。

## 安装

需要 Codex 和 Python 3.11 或更高版本：

### 在 Codex 对话中安装

新建一个 Codex 对话，直接发送以下内容即可，无需打开终端：

```text
请从 https://github.com/yixixi-yahaha/lumenverba-image 安装 lumenverba-image 技能。
```

安装完成后，完全退出并重新打开 Codex。

### 使用命令安装

```powershell
npx.cmd skills add yixixi-yahaha/lumenverba-image@lumenverba-image -g -y
```

安装完成后，重新打开 Codex。技能会在文生图、参考图生图、海报、角色图、插画或包含指定清晰文字的图片请求中自动启用。

## 联网授权

生成图片需要连接 Lumenverba API。首次生图时，Codex 可能会请求联网权限，请在弹出的提示中允许该请求。

若出现 `WinError 10013`，表示当前 Codex 会话的网络策略拦截了请求，图片尚未提交到 Lumenverba。请在允许联网的 Codex 会话中重新发送原请求；无需重新创建或粘贴 API 密钥。

首次生成前，可在 Codex 对话中直接发送：

```text
请使用 lumenverba-image 生成图片，并在执行前申请 Lumenverba 所需的联网权限。我会在弹出的授权提示中允许该请求。
```

若已经出现过 `WinError 10013`，可发送：

```text
请重新执行刚才的 Lumenverba 生图请求，并在执行前申请联网权限。
```

出现联网授权提示后选择允许，随后 Codex 会继续执行生图；不要在对话中提供 API 密钥。

## 首次配置密钥

本技能调用的生图模型由 [Lumenverba](https://lumenverba.cc/home) 中转站提供。请先在该站点创建 API 密钥，再完成下方配置。

不要在聊天中发送 API 密钥。在 PowerShell 中粘贴并运行以下代码，输入时内容不会显示：

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$secureKey = Read-Host "请输入 Lumenverba API 密钥" -AsSecureString
$plainKey = [System.Net.NetworkCredential]::new("", $secureKey).Password
[Environment]::SetEnvironmentVariable("LUMENVERBA_API_KEY", $plainKey, "User")
Remove-Variable plainKey
Write-Host "配置完成。请完全退出并重新打开 Codex，然后重新发送生图请求。"
```

技能固定使用 `https://api.lumenverba.cc/v1`，无需配置 API 地址。

## 干净卸载

仅删除技能目录不会清除首次配置时写入的用户环境变量。若不再使用本技能，可在 Codex 对话中发送：

```text
请卸载 lumenverba-image（Lumenverba 绘图）技能，并删除用户环境变量 LUMENVERBA_API_KEY。不要显示密钥，也不要删除生成的图片或修改其他环境变量。完成后只报告技能目录和密钥是否仍存在，并提醒我完全退出并重新打开 Codex。
```

也可以在 PowerShell 中手动清理密钥：

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Environment]::SetEnvironmentVariable("LUMENVERBA_API_KEY", $null, "User")
Remove-Item Env:LUMENVERBA_API_KEY -ErrorAction SilentlyContinue
$keyStillExists = -not [string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable("LUMENVERBA_API_KEY", "User"))
Write-Host "用户环境变量仍存在: $keyStillExists"
Remove-Variable keyStillExists
```

命令应显示 `用户环境变量仍存在: False`。已经运行的 Codex 进程仍可能保留启动时继承的旧值，因此清理后必须完全退出 Codex、结束后台进程并重新打开。干净卸载不会删除此前生成的图片，也不会修改其他环境变量。

## 快速使用

完成安装、配置密钥并重新打开 Codex 后，直接用自然语言提出绘图请求即可。用户明确给出的 `model`、`size`、`quality` 会优先使用；未给出时使用默认值 `gpt-image-2`、`1536x1024`、`standard`。

文生图：

```text
使用 Lumenverba 绘图生成一幅雨夜广州街头的赛博朋克电影海报，16:9，高质量。
```

参考图生图：将参考图附到 Codex 对话中，再说明需要保留或改变的内容。

```text
参考这张图片中的角色，生成一幅末世上海街头的废土朋克海报，Q 版角色，size 为 1024x1536，quality 为 high。
```

指定文字生图：将需要准确显示的文字用引号标出，并说明画面和文字位置。

```text
生成一张柠檬汽水促销海报，中央必须清晰、完整、逐字显示“夏日特惠”，使用中文粗体字，quality 为 high。
```

## 功能

- 文生图：根据提示词创建图片。
- 参考图生图：使用一张或多张本地参考图片生成新图。
- 文字生图：要求图中完整呈现指定、清晰可读的文字。

默认使用模型 `gpt-image-2`、尺寸 `1536x1024` 和质量 `standard`。可用模型为 `gpt-image-1`、`gpt-image-1.5`、`gpt-image-2`；可用尺寸为 `1024x1024`、`1536x1024`、`1024x1536`；可用质量为 `low`、`standard`、`high`。用户显式指定的参数始终优先。
