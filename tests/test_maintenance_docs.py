import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_utf8(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


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


if __name__ == "__main__":
    unittest.main()
