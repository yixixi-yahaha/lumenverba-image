# Lumenverba v1.2.5 Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish-ready v1.2.5 sources that prevent task-address credential disclosure, never retry billable creation requests, retry safe reads once, and enforce a reproducible release gate.

**Architecture:** Keep the portable standard-library client as the only runtime. Harden the existing `_task_location()` boundary before authenticated polling, make `_send()` retry behavior depend on request semantics, and express release policy through tests, CI, documentation, and ADRs.

**Tech Stack:** Python 3.11+ standard library, `unittest`, GitHub Actions, Markdown, Git.

## Global Constraints

- `main` is the only release source; existing tags are immutable.
- The production endpoint remains `https://api.lumenverba.cc/v1`.
- Creation requests never retry automatically; read requests retry at most once.
- Task polling sends credentials only to trusted task addresses.
- The client remains dependency-free and supports Python 3.11+.
- v1.2.5 contains no new image-generation features.
- Normal CI never calls the live Lumenverba API or reads an API key.
- A manual low-budget live smoke test is required before publishing a tag.

---

### Task 1: Record the domain and release decisions

**Files:**
- Create: `CONTEXT.md`
- Create: `docs/adr/0001-main-is-the-only-release-source.md`
- Create: `docs/adr/0002-task-addresses-must-be-trusted.md`
- Create: `docs/adr/0003-retry-read-requests-only.md`

**Interfaces:**
- Consumes: the confirmed v1.2.5 release decisions.
- Produces: canonical terms and architectural constraints used by Tasks 2-5.

- [ ] **Step 1: Write the glossary and ADRs**

Define `Creation request`, `Read request`, `Trusted task address`, `Result receipt`, `Release source`, and `Release gate`. Record why releases come only from `main`, why task addresses are same-origin and namespace-bound, and why only reads retry.

- [ ] **Step 2: Verify the documents contain no machine-specific paths**

Run:

```powershell
rg -n -i "C:/Users|C:\\Users|songmajun" CONTEXT.md docs/adr
```

Expected: no matches.

- [ ] **Step 3: Commit the decision record**

```powershell
git add CONTEXT.md docs/adr
git commit -m "docs: define v1.2.5 safety boundaries"
```

### Task 2: Reject untrusted asynchronous task addresses

**Files:**
- Modify: `skills/lumenverba-image/scripts/lumenverba_image.py:284`
- Test: `tests/test_public_skill.py`

**Interfaces:**
- Consumes: `Settings.base_url` and an HTTP `Location` header.
- Produces: `_task_location(headers: dict[str, str], settings: Settings) -> str`, returning only a trusted absolute task URL.

- [ ] **Step 1: Write failing task-address tests**

Add tests equivalent to:

```python
def test_accepted_task_rejects_external_https_location(self):
    client = load_public_client()
    with self.assertRaisesRegex(RuntimeError, "不安全的任务地址"):
        client._task_location(
            {"Location": "https://attacker.example/v1/tasks/task-1"},
            client.Settings("test-key"),
        )

def test_task_location_rejects_untrusted_url_shapes(self):
    client = load_public_client()
    invalid = (
        "//api.lumenverba.cc/v1/tasks/task-1",
        "https://api.lumenverba.cc:444/v1/tasks/task-1",
        "https://user@api.lumenverba.cc/v1/tasks/task-1",
        "https://api.lumenverba.cc/v1/tasks/task-1#fragment",
        "https://api.lumenverba.cc/private/task-1",
    )
    for location in invalid:
        with self.subTest(location=location):
            with self.assertRaisesRegex(RuntimeError, "不安全的任务地址"):
                client._task_location({"Location": location}, client.Settings("test-key"))
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
python -m unittest discover -s tests -p "test_public_skill.py" -v
```

Expected: failures because external HTTPS and other untrusted shapes are currently accepted.

- [ ] **Step 3: Implement the minimal trusted-address validation**

Update `_task_location()` to reject protocol-relative values before `urljoin`, parse the resolved URL and base URL, and require HTTPS, identical hostname, effective port 443, no user information, no fragment, and a `/v1/` path prefix. Convert invalid-port parsing into the same safe `RuntimeError`.

- [ ] **Step 4: Run the focused and polling tests**

Run:

```powershell
python -m unittest discover -s tests -p "test_public_skill.py" -v
```

Expected: all pass.

- [ ] **Step 5: Commit the credential-boundary fix**

```powershell
git add tests/test_public_skill.py skills/lumenverba-image/scripts/lumenverba_image.py
git commit -m "fix: restrict authenticated task polling"
```

### Task 3: Retry reads but never creation requests

**Files:**
- Modify: `skills/lumenverba-image/scripts/lumenverba_image.py:164`
- Modify: `tests/test_public_skill.py`
- Modify: `tests/test_regressions.py`

**Interfaces:**
- Consumes: `_send(method, url, headers, body)` calls made by creation, polling, and download paths.
- Produces: no retry for non-GET calls; one retry for eligible GET failures; safe retry notices for successful read recovery.

- [ ] **Step 1: Write failing request-semantics tests**

Replace the POST-retry expectation and add a GET retry test:

