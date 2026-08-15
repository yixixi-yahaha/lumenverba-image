import base64
import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch


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
    sys.modules[spec.name] = module
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

    def test_retryable_network_error_is_retried_once_and_reports_a_safe_notice(self):
        client = load_public_client()
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.headers = {}
        response.read.return_value = b"{}"
        stderr = StringIO()

        failures = [
            client.urllib.error.URLError(client.ssl.SSLError("private TLS detail")),
            response,
        ]
        with patch.object(client.urllib.request, "urlopen", side_effect=failures) as urlopen:
            with redirect_stderr(stderr):
                status, headers, body = client._send(
                    "POST",
                    "https://api.lumenverba.cc/v1/images/generations",
                    {},
                    b"payload",
                )

        self.assertEqual((status, headers, body), (200, {}, b"{}"))
        self.assertEqual(urlopen.call_count, 2)
        self.assertIn("RETRY_NOTICE: 首次调用失败：TLS 连接失败；已自动重试 1 次。", stderr.getvalue())
        self.assertNotIn("private TLS detail", stderr.getvalue())

    def test_timeout_is_not_retried(self):
        client = load_public_client()

        error = client.urllib.error.URLError(TimeoutError("private timeout"))
        with patch.object(client.urllib.request, "urlopen", side_effect=error) as urlopen:
            with self.assertRaisesRegex(RuntimeError, "网络连接超时.*生成状态未知.*未自动重试"):
                client._send("POST", "https://api.lumenverba.cc/v1/images/generations", {})

        self.assertEqual(urlopen.call_count, 1)

    def test_second_network_failure_is_reported_without_a_third_attempt(self):
        client = load_public_client()

        failures = [
            client.urllib.error.URLError(client.socket.gaierror(-2, "private host")),
            client.urllib.error.URLError("proxy credentials unavailable"),
        ]
        with patch.object(client.urllib.request, "urlopen", side_effect=failures) as urlopen:
            with self.assertRaisesRegex(RuntimeError, "首次发生DNS 解析失败.*自动重试后发生代理连接失败.*生成状态未知") as raised:
                client._send("POST", "https://api.lumenverba.cc/v1/images/generations", {})

        self.assertEqual(urlopen.call_count, 2)
        self.assertNotIn("private host", str(raised.exception))
        self.assertNotIn("proxy credentials", str(raised.exception))

    def test_network_error_categories_do_not_expose_raw_error_text(self):
        client = load_public_client()

        self.assertEqual(client._network_error_category(client.socket.gaierror(-2, "secret-dns-host")), "DNS 解析失败")
        self.assertEqual(client._network_error_category(client.ssl.SSLError("private TLS detail")), "TLS 连接失败")
        self.assertEqual(client._network_error_category(ConnectionRefusedError("private endpoint")), "连接被拒绝")
        self.assertEqual(client._network_error_category(TimeoutError("private timeout")), "网络连接超时")
        self.assertEqual(client._network_error_category("proxy credentials unavailable"), "代理连接失败")
        self.assertEqual(client._network_error_category("internal host message"), "网络连接失败")

    def test_defaults_are_used_for_a_generation_payload(self):
        client = load_public_client()

        payload = client.build_generation_request("海鸥在码头吃薯条")

        self.assertEqual(payload["model"], "gpt-image-2")
        self.assertEqual(payload["size"], "1536x1024")
        self.assertEqual(payload["quality"], "standard")
        self.assertEqual(payload["n"], 1)
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["partial_images"], 1)

    def test_generation_count_is_limited_to_ten(self):
        client = load_public_client()

        arguments = client._parser().parse_args(["generate", "--prompt", "同一提示词"])
        self.assertEqual(arguments.count, 1)
        self.assertEqual(client.build_generation_request("同一提示词", count=10)["n"], 10)
        for invalid in (0, 11):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "生成数量必须在 1 到 10 之间"):
                    client.build_generation_request("同一提示词", count=invalid)

    def test_result_receipt_option_is_available_in_every_command_mode(self):
        client = load_public_client()
        result_file = Path("C:/results/current.json")
        commands = (
            ["generate", "--prompt", "测试", "--result-file", str(result_file)],
            ["edit", "--prompt", "测试", "--reference", "C:/reference.png", "--result-file", str(result_file)],
            ["text", "--text", "测试", "--description", "测试", "--result-file", str(result_file)],
            ["batch", "--prompt", "first", "--prompt", "second", "--result-file", str(result_file)],
        )

        for command in commands:
            with self.subTest(command=command[0]):
                arguments = client._parser().parse_args(command)
                self.assertEqual(arguments.result_file, result_file)

    def test_successful_command_writes_a_result_receipt_without_changing_stdout(self):
        client = load_public_client()
        stdout = StringIO()
        stderr = StringIO()

        with tempfile.TemporaryDirectory() as directory:
            returned = [(Path(directory) / "generated.png").resolve()]
            result_file = (Path(directory) / "result.json").resolve()
            with patch.object(client, "generate", return_value=returned):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = client.main([
                        "generate",
                        "--prompt",
                        "测试",
                        "--result-file",
                        str(result_file),
                    ])
            receipt = json.loads(result_file.read_text(encoding="utf-8"))
            temporary_files = list(result_file.parent.glob(f".{result_file.name}.*.tmp"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().splitlines(), [str(returned[0])])
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(receipt, {
            "version": 1,
            "status": "success",
            "exit_code": 0,
            "paths": [str(returned[0])],
            "errors": [],
        })
        self.assertEqual(temporary_files, [])

    def test_successful_retry_notice_is_preserved_in_result_receipt(self):
        client = load_public_client()
        stdout = StringIO()
        stderr = StringIO()

        with tempfile.TemporaryDirectory() as directory:
            returned = [(Path(directory) / "generated.png").resolve()]
            result_file = (Path(directory) / "result.json").resolve()

            def generate_after_retry(*_args):
                client._record_retry_notice("TLS 连接失败")
                return returned

            with patch.object(client, "generate", side_effect=generate_after_retry):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = client.main([
                        "generate",
                        "--prompt",
                        "测试",
                        "--result-file",
                        str(result_file),
                    ])
            receipt = json.loads(result_file.read_text(encoding="utf-8"))

        notice = "RETRY_NOTICE: 首次调用失败：TLS 连接失败；已自动重试 1 次。"
        self.assertEqual(exit_code, 0)
        self.assertIn(notice, stderr.getvalue())
        self.assertEqual(receipt["status"], "success")
        self.assertEqual(receipt["errors"], [notice])

    def test_failed_command_writes_an_error_result_receipt(self):
        client = load_public_client()
        stderr = StringIO()

        with tempfile.TemporaryDirectory() as directory:
            result_file = (Path(directory) / "result.json").resolve()
            with patch.object(client, "generate", side_effect=RuntimeError("模拟失败")):
                with redirect_stderr(stderr):
                    exit_code = client.main([
                        "generate",
                        "--prompt",
                        "测试",
                        "--result-file",
                        str(result_file),
                    ])
            receipt = json.loads(result_file.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertIn("模拟失败", stderr.getvalue())
        self.assertEqual(receipt, {
            "version": 1,
            "status": "error",
            "exit_code": 1,
            "paths": [],
            "errors": ["模拟失败"],
        })

    def test_partial_command_writes_success_paths_and_numbered_errors_to_result_receipt(self):
        client = load_public_client()
        stdout = StringIO()
        stderr = StringIO()

        with tempfile.TemporaryDirectory() as directory:
            returned = [(Path(directory) / "first.png").resolve()]
            result_file = (Path(directory) / "result.json").resolve()
            with patch.object(client, "generate", return_value=returned):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = client.main([
                        "generate",
                        "--prompt",
                        "测试",
                        "--count",
                        "2",
                        "--result-file",
                        str(result_file),
                    ])
            receipt = json.loads(result_file.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertEqual(receipt["status"], "partial")
        self.assertEqual(receipt["paths"], [str(returned[0])])
        self.assertEqual(receipt["errors"], ["批次项 2 失败: 图像服务未返回该图片。"])

    def test_command_rejects_more_images_than_requested_in_result_receipt(self):
        client = load_public_client()

        with tempfile.TemporaryDirectory() as directory:
            returned = [
                (Path(directory) / "first.png").resolve(),
                (Path(directory) / "unexpected.png").resolve(),
            ]
            result_file = (Path(directory) / "result.json").resolve()
            with patch.object(client, "generate", return_value=returned):
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    exit_code = client.main([
                        "generate",
                        "--prompt",
                        "测试",
                        "--count",
                        "1",
                        "--result-file",
                        str(result_file),
                    ])
            receipt = json.loads(result_file.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertEqual(receipt["status"], "partial")
        self.assertEqual(receipt["paths"], [str(path) for path in returned])

    def test_receipt_write_failure_keeps_generated_paths_and_returns_nonzero(self):
        client = load_public_client()
        stdout = StringIO()
        stderr = StringIO()

        with tempfile.TemporaryDirectory() as directory:
            returned = [(Path(directory) / "generated.png").resolve()]
            result_file = (Path(directory) / "result.json").resolve()
            with patch.object(client, "generate", return_value=returned):
                with patch.object(client.Path, "replace", side_effect=OSError("模拟写入失败")):
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        exit_code = client.main([
                            "generate",
                            "--prompt",
                            "测试",
                            "--result-file",
                            str(result_file),
                        ])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue().splitlines(), [str(returned[0])])
        self.assertIn("写入结果回执失败: 模拟写入失败", stderr.getvalue())

    def test_relative_result_receipt_is_rejected_before_generation(self):
        client = load_public_client()
        stderr = StringIO()

        with patch.object(client, "generate") as generate:
            with redirect_stderr(stderr):
                exit_code = client.main([
                    "generate",
                    "--prompt",
                    "测试",
                    "--result-file",
                    "relative-result.json",
                ])

        self.assertEqual(exit_code, 1)
        self.assertIn("结果回执文件必须使用绝对路径", stderr.getvalue())
        generate.assert_not_called()

    def test_generation_prompt_is_passed_through_verbatim(self):
        client = load_public_client()
        prompt = "  保留 $price 与 `code`，不要改写。\n"

        self.assertEqual(client.build_generation_request(prompt)["prompt"], prompt)

    def test_missing_key_is_rejected(self):
        client = load_public_client()

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "未设置 LUMENVERBA_API_KEY"):
                client.Settings.from_environment()

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

    def test_json_response_saves_every_returned_image(self):
        client = load_public_client()
        encoded = base64.b64encode(PNG_BYTES).decode("ascii")
        response = json.dumps({"data": [{"b64_json": encoded}, {"b64_json": encoded}]}).encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            results = client.save_response_images(response, "application/json", Path(directory))

        self.assertEqual(len(results), 2)
        self.assertNotEqual(results[0], results[1])

    def test_sse_response_ignores_partials_and_saves_all_completed_images(self):
        client = load_public_client()
        encoded = base64.b64encode(PNG_BYTES).decode("ascii")
        response = (
            'data: {"type":"image_generation.partial_image","b64_json":"partial"}\n\n'
            f'data: {{"type":"image_generation.completed","b64_json":"{encoded}"}}\n\n'
            f'data: {{"type":"image_generation.completed","b64_json":"{encoded}"}}\n\n'
        ).encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            results = client.save_response_images(response, "text/event-stream", Path(directory))

        self.assertEqual(len(results), 2)

    def test_count_command_outputs_successes_and_reports_missing_images(self):
        client = load_public_client()
        returned = [Path("C:/generated/first.png")]
        stdout = StringIO()
        stderr = StringIO()

        with patch.object(client, "generate", return_value=returned):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = client.main(["generate", "--prompt", "同一提示词", "--count", "2"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue().splitlines(), [str(returned[0])])
        self.assertIn("批次项 2 失败", stderr.getvalue())

    def test_batch_starts_every_prompt_before_any_item_finishes(self):
        client = load_public_client()
        started = threading.Barrier(3)
        release = threading.Event()

        def fake_generate(prompt, model, size, quality, count, output_dir):
            started.wait(timeout=2)
            release.wait(timeout=2)
            return [Path(f"C:/generated/{prompt}.png")]

        with patch.object(client, "generate", side_effect=fake_generate):
            with ThreadPoolExecutor(max_workers=1) as harness:
                future = harness.submit(client.generate_batch, ["first", "second"], None, None, None, Path("output"))
                started.wait(timeout=2)
                release.set()
                results = future.result(timeout=2)

        self.assertEqual([item.path.name for item in results], ["first.png", "second.png"])
        self.assertTrue(all(item.error is None for item in results))

    def test_batch_preserves_successes_when_one_prompt_fails(self):
        client = load_public_client()

        def fake_generate(prompt, model, size, quality, count, output_dir):
            if prompt == "first":
                raise RuntimeError("模拟失败")
            return [Path("C:/generated/second.png")]

        with patch.object(client, "generate", side_effect=fake_generate):
            results = client.generate_batch(["first", "second"], None, None, None, Path("output"))

        self.assertEqual(results[0].error, "模拟失败")
        self.assertEqual(results[1].path, Path("C:/generated/second.png"))

    def test_batch_requires_two_to_four_prompts(self):
        client = load_public_client()
        for prompts in (["only"], ["1", "2", "3", "4", "5"]):
            with self.subTest(prompts=prompts):
                with self.assertRaisesRegex(ValueError, "批量提示词数量必须在 2 到 4 之间"):
                    client.generate_batch(prompts, None, None, None, Path("output"))

    def test_batch_cli_outputs_success_paths_and_numbered_errors(self):
        client = load_public_client()
        results = [
            client.BatchItemResult(error="模拟失败"),
            client.BatchItemResult(path=Path("C:/generated/second.png")),
        ]
        stdout = StringIO()
        stderr = StringIO()

        with patch.object(client, "generate_batch", return_value=results):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = client.main(["batch", "--prompt", "first", "--prompt", "second"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue().splitlines(), [str(Path("C:/generated/second.png"))])
        self.assertIn("批次项 1 失败: 模拟失败", stderr.getvalue())

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

    def test_edit_request_contains_the_requested_count(self):
        client = load_public_client()
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "reference.png"
            reference.write_bytes(PNG_BYTES)
            body, _ = client.build_edit_request("保持主体", [reference], None, None, None, count=4)

        self.assertIn(b'name="n"\r\n\r\n4\r\n', body)

    def test_response_url_is_downloaded_as_png(self):
        client = load_public_client()
        response = json.dumps({"data": [{"url": "https://example.test/image.png"}]}).encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(client, "_send", return_value=(200, {"Content-Type": "image/png"}, PNG_BYTES)) as send:
                result = client.save_response_image(response, "application/json", Path(directory), client.Settings("test-key"))

            self.assertEqual(result.read_bytes(), PNG_BYTES)
            self.assertEqual(send.call_args.args[:2], ("GET", "https://example.test/image.png"))

    def test_accepted_task_is_polled_until_png_is_ready(self):
        client = load_public_client()
        encoded = base64.b64encode(PNG_BYTES).decode("ascii")
        pending = json.dumps({"status": "processing"}).encode("utf-8")
        completed = json.dumps({"status": "completed", "data": [{"b64_json": encoded}]}).encode("utf-8")

        responses = [
            (202, {"Location": "/v1/tasks/task-1"}, b""),
            (200, {"Content-Type": "application/json"}, pending),
            (200, {"Content-Type": "application/json"}, completed),
        ]
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(client, "_send", side_effect=responses) as send:
                with patch.object(client.time, "sleep") as sleep:
                    result = client._request_image(
                        "/images/generations",
                        b"{}",
                        "application/json",
                        client.Settings("test-key"),
                        Path(directory),
                    )

            self.assertEqual(result.read_bytes(), PNG_BYTES)

        self.assertEqual(send.call_args_list[1].args[:2], ("GET", "https://api.lumenverba.cc/v1/tasks/task-1"))
        self.assertEqual(send.call_count, 3)
        sleep.assert_called_once_with(1)

    def test_accepted_task_rejects_an_insecure_location(self):
        client = load_public_client()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(client, "_send", return_value=(202, {"Location": "http://private.test/task"}, b"")):
                with self.assertRaisesRegex(RuntimeError, "不安全的任务地址"):
                    client._request_image(
                        "/images/generations",
                        b"{}",
                        "application/json",
                        client.Settings("test-key"),
                        Path(directory),
                    )

    def test_rejects_non_https_generated_image_url(self):
        client = load_public_client()
        response = json.dumps({"data": [{"url": "file:///private.png"}]}).encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "必须使用 HTTPS"):
                client.save_response_image(response, "application/json", Path(directory), client.Settings("test-key"))

    def test_rejects_relative_and_oversized_reference_images(self):
        client = load_public_client()
        with tempfile.TemporaryDirectory() as directory:
            relative = Path("reference.png")
            with self.assertRaisesRegex(ValueError, "存在的绝对路径"):
                client.build_edit_request("测试", [relative], None, None, None)

            oversized = Path(directory) / "oversized.png"
            oversized.write_bytes(PNG_BYTES + b"x" * (10 * 1024 * 1024))
            with self.assertRaisesRegex(ValueError, "文件过大"):
                client.build_edit_request("测试", [oversized.resolve()], None, None, None)


class PackagedSkillTests(unittest.TestCase):
    def test_documentation_declares_the_runtime_and_versioned_install_contract(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        for content in (readme, skill):
            self.assertIn("https://api.lumenverba.cc/v1", content)

        for expected in (
            "--output-dir",
            "load_workspace_dependencies",
            "/tree/v1.2.1/skills/lumenverba-image",
            "当前最新稳定版 v1.2.1",
        ):
            self.assertIn(expected, readme + skill)

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

    def test_skill_documents_fast_batch_workflow(self):
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        for expected in (
            "`--count 1..10`",
            "每批最多 4 项",
            "`batch`",
            "整批生成授权",
            "原样传递",
            "不得进行视觉检查",
            "成功图片",
            "批次项",
            "自动重试 1 次",
            "RETRY_NOTICE:",
            "首次失败原因",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

        for forbidden in (
            "多个不同素材不批量提交",
            "主体、场景、风格、构图、光线、准确文字和限制补足提示词",
            "还应视觉检查结果",
            "逐项确认和生成",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, content)

    def test_skill_waits_for_completed_command_output_before_reporting_results(self):
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        for expected in (
            "命令仍在运行时继续等待",
            "已取得完整 stdout、stderr 和退出码",
            "执行状态未知",
            "不得扫描输出目录",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

    def test_skill_uses_result_receipt_when_command_output_is_lost(self):
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        for expected in (
            "`--result-file`",
            "唯一",
            "完整 stdout、stderr 和退出码",
            "读取该回执",
            "`exit_code`",
            "不得扫描输出目录",
            "不得重新执行生图命令",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

    def test_skill_waits_for_a_delayed_result_receipt_after_output_is_lost(self):
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        for expected in (
            "每秒",
            "最多等待 60 秒",
            "同一回执",
            "校验成功即停止等待",
            "不得重新执行生图命令",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

    def test_readme_documents_batch_commands_and_limit(self):
        content = (ROOT / "README.md").read_text(encoding="utf-8")
        for expected in (
            "--count",
            "batch --prompt",
            "最多 10 张",
            "2 至 4 个 `--prompt`",
            "并发生成上限为 4 张",
            "部分失败",
            "安全连接错误自动重试 1 次",
            "首次失败原因",
            "网络连接超时、连接中途关闭、生成状态未知和其他错误不自动重试",
        ):
            self.assertIn(expected, content)

    def test_skill_documents_safe_retry_boundary_and_delivery_notice(self):
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        for expected in (
            "DNS 解析失败",
            "TLS 连接失败",
            "连接被拒绝",
            "代理连接失败",
            "自动重试 1 次",
            "网络连接超时",
            "生成状态未知",
            "RETRY_NOTICE:",
            "首次失败原因",
            "脚本之外",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

        for forbidden in ("回复“允许联网”", "重新发送该请求"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, content)

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
        ):
            self.assertIn(expected, content)
