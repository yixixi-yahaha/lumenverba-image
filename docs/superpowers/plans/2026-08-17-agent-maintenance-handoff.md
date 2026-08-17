# Lumenverba Temporary Agent Maintenance Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add repository-tracked instructions and verification gates that let a temporary Agent maintain explicitly authorized Lumenverba code in an isolated clone while the primary Agent retains integration and release authority.

**Architecture:** Keep the GitHub repository and `origin/main` as the only authority, and use a dedicated clone plus a `codex/` task branch as the temporary implementation layer. Add one root instruction file, two focused maintenance documents, and a small contract-test module; verify the workflow with an offline local-clone drill that never reads credentials or changes remote state.

**Tech Stack:** Markdown, Git, PowerShell, Python 3.11+ standard library, `unittest`.

## Global Constraints

- The GitHub repository `https://github.com/yixixi-yahaha/lumenverba-image` and verified `origin/main` are the only release authority.
- The recommended dedicated maintenance clone path is `C:\Projects\lumenverba-image-agent-maintenance`; the primary Agent may select another explicit path for a task.
- Temporary Agents work only in a dedicated clone or explicitly created short-term worktree and on a `codex/` task branch.
- Temporary Agents may read the repository, modify only authorized code/tests, run offline checks, and create local commits.
- Live API calls, push, PR changes, merge, tag, Release, and destructive cleanup each require separate explicit authorization.
- Never read, print, copy, log, or commit `LUMENVERBA_API_KEY`; never commit real receipts or generated images.
- Existing tags are immutable. A changed release candidate receives a new RC tag; `v1.2.6-rc.1` is never moved.
- PR #4 and `v1.2.6-rc.1` remain untouched by this implementation.
- Stable `main` is currently `v1.2.5`; the flexible-size candidate is `codex/gpt-image-2-flexible-sizes` at commit `d88ba22109b5fdaa5632154d3f2e15752985218a` and is not yet stable behavior.
- Production remains Python 3.11+ and standard-library-only. Normal verification is offline and must not access the Lumenverba API.
- Existing `.gitignore` rules for `.env`, `.env.*`, `*.key`, `*.pem`, `output/`, `lumenverba-*.png`, `__pycache__/`, and `*.py[cod]` are sufficient; do not add a broad `*.json` ignore that could hide tracked fixtures or documentation.
- Keep changes limited to `AGENTS.md`, `docs/maintenance/`, and `tests/test_maintenance_docs.py`; do not change runtime code, public skill behavior, stable version metadata, or the existing PR.

---

### Task 1: Add Repository-Level Temporary-Agent Instructions

**Files:**
- Create: `AGENTS.md`
- Create: `tests/test_maintenance_docs.py`
- Verify unchanged: `.gitignore`

**Interfaces:**
- Consumes: repository authority and permission boundaries from the approved design.
- Produces: root-scoped instructions for every Agent, plus `read_utf8(relative_path: str) -> str` for later documentation-contract tests.

- [ ] **Step 1: Write the failing root-instructions contract test**

Create `tests/test_maintenance_docs.py` with this complete initial content:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
python -m unittest tests.test_maintenance_docs.AgentsInstructionsTests -v
```

Expected: `test_root_agents_file_defines_authority_and_security_boundaries` errors with `FileNotFoundError` for `AGENTS.md`; the `.gitignore` test passes.

- [ ] **Step 3: Write the repository instructions**

Create `AGENTS.md` with this content:

```markdown
# Lumenverba Image 仓库维护规则

本文件适用于整个仓库。临时 Agent 只能承担明确授权的脚本维护或小型优化；主维护 Agent 保留集成、版本和发布决策权。

## 开始任务前

1. 阅读 `CONTEXT.md`、`docs/maintenance/HANDOFF.md`、`docs/maintenance/VERIFICATION.md`、任务指定的设计/计划和目标文件。
2. 确认自己位于专用 clone 或明确创建的短期 worktree，并位于 `codex/` 任务分支；不得直接在 `main` 上工作。
3. 记录任务指定的基线提交、允许修改的文件、验收标准和权限范围。
4. 先运行基线离线测试。若基线失败，停止修改并报告，不把既有失败混入新改动。

