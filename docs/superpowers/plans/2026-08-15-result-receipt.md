# Result Receipt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a trusted per-command JSON receipt so the skill can deliver generated images when Codex loses terminal stdout, stderr, and the exit code.

**Architecture:** The portable client accepts an optional absolute `--result-file`, collects the same paths and safe diagnostics it already prints, and atomically writes a versioned JSON receipt after the outcome is known. The skill always supplies a unique receipt path and reads only that file as a fallback; stdout remains the primary channel and output directories are never scanned.

**Tech Stack:** Python 3.11+, Python standard library, `unittest`, Markdown.

## Global Constraints

- Preserve stdout as PNG absolute paths only and stderr as diagnostics plus `RETRY_NOTICE:` metadata.
- Do not change API requests, generation concurrency, retry policy, prompts, image validation, or default counts.
- The receipt must contain only the current invocation's paths and safe client diagnostics.
- The receipt must be UTF-8 JSON and atomically replace a temporary sibling file.
- The skill must never scan output directories or repeat generation when terminal output is missing.
- Add no dependencies and do not create a persistent job database.

---

### Task 1: Write Versioned Result Receipts

**Files:**
- Modify: `tests/test_public_skill.py`
- Modify: `skills/lumenverba-image/scripts/lumenverba_image.py`

**Interfaces:**
- Consumes: `main(argv: list[str] | None = None) -> int`, successful `Path` lists, and existing safe error strings.
- Produces: CLI option `--result-file`, `_write_result_receipt(result_file, exit_code, paths, errors)`, and JSON fields `version`, `status`, `exit_code`, `paths`, `errors`.

- [ ] **Step 1: Write failing client tests**

Add tests that parse `--result-file` for `generate`, `edit`, `text`, and `batch`; run a successful mocked generation and assert the receipt contains one absolute path with `status: success`; run a mocked exception and assert `status: error`; run a one-of-two result and assert `status: partial` with the existing numbered error.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
python -m unittest discover -s tests -p test_public_skill.py -k result_receipt -v
```

Expected: parser rejects `--result-file` or no receipt file is created.

- [ ] **Step 3: Add the option and atomic writer**

Add `--result-file` as `Path` to every command parser. Implement:

```python
def _write_result_receipt(
    result_file: Path | None,
    exit_code: int,
    paths: list[Path],
    errors: list[str],
) -> None:
    if result_file is None:
        return
    status = "success" if exit_code == 0 else "partial" if paths else "error"
    payload = {
        "version": 1,
        "status": status,
        "exit_code": exit_code,
        "paths": [str(path) for path in paths],
        "errors": errors,
    }
    result_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = result_file.with_name(f".{result_file.name}.{secrets.token_hex(4)}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(result_file)
    finally:
        temporary.unlink(missing_ok=True)
```

Reject a relative result path before any API call. Refactor result printing only enough to collect the identical path and error lists for the receipt.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all result receipt tests pass and stdout assertions remain unchanged.

- [ ] **Step 5: Run all portable client tests**

Run:

```powershell
python -m unittest tests.test_public_skill.PortableClientTests -v
```

Expected: every portable client test passes.

### Task 2: Teach the Skill to Recover from a Lost Command Result

**Files:**
- Modify: `tests/test_public_skill.py`
- Modify: `skills/lumenverba-image/SKILL.md`

**Interfaces:**
- Consumes: the Task 1 receipt schema and a preselected unique absolute receipt path.
- Produces: a deterministic fallback sequence that reads the exact receipt and delivers its paths without scanning or regenerating.

- [ ] **Step 1: Write failing documentation contract tests**

Require the skill to contain `--result-file`, `唯一`, `完整 stdout、stderr 和退出码`, `读取该回执`, `不得扫描输出目录`, and `不得重新执行生图命令`.

- [ ] **Step 2: Run the documentation test and verify RED**

Run:

```powershell
python -m unittest discover -s tests -p test_public_skill.py -k result_receipt -v
```

Expected: the documentation contract test fails because `v1.2.2` has no receipt fallback.

- [ ] **Step 3: Update the skill contract**

Require every final command to receive a unique absolute `--result-file`. State stdout-first delivery, exact-receipt fallback after missing terminal output, schema/path validation, and unknown-state handling when no valid receipt exists. Preserve the directory-scan and external-retry prohibitions.

- [ ] **Step 4: Run documentation tests and verify GREEN**

Run the Step 2 command. Expected: all result receipt tests pass.

### Task 3: Verify Packaging and Lost-Output Recovery

**Files:**
- Modify: `C:/Users/songmajun/.codex/skills/lumenverba-image/SKILL.md`
- Modify: `C:/Users/songmajun/.codex/skills/lumenverba-image/scripts/lumenverba_image.py`

**Interfaces:**
- Consumes: verified packaged source files from Tasks 1 and 2.
- Produces: identical installed files and a local proof that a receipt can recover paths without stdout.

- [ ] **Step 1: Run the complete source suite**

```powershell
python -m unittest discover -s tests -p test_*.py -v
```

Expected: all tests pass.

- [ ] **Step 2: Synchronize the installed skill**

Copy only the verified `SKILL.md` and `scripts/lumenverba_image.py` contents to the installed skill directory.

- [ ] **Step 3: Simulate a lost execution result without API cost**

Use the installed module with a mocked successful `generate()` call, redirect stdout/stderr away from the harness, and assert that the preselected receipt still contains the expected PNG absolute path. Read that exact JSON file and validate the named PNG signature.

- [ ] **Step 4: Run final verification**

```powershell
python -m unittest discover -s tests -p test_*.py -v
git diff --check
git status --short
```

Expected: all tests pass, no whitespace errors exist, and only the design, plan, client, skill, and tests changed.
