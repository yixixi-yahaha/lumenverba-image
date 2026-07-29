import base64
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "lumenverba-image"
SCRIPT_PATH = SKILL_ROOT / "scripts" / "lumenverba_image.py"
PUBLIC_FILES = (ROOT / "README.md", SKILL_ROOT / "SKILL.md", SCRIPT_PATH)
PNG_BYTES = b"\x89PNG\r\n\x1a\nexample"


def load_public_client():
    spec = importlib.util.spec_from_file_location("public_lumenverba_client", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载公开客户端脚本")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicSkillPrivacyTests(unittest.TestCase):
    def test_public_files_do_not_include_this_machine_path_or_key_assignment(self):
        forbidden_paths = {str(Path.home()), str(ROOT)}
        for path in PUBLIC_FILES:
            content = path.read_text(encoding="utf-8")
            for forbidden in forbidden_paths:
                self.assertNotIn(forbidden, content, f"公开文件泄露了本机路径: {path}")
            self.assertNotIn("LUMENVERBA_API_KEY=", content, f"公开文件包含密钥赋值: {path}")


class PortableClientTests(unittest.TestCase):
    def test_text_arguments_preserve_shell_sensitive_characters(self):
        client = load_public_client()

        arguments = client._parser().parse_args([
            "text",
            "--text",
            "“夏日$特惠” O'Reilly `test`",
            "--description",
            '海报包含 "ASCII quotes" 与 $price',
        ])

        self.assertEqual(arguments.text, "“夏日$特惠” O'Reilly `test`")
        self.assertEqual(arguments.description, '海报包含 "ASCII quotes" 与 $price')

    def test_settings_uses_the_api_subdomain_by_default(self):
        client = load_public_client()

        with patch.dict(os.environ, {"LUMENVERBA_API_KEY": "test-key"}, clear=True):
            self.assertEqual(client.Settings.from_environment().base_url, "https://api.lumenverba.cc/v1")

    def test_defaults_are_used_for_a_generation_payload(self):
        client = load_public_client()

        payload = client.build_generation_request("海鸥在码头吃薯条")

        self.assertEqual(payload["model"], "gpt-image-2")
        self.assertEqual(payload["size"], "1536x1024")
        self.assertEqual(payload["quality"], "standard")
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["partial_images"], 1)

    def test_missing_key_is_rejected(self):
        client = load_public_client()

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "未设置 LUMENVERBA_API_KEY"):
                client.Settings.from_environment()

    def test_network_error_reports_unknown_generation_state_without_retrying(self):
        client = load_public_client()

        with patch.object(client.urllib.request, "urlopen", side_effect=client.urllib.error.URLError("TLS EOF")) as urlopen:
            with self.assertRaisesRegex(RuntimeError, "生成状态未知"):
                client._send("POST", "https://api.lumenverba.cc/v1/images/generations", {})

        urlopen.assert_called_once()

    def test_text_prompt_requires_verbatim_readable_text(self):
        client = load_public_client()

        prompt = client.build_text_prompt("夏日特惠", "柠檬汽水海报", "zh-CN", "center", "粗体无衬线")

        self.assertIn('"夏日特惠"', prompt)
        self.assertIn("逐字准确", prompt)
        self.assertIn("清晰可读", prompt)

    def test_sse_final_image_is_saved_as_png(self):
        client = load_public_client()
        encoded = base64.b64encode(PNG_BYTES).decode("ascii")
        response = (
            'data: {"type":"image_generation.partial_image","b64_json":"partial"}\n\n'
            f'data: {{"type":"image_generation.completed","b64_json":"{encoded}"}}\n\n'
        ).encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            result = client.save_response_image(response, "text/event-stream", Path(directory))

            self.assertEqual(result.read_bytes(), PNG_BYTES)
            self.assertEqual(result.suffix, ".png")

    def test_https_image_url_is_downloaded_and_saved_as_png(self):
        client = load_public_client()
        response = json.dumps({"data": [{"url": "https://cdn.example.test/image.png"}]}).encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(client, "_send", return_value=(200, {"Content-Type": "image/png"}, PNG_BYTES)) as send:
                result = client.save_response_image(response, "application/json", Path(directory), client.Settings("test-key"))

            self.assertEqual(result.read_bytes(), PNG_BYTES)
            self.assertEqual(result.suffix, ".png")

        send.assert_called_once_with("GET", "https://cdn.example.test/image.png", {})

    def test_https_image_url_rejects_non_png_content_type(self):
        client = load_public_client()
        response = json.dumps({"data": [{"url": "https://cdn.example.test/image.png"}]}).encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(client, "_send", return_value=(200, {"Content-Type": "text/html"}, PNG_BYTES)) as send:
                with self.assertRaisesRegex(RuntimeError, "下载生成图像失败"):
                    client.save_response_image(response, "application/json", Path(directory), client.Settings("test-key"))

        send.assert_called_once_with("GET", "https://cdn.example.test/image.png", {})

    def test_non_png_image_response_is_rejected(self):
        client = load_public_client()
        encoded = base64.b64encode(b"not a png").decode("ascii")
        response = json.dumps({"data": [{"b64_json": encoded}]}).encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "不是 PNG"):
                client.save_response_image(response, "application/json", Path(directory))

    def test_accepted_generation_polls_its_task_until_a_png_is_available(self):
        client = load_public_client()
        encoded = base64.b64encode(PNG_BYTES).decode("ascii")
        responses = [
            (202, {"Location": "/v1/tasks/task-123"}, b'{"id":"task-123","status":"queued"}'),
            (200, {}, b'{"id":"task-123","status":"queued"}'),
            (200, {}, json.dumps({"data": [{"b64_json": encoded}]}).encode("utf-8")),
        ]

        with tempfile.TemporaryDirectory() as directory:
            settings = client.Settings("test-key")
            with patch.object(client, "_send", side_effect=responses) as send, patch.object(client.time, "sleep") as sleep:
                result = client._request_image("/images/generations", b"{}", "application/json", settings, Path(directory))
            self.assertEqual(result.read_bytes(), PNG_BYTES)

        self.assertEqual(send.call_args_list[0].args[0], "POST")
        self.assertEqual(send.call_args_list[1].args[0], "GET")
        self.assertEqual(send.call_args_list[1].args[1], "https://api.lumenverba.cc/v1/tasks/task-123")
        self.assertEqual(send.call_args_list[2].args[0], "GET")
        sleep.assert_called_once_with(1)

    def test_edit_request_contains_each_reference_image(self):
        client = load_public_client()
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.png"
            second = Path(directory) / "second.png"
            first.write_bytes(PNG_BYTES)
            second.write_bytes(PNG_BYTES)

            body, content_type = client.build_edit_request("保留人物姿势", [first, second], "gpt-image-2", "1024x1024", "standard")

        self.assertIn(b'name="image[]"; filename="first.png"', body)
        self.assertIn(b'name="image[]"; filename="second.png"', body)
        self.assertIn("multipart/form-data", content_type)

    def test_edit_request_rejects_relative_reference_path(self):
        client = load_public_client()

        with self.assertRaisesRegex(ValueError, "绝对路径"):
            client.build_edit_request("保留人物姿势", [Path("relative.png")], "gpt-image-2", "1024x1024", "standard")

    def test_edit_request_rejects_oversized_reference_image(self):
        client = load_public_client()
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "large.png"
            image.write_bytes(PNG_BYTES + b"x" * client.MAX_REFERENCE_BYTES)

            with self.assertRaisesRegex(ValueError, "文件过大"):
                client.build_edit_request("保留人物姿势", [image], "gpt-image-2", "1024x1024", "standard")