## 权威与范围

- GitHub 仓库和验证通过的 `origin/main` 是唯一发布源；普通文件夹副本不是维护源。
- 只修改任务明确授权的代码、测试和文档，保持现有风格，采用最小且可验证的改动。
- 临时 Agent 默认可以读取仓库、运行离线检查、编辑授权文件并创建本地提交。
- 未经单独明确授权，不得联网调用真实 API、push、创建或修改 PR、merge、创建或移动 tag、创建 Release、force-push 或执行破坏性清理。
- 已有标签不可移动；候选版本发生变化时创建新的 RC 标签。

## 凭据与计费操作

- 不得读取、输出、复制、记录或提交 `LUMENVERBA_API_KEY`，也不得要求用户在聊天中提供密钥。
- 不得提交真实 API 回执、生成图片、`.env`、密钥文件或包含令牌的日志。
- 真实 API 测试必须单独授权，并限制为约定模型、尺寸、质量、数量和唯一临时回执。
- 创建请求失败或状态未知时不得盲目重试；读取请求仅遵守当前客户端已有的安全重试契约。

## 工程门禁

- Python 最低版本为 3.11；运行时保持仅依赖标准库。
- 修改行为时先添加能证明问题的测试，再实施最小修复，并运行聚焦测试与完整离线门禁。
- 不把零测试的 `unittest discover` 当作成功；两种发现命令都必须实际执行测试。
- 提交前检查差异、格式、机器私有路径和疑似凭据；不得通过输出匹配行来暴露疑似密钥。

## 交付格式

临时 Agent 交付时必须报告：任务分支、提交 SHA、变更文件、测试命令和结果、未解决风险，以及未执行的联网或发布动作。主维护 Agent独立审查提交后，才决定是否 cherry-pick、push、更新 PR、merge、打标签或发布 Release。
```

- [ ] **Step 4: Run the focused and existing documentation tests**

Run:

```powershell
python -m unittest tests.test_maintenance_docs.AgentsInstructionsTests -v
python -m unittest discover -s tests -p "test_public_skill.py" -v
```

Expected: both commands pass; the second command executes the repository's existing public-contract suite rather than zero tests.

- [ ] **Step 5: Verify the exact Task 1 diff**

Run:

```powershell
git diff --check
git status --short
git diff -- AGENTS.md tests/test_maintenance_docs.py .gitignore
```

Expected: only `AGENTS.md` and `tests/test_maintenance_docs.py` are new; `.gitignore` has no diff.

- [ ] **Step 6: Commit the repository instructions**

```powershell
git add -- AGENTS.md tests/test_maintenance_docs.py
git commit -m "docs: define temporary agent maintenance rules"
```

### Task 2: Add the Version-Aware Maintenance Handoff

**Files:**
- Create: `docs/maintenance/HANDOFF.md`
- Modify: `tests/test_maintenance_docs.py`

**Interfaces:**
- Consumes: `read_utf8(relative_path: str) -> str` and the authority rules from Task 1.
- Produces: a project map, stable/candidate distinction, intake template, task lifecycle, and delivery template for temporary Agents.

- [ ] **Step 1: Add the failing handoff contract test**

Insert this class before the `if __name__ == "__main__":` block in `tests/test_maintenance_docs.py`:

```python
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
```

- [ ] **Step 2: Run the handoff test and verify RED**

Run:

```powershell
python -m unittest tests.test_maintenance_docs.HandoffDocumentTests -v
```

Expected: the test errors with `FileNotFoundError` for `docs/maintenance/HANDOFF.md`.

- [ ] **Step 3: Write the handoff document**

Create `docs/maintenance/HANDOFF.md` with this content:

```markdown
# Lumenverba Image 临时维护交接

本文件给只承担临时代码维护的 Agent 使用。GitHub 仓库、`origin/main` 和主维护 Agent 的审查结论始终优先于本文件中的状态快照。开始任务时必须核对本地 refs；若状态已变化，先报告并由主维护 Agent 决定是否更新本文件。

