# Safe Network Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retry one clearly unsubmitted Lumenverba network operation once and, when images are ultimately delivered, expose the first safe failure category to the user.

**Architecture:** Keep retry policy inside the portable client's `_send()` boundary so every generation, polling, and download call uses the same rule. Emit a stable `RETRY_NOTICE:` line on stderr after a retry reaches an HTTP response; the packaged skill treats that line as delivery metadata only when stdout contains successful PNG paths.

**Tech Stack:** Python 3.11+, Python standard library, `unittest`, Markdown.

## Global Constraints

- Retry at most once per HTTP operation and reuse the exact method, URL, headers, and body.
- Only `DNS 解析失败`, `TLS 连接失败`, `连接被拒绝`, and `代理连接失败` are retryable.
- Do not retry `网络连接超时`, a connection closed after transmission may have begun, generic `网络连接失败`, HTTP responses, task failures, parsing failures, missing images, or unknown generation status.
- A retry must not change prompt, model, size, quality, count, references, output directory, or generation mode.
- Successful stdout remains PNG absolute paths only.
- Never expose raw exception text, host details, proxy credentials, API keys, or tokens.
- Do not add dependencies, configurable retry counts, backoff, persistent state, prompt rewriting, visual inspection, or MCP changes.

---

### Task 1: Retry Safe Network Failures Once

**Files:**
- Modify: `tests/test_public_skill.py:64-81`
- Modify: `skills/lumenverba-image/scripts/lumenverba_image.py:32-149`

**Interfaces:**
- Consumes: `_network_error_category(reason: object) -> str` and `_send(method: str, url: str, headers: dict[str, str], body: bytes = b"") -> tuple[int, dict[str, str], bytes]`.
- Produces: `RETRYABLE_NETWORK_ERROR_CATEGORIES`, `RETRY_NOTICE_PREFIX`, one identical retry for safe categories, and stable safe stderr diagnostics.

- [ ] **Step 1: Replace the old network recovery test with failing retry tests**

Add `MagicMock` to the existing mock import:

```python
from unittest.mock import MagicMock, patch
```

Replace `test_network_error_reports_a_safe_category_and_network_recovery()` with these tests:

```python
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
```

Keep `test_network_error_categories_do_not_expose_raw_error_text()` unchanged.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
python -m unittest \
  tests.test_public_skill.PortableClientTests.test_retryable_network_error_is_retried_once_and_reports_a_safe_notice \
  tests.test_public_skill.PortableClientTests.test_timeout_is_not_retried \
  tests.test_public_skill.PortableClientTests.test_second_network_failure_is_reported_without_a_third_attempt \
  -v
```

Expected: all three tests fail against the current single-attempt implementation. The first raises instead of succeeding, the timeout diagnostic lacks `未自动重试`, and the two-failure test records only one `urlopen` call.

- [ ] **Step 3: Implement the minimum retry policy**

Add these constants beside the existing timeout and polling constants:

```python
RETRYABLE_NETWORK_ERROR_CATEGORIES = {
    "DNS 解析失败",
    "TLS 连接失败",
    "连接被拒绝",
    "代理连接失败",
}
RETRY_NOTICE_PREFIX = "RETRY_NOTICE:"
```

Replace `_send()` with:

```python
def _send(method: str, url: str, headers: dict[str, str], body: bytes = b"") -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url=url, data=body, headers=headers, method=method)

    def send_once() -> tuple[int, dict[str, str], bytes]:
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.status, dict(response.headers.items()), response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers.items()), error.read(MAX_RESPONSE_BYTES + 1)

    try:
        return send_once()
    except urllib.error.URLError as first_error:
        first_category = _network_error_category(first_error.reason)
        if first_category not in RETRYABLE_NETWORK_ERROR_CATEGORIES:
            raise RuntimeError(
                f"调用图像服务时发生{first_category}，生成状态未知，未自动重试。"
            ) from first_error

    try:
        result = send_once()
    except urllib.error.URLError as second_error:
        second_category = _network_error_category(second_error.reason)
        raise RuntimeError(
            f"调用图像服务首次发生{first_category}；自动重试后发生{second_category}，生成状态未知。"
        ) from second_error

    print(
        f"{RETRY_NOTICE_PREFIX} 首次调用失败：{first_category}；已自动重试 1 次。",
        file=sys.stderr,
    )
    return result
