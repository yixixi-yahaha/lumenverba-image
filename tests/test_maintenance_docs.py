import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_utf8(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _is_known_safe_secret_fixture(path: str, line: str) -> bool:
    assignment_literal = "LUMENVERBA_" + "API_KEY="
    expected = (
        'self.assertNotIn("'
        + assignment_literal
        + '", content, f"公开文件包含密钥赋值: {path}")'
    )
    return path == "tests/test_public_skill.py" and line.strip() == expected


def suspected_secret_files(files: dict[str, str]) -> list[str]:
    patterns = (
        re.compile("sk-" + r"[A-Za-z0-9_-]{32,}"),
        re.compile("LUMENVERBA_" + r"API_KEY\s*="),
        re.compile("Authorization:" + r"\s*Bearer\s+[A-Za-z0-9._-]{12,}"),
    )
    offenders = set()
    for path, content in files.items():
        for line in content.splitlines():
            if _is_known_safe_secret_fixture(path, line):
                continue
            if any(pattern.search(line) for pattern in patterns):
                offenders.add(path)
                break
    return sorted(offenders)


class AgentsInstructionsTests(unittest.TestCase):
    def test_root_agents_file_defines_authority_and_security_boundaries(self):
        content = read_utf8("AGENTS.md")
        required = (
            "origin/main",
            "codex/",
            "LUMENVERBA_API_KEY",
            "真实 API",
            "push",
            "PR",
            "merge",
            "tag",
            "Release",
            "提交 SHA",
            "测试命令和结果",
            "未解决风险",
        )
        for expected in required:
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

        self.assertIn("只修改任务明确授权的代码、测试和文档", content)
        self.assertIn("不得读取、输出、复制、记录或提交", content)
        self.assertNotRegex(content, r"(?i)[a-z]:[\\/]+users[\\/]+")

    def test_existing_ignore_rules_cover_local_secrets_outputs_and_caches(self):
        content = read_utf8(".gitignore")
        for expected in (
            ".env",
            ".env.*",
            "*.key",
            "*.pem",
            "output/",
            "lumenverba-*.png",
            "__pycache__/",
            "*.py[cod]",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, content)
        self.assertNotIn("*.json", content)


class HandoffDocumentTests(unittest.TestCase):
    def test_handoff_distinguishes_stable_and_candidate_state(self):
        content = read_utf8("docs/maintenance/HANDOFF.md")
        required = (
            "## 稳定基线",
            "v1.2.5",
            "02b1731e5b5aa3e19e92a63b4a7d1e12d4f50703",
            "## 候选版本",
            "codex/gpt-image-2-flexible-sizes",
            "PR #4",
            "v1.2.6-rc.1",
            "d88ba22109b5fdaa5632154d3f2e15752985218a",
            "## 项目地图",
            "## 任务输入模板",
            "## 交付模板",
        )
        for expected in required:
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

        self.assertIn("开始任务时必须核对本地 refs", content)
        self.assertIn("不得把候选行为写成 main 已发布能力", content)
        self.assertNotRegex(content, r"(?i)[a-z]:[\\/]+users[\\/]+")


class SecretScanTests(unittest.TestCase):
    def test_scanner_reports_only_filenames_for_suspected_values(self):
        token = "sk-" + "x" * 40
        key_assignment = "LUMENVERBA_" + "API_KEY=example"
        bearer_value = "Authorization:" + " Bearer " + "a" * 20
        files = {
            "safe.txt": "ordinary documentation",
            "token.txt": token,
            "key.txt": key_assignment,
            "bearer.txt": bearer_value,
        }

        result = suspected_secret_files(files)

        self.assertEqual(["bearer.txt", "key.txt", "token.txt"], result)
        self.assertNotIn(token, repr(result))
        self.assertNotIn(key_assignment, repr(result))
        self.assertNotIn(bearer_value, repr(result))

    def test_scanner_allows_only_the_existing_privacy_assertion_fixture(self):
        assignment_literal = "LUMENVERBA_" + "API_KEY="
        fixture = (
            'self.assertNotIn("'
            + assignment_literal
            + '", content, f"公开文件包含密钥赋值: {path}")'
        )
        files = {
            "tests/test_public_skill.py": fixture,
            "another_test.py": fixture,
        }

        self.assertEqual(["another_test.py"], suspected_secret_files(files))

    def test_tracked_utf8_text_has_no_suspected_secret_values(self):
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        files = {}
        for raw_path in result.stdout.split(b"\0"):
            if not raw_path:
                continue
            relative = raw_path.decode("utf-8")
            try:
                files[relative] = read_utf8(relative)
            except UnicodeDecodeError:
                continue

        self.assertEqual([], suspected_secret_files(files))


class VerificationDocumentTests(unittest.TestCase):
    def test_verification_document_contains_offline_and_authorization_gates(self):
        content = read_utf8("docs/maintenance/VERIFICATION.md")
        commands = (
            "python -m unittest discover -s tests -v",
            "python -m unittest discover -v",
            "python -m compileall -q skills tests",
            "lumenverba_image.py --help",
            "lumenverba_image.py generate --help",
            "lumenverba_image.py edit --help",
            "lumenverba_image.py text --help",
            "lumenverba_image.py batch --help",
            "git diff --check",
            "git status --short --branch",
            "python -m unittest tests.test_maintenance_docs.SecretScanTests -v",
        )
        for expected in commands:
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

        for boundary in (
            "不读取环境变量值",
            "不调用真实 API",
            "不得自动重试创建请求",
            "单独明确授权",
            "不得 push、修改 PR、merge、创建或移动 tag、创建 Release",
        ):
            with self.subTest(boundary=boundary):
                self.assertIn(boundary, content)

        self.assertNotRegex(content, r"(?i)[a-z]:[\\/]+users[\\/]+")


if __name__ == "__main__":
    unittest.main()