## 权威仓库

- 仓库：`https://github.com/yixixi-yahaha/lumenverba-image`
- 唯一发布源：验证通过的 `origin/main`
- 临时实现位置：主维护 Agent 指定的专用 clone；推荐目录为 `C:\Projects\lumenverba-image-agent-maintenance`
- 临时任务分支：`codex/<task-name>`

普通文件夹复制不是维护方式。短期 worktree 只用于本机隔离，不作为长期交接目录。

## 稳定基线

- 当前稳定版本：`v1.2.5`
- `origin/main` 稳定提交：`02b1731e5b5aa3e19e92a63b4a7d1e12d4f50703`
- 稳定版默认值：`model=gpt-image-2`、`size=1536x1024`、`quality=standard`
- 稳定版公开安装说明仍固定到 `v1.2.5`

## 候选版本

- 分支：`codex/gpt-image-2-flexible-sizes`
- PR：PR #4，`https://github.com/yixixi-yahaha/lumenverba-image/pull/4`
- RC 标签：`v1.2.6-rc.1`
- RC 目标提交：`d88ba22109b5fdaa5632154d3f2e15752985218a`
- 候选契约：只支持 `gpt-image-2`；默认 `size=auto`、`quality=medium`；接受官方质量值与受约束的灵活尺寸；实验分辨率警告但允许执行。

PR #4 尚未合并，`v1.2.6-rc.1` 不得移动。不得把候选行为写成 main 已发布能力；任务必须明确选择稳定基线或候选分支。

## 项目地图

- `CONTEXT.md`：领域术语和发布语言。
- `README.md`：安装、配置、公开能力和维护者发布门禁。
- `skills/lumenverba-image/SKILL.md`：Agent 调用契约与结果交付规则。
- `skills/lumenverba-image/scripts/lumenverba_image.py`：唯一生产客户端。
- `tests/test_public_skill.py`：公开契约、网络边界、CLI 和文档测试。
- `tests/test_regressions.py`：结果回执及历史回归测试。
- `.github/workflows/ci.yml`：Windows/Ubuntu、Python 3.11/3.14 离线门禁。
- `docs/adr/`：不可随意改变的架构决策。
- `docs/superpowers/specs/` 与 `docs/superpowers/plans/`：已确认设计和可执行计划。
- `docs/maintenance/VERIFICATION.md`：临时维护验证与交付门禁。

## 关键运行契约

- API 基址固定为 `https://api.lumenverba.cc/v1`；客户端保持 Python 标准库实现。
- 创建请求绝不自动重试；安全读取请求最多按现有契约重试一次。
- 异步任务地址必须通过可信源和版本命名空间校验后才能携带认证信息轮询。
- 每次调用使用预先确定的唯一结果回执；结果通道丢失时只轮询同一回执，不扫描输出目录，不重复创建请求。
- 所有返回图片路径都必须验证并交付；数量不一致报告 `partial`，不得截断路径。
- 不读取、不显示、不复制、不记录、不提交 `LUMENVERBA_API_KEY`。

## 任务输入模板

主维护 Agent 在交付临时任务时填写：

```text
任务目标：
基线分支与提交：
允许修改的文件：
禁止修改的文件：
验收标准：
必须运行的离线测试：
是否允许联网/fetch：否（除非明确改为是）
是否允许真实 API：否（除非明确改为是，并给出模型/尺寸/质量/数量）
是否允许 push/PR/merge/tag/Release：均否（每项需单独授权）
```

## 接管流程

1. 主维护 Agent 从权威仓库创建或刷新专用 clone，并指定准确基线。
2. 在基线上创建 `codex/` 任务分支，确认工作树干净。
3. 临时 Agent 阅读仓库规则、领域文档、验证文档、任务设计/计划和目标代码。
4. 运行基线离线门禁；失败时停止并报告。
5. 只修改授权文件，按测试先行方式形成最小提交。
6. 运行聚焦测试和完整离线门禁，检查差异与疑似凭据文件名。
7. 创建本地提交并按交付模板报告；不自行执行任何远端或发布动作。
8. 主维护 Agent 独立审查提交，决定返工、cherry-pick 或后续授权。

