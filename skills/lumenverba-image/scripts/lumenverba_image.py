"""Portable command-line client for the Lumenverba image API."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_BASE_URL = "https://api.lumenverba.cc/v1"
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_SIZE = "1536x1024"
DEFAULT_QUALITY = "standard"
ALLOWED_MODELS = {"gpt-image-1", "gpt-image-1.5", "gpt-image-2"}
ALLOWED_SIZES = {"1024x1024", "1536x1024", "1024x1536"}
ALLOWED_QUALITIES = {"low", "standard", "high"}
MAX_REFERENCE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024
TIMEOUT_SECONDS = 600


class Settings:
    def __init__(self, api_key: str):
        self.base_url = DEFAULT_BASE_URL
        self.api_key = api_key

    @classmethod
    def from_environment(cls) -> "Settings":
        api_key = os.environ.get("LUMENVERBA_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("未设置 LUMENVERBA_API_KEY 环境变量。")
        return cls(api_key)


def _select(value: str | None, allowed: set[str], default: str, label: str) -> str:
    selected = value or default
    if selected not in allowed:
        raise ValueError(f"不支持的{label}: {selected}")
    return selected


def build_generation_request(
    prompt: str,
    model: str | None = None,
    size: str | None = None,
    quality: str | None = None,
) -> dict[str, object]:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("提示词不能为空。")
    return {
        "model": _select(model, ALLOWED_MODELS, DEFAULT_MODEL, "模型"),
        "prompt": prompt.strip(),
        "size": _select(size, ALLOWED_SIZES, DEFAULT_SIZE, "尺寸"),
        "quality": _select(quality, ALLOWED_QUALITIES, DEFAULT_QUALITY, "质量"),
        "stream": True,
        "partial_images": 1,
    }


def build_text_prompt(
    text: str,
    description: str,
    language: str | None = None,
    position: str | None = None,
    style: str | None = None,
) -> str:
    if not text or not text.strip() or not description or not description.strip():
        raise ValueError("指定文字和画面描述不能为空。")
    return (
        f"{description.strip()}\n\n"
        f'图片中必须完整呈现以下文字："{text.strip()}"。文字必须逐字准确、清晰可读、完整显示，'
        "不得添加未要求的文字。\n"
        f"文字语言：{language or '自动识别'}。\n"
        f"文字位置：{position or '由构图决定'}。\n"
        f"文字样式：{style or '与视觉主题协调'}。"
    )


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.api_key}",
        "User-Agent": "LumenverbaCodexSkill/1.0",
    }


def _send(method: str, url: str, headers: dict[str, str], body: bytes = b"") -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url=url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, dict(response.headers.items()), response.read(MAX_IMAGE_BYTES + 1)
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()), error.read(MAX_IMAGE_BYTES + 1)
    except urllib.error.URLError as error:
        raise RuntimeError(f"调用图像服务失败: {error.reason}") from error


def _extract_image(payload: object) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("b64_json"), str) or isinstance(payload.get("url"), str):
        return payload
    data = payload.get("data")
    if isinstance(data, list):
        for item in data:
            image = _extract_image(item)
            if image:
                return image
    for key in ("image", "result", "output"):
        image = _extract_image(payload.get(key))
        if image:
            return image
    return None


def _decode_sse(body: bytes) -> dict[str, object]:
    for event in body.decode("utf-8").replace("\r\n", "\n").split("\n\n"):
        data = "\n".join(line[5:].lstrip() for line in event.splitlines() if line.startswith("data:"))
        if not data or data == "[DONE]":
            continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        event_type = str(payload.get("type", "")).lower() if isinstance(payload, dict) else ""
        image = _extract_image(payload)
        if image and "partial" not in event_type:
            return image
    raise RuntimeError("图像服务的流式响应中没有最终图像。")


def _decode_image(body: bytes, content_type: str) -> dict[str, object]:
    if content_type.lower().startswith("text/event-stream"):
        return _decode_sse(body)
    try:
        image = _extract_image(json.loads(body.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("图像服务响应无法解析。") from error
    if not image:
        raise RuntimeError("图像服务响应中没有可保存的图像。")
    return image


def _save_png(image_bytes: bytes, output_dir: Path) -> Path:
    if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("图像服务返回的内容不是 PNG 图像。")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise RuntimeError("生成图像文件过大。")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"lumenverba-{secrets.token_hex(12)}.png"
    path.write_bytes(image_bytes)
    return path.resolve()


def save_response_image(body: bytes, content_type: str, output_dir: Path, settings: Settings | None = None) -> Path:
    image = _decode_image(body, content_type)
    encoded = image.get("b64_json")
    if isinstance(encoded, str):
        try:
            return _save_png(base64.b64decode(encoded, validate=True), output_dir)
        except (ValueError, TypeError) as error:
            raise RuntimeError("图像服务返回的 base64 数据无效。") from error
    url = image.get("url")
    if not isinstance(url, str) or settings is None:
        raise RuntimeError("图像服务响应中没有可保存的图像。")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise RuntimeError("生成图像 URL 必须使用 HTTPS。")
    status, headers, image_bytes = _send("GET", url, {})
    if not 200 <= status < 300 or not headers.get("Content-Type", "").lower().startswith("image/png"):
        raise RuntimeError("下载生成图像失败。")
    return _save_png(image_bytes, output_dir)


def _is_supported_image(path: Path) -> bool:
    signature = path.read_bytes()[:12]
    return signature.startswith(b"\x89PNG\r\n\x1a\n") or signature.startswith(b"\xff\xd8\xff") or signature.startswith((b"GIF87a", b"GIF89a")) or (signature.startswith(b"RIFF") and signature[8:12] == b"WEBP")


def build_edit_request(prompt: str, references: list[Path], model: str | None, size: str | None, quality: str | None) -> tuple[bytes, str]:
    payload = build_generation_request(prompt, model, size, quality)
    payload.pop("stream")
    payload.pop("partial_images")
    if not references:
        raise ValueError("至少需要提供一张参考图。")
    boundary = f"----Lumenverba{secrets.token_hex(16)}"
    chunks: list[bytes] = []
    for name, value in payload.items():
        chunks.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), str(value).encode("utf-8"), b"\r\n"])
    for path in references:
        if not path.is_absolute() or not path.is_file():
            raise ValueError(f"参考图必须是存在的绝对路径: {path}")
        if path.stat().st_size > MAX_REFERENCE_BYTES or not _is_supported_image(path):
            raise ValueError(f"参考图格式不支持或文件过大: {path}")
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="image[]"; filename="{path.name}"\r\n'.encode(), f"Content-Type: {mime}\r\n\r\n".encode(), path.read_bytes(), b"\r\n"])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _request_image(endpoint: str, body: bytes, content_type: str, settings: Settings, output_dir: Path) -> Path:
    status, headers, response = _send("POST", f"{settings.base_url}{endpoint}", {**_headers(settings), "Content-Type": content_type}, body)
    if not 200 <= status < 300:
        raise RuntimeError(f"图像服务返回 HTTP {status}。")
    return save_response_image(response, headers.get("Content-Type", ""), output_dir, settings)


def generate(prompt: str, model: str | None, size: str | None, quality: str | None, output_dir: Path) -> Path:
    settings = Settings.from_environment()
    payload = build_generation_request(prompt, model, size, quality)
    return _request_image("/images/generations", json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json", settings, output_dir)


def edit(prompt: str, references: list[Path], model: str | None, size: str | None, quality: str | None, output_dir: Path) -> Path:
    settings = Settings.from_environment()
    body, content_type = build_edit_request(prompt, references, model, size, quality)
    return _request_image("/images/edits", body, content_type, settings, output_dir)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lumenverba 绘图客户端")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in ("generate", "edit", "text"):
        current = subcommands.add_parser(command)
        current.add_argument("--model", choices=sorted(ALLOWED_MODELS))
        current.add_argument("--size", choices=sorted(ALLOWED_SIZES))
        current.add_argument("--quality", choices=sorted(ALLOWED_QUALITIES))
        current.add_argument("--output-dir", type=Path, default=Path.cwd() / "output")
    subcommands.choices["generate"].add_argument("--prompt", required=True)
    subcommands.choices["edit"].add_argument("--prompt", required=True)
    subcommands.choices["edit"].add_argument("--reference", type=Path, action="append", required=True)
    subcommands.choices["text"].add_argument("--text", required=True)
    subcommands.choices["text"].add_argument("--description", required=True)
    subcommands.choices["text"].add_argument("--language")
    subcommands.choices["text"].add_argument("--position")
    subcommands.choices["text"].add_argument("--style")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "generate":
            path = generate(arguments.prompt, arguments.model, arguments.size, arguments.quality, arguments.output_dir)
        elif arguments.command == "edit":
            path = edit(arguments.prompt, arguments.reference, arguments.model, arguments.size, arguments.quality, arguments.output_dir)
        else:
            prompt = build_text_prompt(arguments.text, arguments.description, arguments.language, arguments.position, arguments.style)
            path = generate(prompt, arguments.model, arguments.size, arguments.quality, arguments.output_dir)
    except (OSError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