```

Do not add sleeps or configurable retry state. Do not retry `HTTPError`; `send_once()` continues to return it as an HTTP response.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the command from Step 2.

Expected: 3 tests pass. The retryable operation calls `urlopen` twice, the timeout calls it once, and the second failure never creates a third attempt.

- [ ] **Step 5: Run all client tests**

Run:

```bash
python -m unittest tests.test_public_skill.PortableClientTests -v
```

Expected: all portable client tests pass with no unexpected warnings.

- [ ] **Step 6: Commit the client behavior**

```bash
git add tests/test_public_skill.py skills/lumenverba-image/scripts/lumenverba_image.py
git commit -m "feat: retry safe network failures once"
```

### Task 2: Document Retry Delivery Semantics

**Files:**
- Modify: `tests/test_public_skill.py:374-414`
- Modify: `skills/lumenverba-image/SKILL.md:26-42`
- Modify: `README.md:96`

**Interfaces:**
- Consumes: `RETRY_NOTICE:` and the four retryable categories produced by Task 1.
- Produces: packaged skill instructions that show successful images before the first failure reason and forbid command-level retries.

- [ ] **Step 1: Change documentation contract tests before documentation**

In `test_skill_documents_fast_batch_workflow()`, replace `"不得自动重试"` with these strings:

```python
"自动重试 1 次",
"RETRY_NOTICE:",
"首次失败原因",
```

Replace `test_skill_documents_network_recovery_after_an_unknown_state()` with:

```python
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

    for forbidden in ("回复“允许联网”", "重新发送该请求", "不得自动重试"):
        with self.subTest(forbidden=forbidden):
            self.assertNotIn(forbidden, content)
```

Add retry documentation expectations to `test_readme_documents_batch_commands_and_limit()`:

```python
"安全连接错误自动重试 1 次",
"首次失败原因",
"网络连接超时不自动重试",
```

- [ ] **Step 2: Run the documentation tests and verify RED**

Run:

```bash
python -m unittest \
  tests.test_public_skill.PackagedSkillTests.test_skill_documents_fast_batch_workflow \
  tests.test_public_skill.PackagedSkillTests.test_skill_documents_safe_retry_boundary_and_delivery_notice \
  tests.test_public_skill.PackagedSkillTests.test_readme_documents_batch_commands_and_limit \
  -v
```

Expected: the tests fail because the current documents forbid all automatic retries and still instruct the user to resend the request.

- [ ] **Step 3: Update packaged skill instructions**

Replace the network-error sentence in `skills/lumenverba-image/SKILL.md` with:

```markdown
- 执行时以技能目录中的 `scripts/lumenverba_image.py` 为脚本路径。脚本成功时 stdout 只返回生成 PNG 的绝对路径；失败诊断和重试提示写入 stderr。脚本仅对 `DNS 解析失败`、`TLS 连接失败`、`连接被拒绝`、`代理连接失败`自动重试 1 次；`网络连接超时`、连接中途关闭、通用网络失败和生成状态未知不得自动重试。
```

Add this result-delivery rule after the existing stdout rule:

```markdown
- 若 stderr 包含 `RETRY_NOTICE:` 且 stdout 包含成功 PNG，先展示全部成功图片，再附注“首次失败原因：<安全分类>；自动重试一次后成功。”；不得把该提示当作批次失败。
```

Replace the blanket retry prohibition with:

```markdown
- 不得自动调整提示词、重新生成、在脚本之外重试创建请求或把单请求多图改为并发单图。
```

- [ ] **Step 4: Update README retry documentation**

Replace the final sentence below the CLI examples with:

```markdown
全部成功时退出码为 `0`。部分失败时已成功图片仍保留并输出，失败批次项写入标准错误，退出码为 `1`。脚本会对 DNS、TLS、连接被拒绝和代理等安全连接错误自动重试 1 次；网络连接超时、连接中途关闭、生成状态未知和其他错误不自动重试。若重试后成功生成图片，Codex 会在展示图片后附带首次失败原因。
```

- [ ] **Step 5: Run documentation tests and verify GREEN**

Run the command from Step 2.

Expected: 3 tests pass.

- [ ] **Step 6: Run complete verification**

Run:

```bash
python -m unittest discover -s tests -v
git diff --check
rg -n '回复“允许联网”|重新发送该请求|不得自动重试' README.md skills tests
rg -n 'RETRY_NOTICE:|自动重试 1 次|首次失败原因|网络连接超时.*不自动重试' README.md skills tests
```

Expected:

- The full suite passes.
- `git diff --check` exits 0.
- The stale retry-prohibition search returns no matches outside historical design/plan documents.
- The new retry contract appears in the script tests, packaged skill, README, and documentation tests.

- [ ] **Step 7: Commit documentation and contracts**

```bash
git add tests/test_public_skill.py skills/lumenverba-image/SKILL.md README.md
git commit -m "docs: explain safe retry results"
```

After committing, run:

```bash
python -m unittest discover -s tests -v
git diff --check HEAD~2..HEAD
git diff --name-status HEAD~2..HEAD
```

Expected: all tests pass, no whitespace errors exist, and the implementation touches only the client, tests, skill instructions, README, plan, and design required for this feature.