## 交付模板

```text
任务分支：
基线提交：
交付提交 SHA：
变更文件：
测试命令和结果：
未解决风险：
未执行动作：真实 API / push / PR / merge / tag / Release / 清理
建议集成方式：仅供主维护 Agent 审查后决定
```
```

- [ ] **Step 4: Run the handoff and full maintenance-document tests**

Run:

```powershell
python -m unittest tests.test_maintenance_docs.HandoffDocumentTests -v
python -m unittest tests.test_maintenance_docs -v
```

Expected: all maintenance-document tests pass.

- [ ] **Step 5: Commit the handoff document**

```powershell
git add -- docs/maintenance/HANDOFF.md tests/test_maintenance_docs.py
git commit -m "docs: add version-aware maintenance handoff"
```

### Task 3: Add Reproducible Offline Verification Gates

**Files:**
- Create: `docs/maintenance/VERIFICATION.md`
- Modify: `tests/test_maintenance_docs.py`

**Interfaces:**
- Consumes: `read_utf8(relative_path: str) -> str`, the project map from Task 2, and the existing CI commands.
- Produces: `suspected_secret_files(files: dict[str, str]) -> list[str]` plus exact preflight, focused, complete, diff, safe secret-scan, optional live-API, and delivery checks.

- [ ] **Step 1: Add failing secret-scanner and verification-document tests**

Insert these classes before the `if __name__ == "__main__":` block in `tests/test_maintenance_docs.py`. The scanner function intentionally does not exist yet:

```python
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
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
python -m unittest tests.test_maintenance_docs.SecretScanTests -v
python -m unittest tests.test_maintenance_docs.VerificationDocumentTests -v
```

Expected: the scanner tests error with `NameError: name 'suspected_secret_files' is not defined`; the verification-document test errors with `FileNotFoundError` for `docs/maintenance/VERIFICATION.md`.

- [ ] **Step 3: Implement the safe scanner and write the verification document**

Add `import subprocess` beside the existing imports in `tests/test_maintenance_docs.py`, then insert these helpers after `read_utf8()`:

```python
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
```

Create `docs/maintenance/VERIFICATION.md` with this content:

```markdown
# Lumenverba Image 维护验证

除“真实 API 门禁”外，本文件中的检查全部离线执行，不读取环境变量值，不调用真实 API。任何联网、计费或远端 Git 动作都必须由主维护 Agent 单独明确授权。

## 1. 基线预检

```powershell
git status --short --branch
git branch --show-current
git rev-parse HEAD
git log -1 --oneline --decorate
git tag --points-at HEAD
```

预期：位于任务指定的 `codex/` 分支，工作树干净，`HEAD` 与任务输入的基线一致。若不一致或已有未授权改动，停止并报告。

## 2. 聚焦测试

文档维护：

```powershell
python -m unittest tests.test_maintenance_docs -v
```

公开技能、CLI、网络或参数契约：

```powershell
python -m unittest discover -s tests -p "test_public_skill.py" -v
```

结果回执或历史回归：

```powershell
python -m unittest discover -s tests -p "test_regressions.py" -v
```

预期：目标测试全部通过，并且输出显示实际执行了测试。

## 3. 完整离线门禁

```powershell
python -m unittest discover -s tests -v
python -m unittest discover -v
python -m compileall -q skills tests
python skills/lumenverba-image/scripts/lumenverba_image.py --help
python skills/lumenverba-image/scripts/lumenverba_image.py generate --help
python skills/lumenverba-image/scripts/lumenverba_image.py edit --help
python skills/lumenverba-image/scripts/lumenverba_image.py text --help
python skills/lumenverba-image/scripts/lumenverba_image.py batch --help
git diff --check
```

预期：所有命令退出码为 0；两种 `unittest discover` 都执行完整测试集；CLI 帮助不发起网络请求。

## 4. 疑似凭据安全扫描

专用测试扫描全部 Git 跟踪的 UTF-8 文本，二进制文件跳过；结果只包含文件名，不包含匹配行或疑似值。现有 `tests/test_public_skill.py` 中用于断言禁止赋值的字面量只按准确文件路径和准确整行放行，不排除整个文件或目录。

