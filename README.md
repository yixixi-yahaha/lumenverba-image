# Lumenverba 绘图

可安装的 Codex 技能，使用 Lumenverba 图像 API 生成图片。技能包内置仅依赖 Python 标准库的客户端，不依赖 MCP 常驻服务、本机固定路径或额外 Python 包。

## 安装

需要 Codex 和 Python 3.11 或更高版本：

```powershell
npx.cmd skills add yixixi-yahaha/lumenverba-image@lumenverba-image -g -y
```

安装完成后，重新打开 Codex。技能会在文生图、参考图生图、海报、角色图、插画或包含指定清晰文字的图片请求中自动启用。

## 首次配置密钥

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

## 功能

- 文生图：根据提示词创建图片。
- 参考图生图：使用一张或多张本地参考图片生成新图。
- 文字生图：要求图中完整呈现指定、清晰可读的文字。

默认使用模型 `gpt-image-2`、尺寸 `1536x1024` 和质量 `standard`。可用模型为 `gpt-image-1`、`gpt-image-1.5`、`gpt-image-2`；可用尺寸为 `1024x1024`、`1536x1024`、`1024x1536`；可用质量为 `low`、`standard`、`high`。用户显式指定的参数始终优先。