class PackagedSkillTests(unittest.TestCase):
    def test_readme_documents_installation_and_release_contracts(self):
        content = (ROOT / "README.md").read_text(encoding="utf-8")

        for expected in (
            "https://api.lumenverba.cc/v1",
            'npx.cmd skills add "https://github.com/yixixi-yahaha/lumenverba-image/tree/v1.0.0/skills/lumenverba-image" -g -y',
            "/tree/v1.0.0/skills/lumenverba-image",
            "发布门禁",
            "默认测试",
            "PR 不联网",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

    def test_skill_documents_runtime_and_network_failure_contracts(self):
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        for expected in (
            "https://api.lumenverba.cc/v1",
            "--output-dir",
            "load_workspace_dependencies",
            "生成状态未知",
            "不自动重试",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

    def test_readme_documents_clean_uninstall(self):
        content = (ROOT / "README.md").read_text(encoding="utf-8")

        for expected in (
            "## 干净卸载",
            "请卸载 lumenverba-image（Lumenverba 绘图）技能",
            '[Environment]::SetEnvironmentVariable("LUMENVERBA_API_KEY", $null, "User")',
            "Remove-Item Env:LUMENVERBA_API_KEY",
            "不要显示密钥",
            "不要删除生成的图片或修改其他环境变量",
            "完全退出并重新打开 Codex",
        ):
            self.assertIn(expected, content)

    def test_skill_forbids_inline_python_and_documents_safe_quoting(self):
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        for expected in (
            "不得使用 `python -c`",
            "`text --text --description`",
            "PowerShell",
            "单引号写成两个单引号",
        ):
            self.assertIn(expected, content)

    def test_skill_documents_secure_first_use_and_all_modes(self):
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for expected in (
            "generate",
            "edit",
            "text",
            "gpt-image-2",
            "1536x1024",
            "standard",
            "Read-Host",
            "AsSecureString",
            "SetEnvironmentVariable",
            "完全退出并重新打开 Codex",
            "require_escalated",
            "联网权限",
            "WinError 10013",
        ):
            self.assertIn(expected, content)