```powershell
python -m unittest tests.test_maintenance_docs.SecretScanTests -v
```

预期：3 个扫描测试全部通过。失败信息只能列出可疑文件名；不得显示匹配内容，不读取、输出或记录密钥值。

## 5. 差异与提交检查

```powershell
git status --short --branch
git diff --check
git diff --stat
git diff --name-status
git diff
```

提交后再运行：

```powershell
git show --check --stat --oneline HEAD
git diff-tree --no-commit-id --name-status -r HEAD
git status --short --branch
```

预期：只有授权文件发生变化；提交通过格式检查；工作树干净。审查输出不得包含密钥、真实回执或生成图片。

## 6. 真实 API 门禁

默认不执行。只有主维护 Agent 对本次测试给出单独明确授权后才能进行，并且授权必须确定模型、尺寸、质量、数量、输出目录和唯一临时结果回执。

- 只使用授权的低额度单次创建请求；不读取环境变量值，只让客户端从环境继承认证。
- 回执和生成图片写入系统临时目录，不复制进仓库。
- 校验回执结构、返回数量、绝对路径、文件存在性和 PNG 签名；不输出认证头或环境变量值。
- 创建请求失败或状态未知时不得自动重试创建请求；只报告安全错误分类并等待新的明确授权。
- 测试成功不构成 push、PR、merge、tag 或 Release 授权。

## 7. 交付门禁