```python
def test_creation_request_network_error_is_not_retried(self):
    client = load_public_client()
    error = client.urllib.error.URLError(client.ssl.SSLError("private TLS detail"))
    with patch.object(client.urllib.request, "urlopen", side_effect=error) as urlopen:
        with self.assertRaisesRegex(RuntimeError, "生成状态未知.*创建请求未自动重试"):
            client._send("POST", "https://api.lumenverba.cc/v1/images/generations", {})
    self.assertEqual(urlopen.call_count, 1)

def test_read_request_retries_one_safe_network_failure(self):
    client = load_public_client()
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 200
    response.headers = {"Content-Type": "application/json"}
    response.read.return_value = b"{}"
    first = client.urllib.error.URLError(client.ssl.SSLError("private TLS detail"))
    with patch.object(client.urllib.request, "urlopen", side_effect=[first, response]) as urlopen:
        with redirect_stderr(StringIO()):
            client._send("GET", "https://api.lumenverba.cc/v1/tasks/task-1", {})
    self.assertEqual(urlopen.call_count, 2)
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
python -m unittest discover -s tests -p "test_public_skill.py" -v
```

Expected: the creation test fails because POST currently retries.

- [ ] **Step 3: Implement method-aware retry behavior**

In `_send()`, retry only when `method.upper() == "GET"` and the first failure category is in the safe read-retry set. Creation failures report unknown generation state and explicitly state that the creation request was not retried. Successful GET recovery continues to emit `RETRY_NOTICE:`.

- [ ] **Step 4: Update the end-to-end retry regression**

Change the result-receipt regression to return HTTP 202 for the creation call, fail the first task GET with TLS, then return the completed image on the single GET retry. Assert that the image succeeds and the receipt contains the safe retry notice.

- [ ] **Step 5: Run retry and receipt tests**

Run:

```powershell
python -m unittest discover -s tests -p "test_public_skill.py" -v
python -m unittest discover -s tests -p "test_regressions.py" -v
```

Expected: all pass.

- [ ] **Step 6: Commit the retry-boundary fix**

```powershell
git add tests/test_public_skill.py tests/test_regressions.py skills/lumenverba-image/scripts/lumenverba_image.py
git commit -m "fix: retry read requests only"
```

### Task 4: Align v1.2.5 documentation and release metadata

**Files:**
- Modify: `README.md`
- Modify: `skills/lumenverba-image/SKILL.md`
- Modify: `tests/test_public_skill.py`
- Create: `LICENSE`

**Interfaces:**
- Consumes: the Task 2 and Task 3 behavior.
- Produces: consistent user-facing v1.2.5 install, retry, release, and license contracts.

- [ ] **Step 1: Write failing documentation-contract tests**

Update the version assertions to `v1.2.5`, require README and skill text describing creation/read retry boundaries, and assert that `LICENSE` contains `MIT License` and `2026 yixixi-yahaha`.

- [ ] **Step 2: Run packaged-skill tests and verify RED**

Run:

```powershell
python -m unittest discover -s tests -p "test_public_skill.py" -v
```

Expected: failures for v1.2.5, retry wording, and the missing license.

- [ ] **Step 3: Update the public contract**

Point README installation examples to `v1.2.5`; describe that creation requests never retry and read requests retry eligible failures once; document the exact offline release command and manual smoke gate. Update `SKILL.md` to use the same retry terminology and retain receipt delivery rules. Add the standard MIT License with copyright `2026 yixixi-yahaha`.

- [ ] **Step 4: Run packaged-skill tests**

Run:

```powershell
python -m unittest discover -s tests -p "test_public_skill.py" -v
```

Expected: all pass.

- [ ] **Step 5: Commit the release contract**

```powershell
git add README.md LICENSE skills/lumenverba-image/SKILL.md tests/test_public_skill.py
git commit -m "docs: prepare v1.2.5 safety release"
```

### Task 5: Add a reproducible offline CI gate

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `tests/__init__.py`
- Modify: `tests/test_public_skill.py`

**Interfaces:**
- Consumes: the complete v1.2.5 source tree.
- Produces: required Windows and Ubuntu verification on Python 3.11 and 3.14 with no live API access.

- [ ] **Step 1: Add release-gate assertions**

Add tests that scan tracked public text for machine-specific paths and verify README, `SKILL.md`, and the expected stable version agree. Add an empty `tests/__init__.py` so default discovery recurses into `tests/`.

- [ ] **Step 2: Verify default discovery executes tests**

Run:

```powershell
python -m unittest discover -v
```

Expected: more than zero tests execute and all pass.

- [ ] **Step 3: Add the GitHub Actions workflow**

Create a matrix for `windows-latest` and `ubuntu-latest` with Python `3.11` and `3.14`. Run unit discovery, `compileall`, root and subcommand help, and `git diff --check HEAD^ HEAD` with enough checkout history. Do not configure secrets or live network tests.

- [ ] **Step 4: Run the complete local gate**

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
git diff --check HEAD^ HEAD
```

Expected: all commands exit 0; both discovery commands execute the full suite.

- [ ] **Step 5: Commit the CI gate**

```powershell
git add .github/workflows/ci.yml tests/__init__.py tests/test_public_skill.py
git commit -m "ci: enforce v1.2.5 release gate"
```

### Task 6: Review without publishing

**Files:**
- Review: all changed files

**Interfaces:**
- Consumes: Tasks 1-5.
- Produces: a verified local branch ready for human review, live smoke testing, merge to `main`, and later v1.2.5 tagging.

- [ ] **Step 1: Inspect the final change set**

Run:

```powershell
git status --short --branch
git diff --stat v1.2.4...HEAD
git diff --check v1.2.4...HEAD
```

Expected: only the planned security, documentation, test, CI, and license files differ.

- [ ] **Step 2: Confirm no release side effects occurred**

Do not push, merge, create a tag, create a GitHub Release, or call the live API. Report those as explicit remaining release steps requiring separate authorization and the manual smoke-test key.
