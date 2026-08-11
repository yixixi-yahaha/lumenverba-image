"""Portable command-line client for the Lumenverba image API."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import secrets
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
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
MAX_GENERATION_COUNT = 10
MAX_BATCH_PROMPT_COUNT = 4
MAX_RESPONSE_BYTES = MAX_IMAGE_BYTES * MAX_GENERATION_COUNT * 4 // 3 + 64 * 1024
TIMEOUT_SECONDS = 600
MAX_TASK_POLL_ATTEMPTS = 60
TASK_POLL_INTERVAL_SECONDS = 1


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


@dataclass(frozen=True)
class BatchItemResult:
    path: Path | None = None
    error: str | None = None


def _select(value: str | None, allowed: set[str], default: str, label: str) -> str:
    selected = value or default
    if selected not in allowed:
        raise ValueError(f"不支持的{label}: {selected}")
    return selected


def _select_count(count: int) -> int:
    if not 1 <= count <= MAX_GENERATION_COUNT:
        raise ValueError("生成数量必须在 1 到 10 之间。")
    return count


def build_generation_request(
    prompt: str,
    model: str | None = None,
    size: str | None = None,
    quality: str | None = None,
    count: int = 1,
) -> dict[str, object]:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("提示词不能为空。")
    return {
        "model": _select(model, ALLOWED_MODELS, DEFAULT_MODEL, "模型"),
        "prompt": prompt,
        "size": _select(size, ALLOWED_SIZES, DEFAULT_SIZE, "尺寸"),
        "quality": _select(quality, ALLOWED_QUALITIES, DEFAULT_QUALITY, "质量"),
        "n": _select_count(count),
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


def _network_error_category(reason: object) -> str:
    if isinstance(reason, socket.gaierror):
        return "DNS 解析失败"
    if isinstance(reason, ssl.SSLError):
        return "TLS 连接失败"
    if isinstance(reason, ConnectionRefusedError):
        return "连接被拒绝"
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "网络连接超时"

    text = str(reason).lower()
    if "proxy" in text:
        return "代理连接失败"
    if "tls" in text or "ssl" in text:
        return "TLS 连接失败"
    if "refused" in text:
        return "连接被拒绝"
    if "timeout" in text or "timed out" in text:
        return "网络连接超时"
    return "网络连接失败"


def _send(method: str, url: str, headers: dict[str, str], body: bytes = b"") -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url=url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, dict(response.headers.items()), response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()), error.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.URLError as error:
        category = _network_error_category(error.reason)
        raise RuntimeError(f"调用图像服务时发生{category}，生成状态未知，请勿自动重试。请回复“允许联网”，然后重新发送该请求。") from error


def _extract_images(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        images: list[dict[str, object]] = []
        for item in payload:
            images.extend(_extract_images(item))
        return images
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("b64_json"), str) or isinstance(payload.get("url"), str):
        return [payload]
    images = _extract_images(payload.get("data"))
    for key in ("image", "result", "output"):
        images.extend(_extract_images(payload.get(key)))
    return images


def _decode_sse(body: bytes) -> list[dict[str, object]]:
    images: list[dict[str, object]] = []
    for event in body.decode("utf-8").replace("\r\n", "\n").split("\n\n"):
        data = "\n".join(line[5:].lstrip() for line in event.splitlines() if line.startswith("data:"))
        if not data or data == "[DONE]":
            continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        event_type = str(payload.get("type", "")).lower() if isinstance(payload, dict) else ""
        if "partial" not in event_type:
            images.extend(_extract_images(payload))
    if not images:
        raise RuntimeError("图像服务的流式响应中没有最终图像。")
    return images


def _decode_images(body: bytes, content_type: str) -> list[dict[str, object]]:
    if content_type.lower().startswith("text/event-stream"):
        return _decode_sse(body)
    try:
        images = _extract_images(json.loads(body.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("图像服务响应无法解析。") from error
    if not images:
        raise RuntimeError("图像服务响应中没有可保存的图像。")
    return images


def _save_png(image_bytes: bytes, output_dir: Path) -> Path:
    if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("图像服务返回的内容不是 PNG 图像。")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise RuntimeError("生成图像文件过大。")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"lumenverba-{secrets.token_hex(12)}.png"
    path.write_bytes(image_bytes)
    return path.resolve()


def _save_response_item(image: dict[str, object], output_dir: Path, settings: Settings | None) -> Path:
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


def save_response_images(
    body: bytes,
    content_type: str,
    output_dir: Path,
    settings: Settings | None = None,
) -> list[Path]:
    return [_save_response_item(image, output_dir, settings) for image in _decode_images(body, content_type)]


def save_response_image(body: bytes, content_type: str, output_dir: Path, settings: Settings | None = None) -> Path:
    return save_response_images(body, content_type, output_dir, settings)[0]


def _task_location(headers: dict[str, str], settings: Settings) -> str:
    location = next((value for key, value in headers.items() if key.lower() == "location"), None)
    if not location:
        raise RuntimeError("图像服务返回了异步任务，但没有任务地址。")
    task_url = urllib.parse.urljoin(f"{settings.base_url}/", location)
    parsed = urllib.parse.urlsplit(task_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise RuntimeError("图像服务返回了不安全的任务地址。")
    return task_url


def _task_status(body: bytes) -> str:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    if isinstance(payload.get("status"), str):
        return payload["status"].lower()
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("status"), str):
        return data["status"].lower()
    return ""


def _wait_for_task(task_url: str, settings: Settings, output_dir: Path) -> list[Path]:
    pending_statuses = {"queued", "pending", "processing", "running", "in_progress"}
    failed_statuses = {"failure", "failed", "error", "cancelled"}
    for attempt in range(MAX_TASK_POLL_ATTEMPTS):
        status, headers, response = _send("GET", task_url, _headers(settings))
        if not 200 <= status < 300:
            raise RuntimeError(f"图像任务查询返回 HTTP {status}。")
        try:
            return save_response_images(response, headers.get("Content-Type", ""), output_dir, settings)
        except RuntimeError as error:
            task_status = _task_status(response)
            if task_status in failed_statuses:
                raise RuntimeError(f"图像任务失败: {task_status}。") from error
            if task_status not in pending_statuses:
                raise
        if attempt + 1 < MAX_TASK_POLL_ATTEMPTS:
            time.sleep(TASK_POLL_INTERVAL_SECONDS)
    raise RuntimeError("图像任务在等待期间未完成。")


def _is_supported_image(path: Path) -> bool:
    signature = path.read_bytes()[:12]
    return signature.startswith(b"\x89PNG\r\n\x1a\n") or signature.startswith(b"\xff\xd8\xff") or signature.startswith((b"GIF87a", b"GIF89a")) or (signature.startswith(b"RIFF") and signature[8:12] == b"WEBP")


def build_edit_request(
    prompt: str,
    references: list[Path],
    model: str | None,
    size: str | None,
    quality: str | None,
    count: int = 1,
) -> tuple[bytes, str]:
    payload = build_generation_request(prompt, model, size, quality, count)
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


def _request_images(endpoint: str, body: bytes, content_type: str, settings: Settings, output_dir: Path) -> list[Path]:
    status, headers, response = _send("POST", f"{settings.base_url}{endpoint}", {**_headers(settings), "Content-Type": content_type}, body)
    if not 200 <= status < 300:
        raise RuntimeError(f"图像服务返回 HTTP {status}。")
    if status == 202:
        return _wait_for_task(_task_location(headers, settings), settings, output_dir)
    return save_response_images(response, headers.get("Content-Type", ""), output_dir, settings)


def _request_image(endpoint: str, body: bytes, content_type: str, settings: Settings, output_dir: Path) -> Path:
    return _request_images(endpoint, body, content_type, settings, output_dir)[0]


def generate(prompt: str, model: str | None, size: str | None, quality: str | None, count: int, output_dir: Path) -> list[Path]:
    settings = Settings.from_environment()
    payload = build_generation_request(prompt, model, size, quality, count)
    return _request_images("/images/generations", json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json", settings, output_dir)


def edit(prompt: str, references: list[Path], model: str | None, size: str | None, quality: str | None, count: int, output_dir: Path) -> list[Path]:
    settings = Settings.from_environment()
    body, content_type = build_edit_request(prompt, references, model, size, quality, count)
    return _request_images("/images/edits", body, content_type, settings, output_dir)


def generate_batch(
    prompts: list[str],
    model: str | None,
    size: str | None,
    quality: str | None,
    output_dir: Path,
) -> list[BatchItemResult]:
    if not 2 <= len(prompts) <= MAX_BATCH_PROMPT_COUNT:
        raise ValueError("批量提示词数量必须在 2 到 4 之间。")
    if any(not isinstance(prompt, str) or not prompt.strip() for prompt in prompts):
        raise ValueError("批量提示词不能为空。")

    def run(prompt: str) -> BatchItemResult:
        try:
            paths = generate(prompt, model, size, quality, 1, output_dir)
            if not paths:
                return BatchItemResult(error="图像服务未返回图片。")
            return BatchItemResult(path=paths[0])
        except (OSError, RuntimeError, ValueError) as error:
            return BatchItemResult(error=str(error))

    with ThreadPoolExecutor(max_workers=len(prompts)) as executor:
        futures = [executor.submit(run, prompt) for prompt in prompts]
        return [future.result() for future in futures]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lumenverba 绘图客户端")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in ("generate", "edit", "text"):
        current = subcommands.add_parser(command)
        current.add_argument("--model", choices=sorted(ALLOWED_MODELS))
        current.add_argument("--size", choices=sorted(ALLOWED_SIZES))
        current.add_argument("--quality", choices=sorted(ALLOWED_QUALITIES))
        current.add_argument("--output-dir", type=Path, default=Path.cwd() / "output")
        current.add_argument("--count", type=int, choices=range(1, MAX_GENERATION_COUNT + 1), default=1)
    subcommands.choices["generate"].add_argument("--prompt", required=True)
    subcommands.choices["edit"].add_argument("--prompt", required=True)
    subcommands.choices["edit"].add_argument("--reference", type=Path, action="append", required=True)
    subcommands.choices["text"].add_argument("--text", required=True)
    subcommands.choices["text"].add_argument("--description", required=True)
    subcommands.choices["text"].add_argument("--language")
    subcommands.choices["text"].add_argument("--position")
    subcommands.choices["text"].add_argument("--style")
    batch_parser = subcommands.add_parser("batch")
    batch_parser.add_argument("--model", choices=sorted(ALLOWED_MODELS))
    batch_parser.add_argument("--size", choices=sorted(ALLOWED_SIZES))
    batch_parser.add_argument("--quality", choices=sorted(ALLOWED_QUALITIES))
    batch_parser.add_argument("--output-dir", type=Path, default=Path.cwd() / "output")
    batch_parser.add_argument("--prompt", action="append", required=True)
    return parser


def _print_results(paths: list[Path], expected_count: int) -> int:
    for path in paths:
        print(path)
    if len(paths) == expected_count:
        return 0
    for index in range(len(paths) + 1, expected_count + 1):
        print(f"批次项 {index} 失败: 图像服务未返回该图片。", file=sys.stderr)
    return 1


def _print_batch_results(results: list[BatchItemResult]) -> int:
    failed = False
    for index, result in enumerate(results, start=1):
        if result.path is not None:
            print(result.path)
        else:
            failed = True
            print(f"批次项 {index} 失败: {result.error or '未知错误'}", file=sys.stderr)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "batch":
            results = generate_batch(arguments.prompt, arguments.model, arguments.size, arguments.quality, arguments.output_dir)
            return _print_batch_results(results)
        if arguments.command == "generate":
            paths = generate(arguments.prompt, arguments.model, arguments.size, arguments.quality, arguments.count, arguments.output_dir)
        elif arguments.command == "edit":
            paths = edit(arguments.prompt, arguments.reference, arguments.model, arguments.size, arguments.quality, arguments.count, arguments.output_dir)
        else:
            prompt = build_text_prompt(arguments.text, arguments.description, arguments.language, arguments.position, arguments.style)
            paths = generate(prompt, arguments.model, arguments.size, arguments.quality, arguments.count, arguments.output_dir)
    except (OSError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return _print_results(paths, arguments.count)


if __name__ == "__main__":
    raise SystemExit(main())