临时 Agent 报告任务分支、基线、提交 SHA、变更文件、每条测试命令及结果、未解决风险和未执行动作。随后停止；未经分别授权，不得 push、修改 PR、merge、创建或移动 tag、创建 Release，也不得删除维护 clone 或任务分支。
```

- [ ] **Step 4: Run the verification and all maintenance-document tests**

Run:

```powershell
python -m unittest tests.test_maintenance_docs.SecretScanTests -v
python -m unittest tests.test_maintenance_docs.VerificationDocumentTests -v
python -m unittest tests.test_maintenance_docs -v
```

Expected: all tests pass.

- [ ] **Step 5: Run the documented safe secret scan exactly as written**

Run the command from `docs/maintenance/VERIFICATION.md` section 4.

Expected: exit code 0 and 3 passing tests; no matching content is printed.

- [ ] **Step 6: Commit the verification document**

```powershell
git add -- docs/maintenance/VERIFICATION.md tests/test_maintenance_docs.py
git commit -m "docs: add offline maintenance verification gate"
```

### Task 4: Run an Offline Dedicated-Clone Handoff Drill

**Files:**
- Review: `AGENTS.md`
- Review: `docs/maintenance/HANDOFF.md`
- Review: `docs/maintenance/VERIFICATION.md`
- Review: `tests/test_maintenance_docs.py`
- Create outside repository: one uniquely named temporary local clone retained for user-approved cleanup

**Interfaces:**
- Consumes: the complete maintenance documentation and the current implementation-branch `HEAD`.
- Produces: evidence that a new Agent can enter a separate clone, identify the baseline/RC relationship, read all required documents, and pass the offline gate without credentials or network access.

- [ ] **Step 1: Run the complete gate in the implementation worktree**

Run:

```powershell
python -m unittest discover -s tests -v
python -m unittest discover -v
python -m compileall -q skills tests
python skills/lumenverba-image/scripts/lumenverba_image.py --help
python skills/lumenverba-image/scripts/lumenverba_image.py generate --help
python skills/lumenverba-image/scripts/lumenverba_image.py edit --help
python skills/lumenverba-image/scripts/lumenverba_image.py text --help
python skills/lumenverba-image/scripts/lumenverba_image.py batch --help
git diff --check
git status --short --branch
```

Expected: every command exits 0, both discovery commands execute the full suite, and the worktree is clean.

- [ ] **Step 2: Record immutable expected refs without reading credentials**

Run:

```powershell
$sourceRepo = (git rev-parse --show-toplevel).Trim()
$expectedHead = (git rev-parse HEAD).Trim()
$expectedStable = (git rev-parse 'v1.2.5^{}').Trim()
$expectedRc = (git rev-parse 'v1.2.6-rc.1^{}').Trim()
$drillRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('lumenverba-handoff-drill-' + [guid]::NewGuid().ToString('N'))
Write-Host "Drill clone: $drillRoot"
```

Expected: `$expectedStable` is `02b1731e5b5aa3e19e92a63b4a7d1e12d4f50703`, `$expectedRc` is `d88ba22109b5fdaa5632154d3f2e15752985218a`, and `$drillRoot` is a new uniquely named system-temporary path. Do not inspect `LUMENVERBA_API_KEY`.

- [ ] **Step 3: Create a physically independent local clone with no network**

Continue in the same PowerShell session:

```powershell
git clone --no-local --branch codex/agent-maintenance-handoff-design $sourceRepo $drillRoot
if ($LASTEXITCODE -ne 0) { throw 'Offline drill clone failed.' }
Set-Location -LiteralPath $drillRoot
git remote set-url origin https://github.com/yixixi-yahaha/lumenverba-image
```

Expected: clone succeeds without contacting GitHub, and `origin` is recorded as the authority URL only after cloning. No fetch or push occurs.

- [ ] **Step 4: Verify refs, documents, and isolation inside the clone**

Continue in the drill clone:

```powershell
$actualHead = (git rev-parse HEAD).Trim()
$actualStable = (git rev-parse 'v1.2.5^{}').Trim()
$actualRc = (git rev-parse 'v1.2.6-rc.1^{}').Trim()
if ($actualHead -ne $expectedHead) { throw 'Drill HEAD differs from source HEAD.' }
if ($actualStable -ne $expectedStable) { throw 'Stable tag target differs.' }
if ($actualRc -ne $expectedRc) { throw 'RC tag target differs.' }
@('AGENTS.md', 'CONTEXT.md', 'docs/maintenance/HANDOFF.md', 'docs/maintenance/VERIFICATION.md') | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_ -PathType Leaf)) { throw "Missing handoff file: $_" }
}
if ((git remote get-url origin).Trim() -ne 'https://github.com/yixixi-yahaha/lumenverba-image') {
    throw 'Authority remote URL is incorrect.'
}
git status --short --branch
```

Expected: all comparisons pass, all four onboarding files exist, `origin` is the GitHub authority URL, and the drill clone is clean.

- [ ] **Step 5: Run the offline gate from the fresh clone**

Run:

```powershell
python -m unittest discover -s tests -v
python -m unittest discover -v
python -m compileall -q skills tests
python skills/lumenverba-image/scripts/lumenverba_image.py --help
python skills/lumenverba-image/scripts/lumenverba_image.py generate --help
python skills/lumenverba-image/scripts/lumenverba_image.py edit --help
python skills/lumenverba-image/scripts/lumenverba_image.py text --help
python skills/lumenverba-image/scripts/lumenverba_image.py batch --help
git diff --check
git status --short --branch
```

Expected: every command exits 0, both discovery commands execute the same nonzero test count as the implementation worktree, and the clone remains clean.

- [ ] **Step 6: Retain the drill clone and report the handoff evidence**

Do not delete `$drillRoot`. Report its exact path, the source and drill `HEAD`, stable and RC tag targets, test counts, command results, and the fact that no live API, fetch, push, PR change, merge, tag creation/movement, or Release occurred. Destructive cleanup of the drill clone requires separate user authorization.

- [ ] **Step 7: Review the final implementation branch without publishing**

Return to the implementation worktree and run:

```powershell
git status --short --branch
git log --oneline --decorate origin/main..HEAD
git diff --check origin/main...HEAD
git diff --stat origin/main...HEAD
git diff --name-status origin/main...HEAD
```

Expected: the branch contains the approved design/plan plus the three maintenance-document commits; runtime code, `README.md`, `SKILL.md`, stable metadata, PR #4, and `v1.2.6-rc.1` are unchanged. Stop here: do not push, modify a PR, merge, create or move a tag, create a Release, or call the live API.
