# GPT Image 2 Flexible Sizes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Lumenverba 图像技能仅使用 `gpt-image-2`，支持官方 `auto` 与任意合法输出尺寸，并在不阻断请求的前提下警告实验分辨率。

**Architecture:** 保留单文件标准库客户端，在请求构建边界增加一个纯尺寸校验函数，并让 CLI 的 `argparse` 类型转换复用它。分辨率档位只由 `SKILL.md` 映射为具体 `WIDTHxHEIGHT`；实验范围仅增加一次 `stderr` 警告，不进入请求字段、结果错误或重试流程。

**Tech Stack:** Python 3.11+ 标准库、`argparse`、`unittest`、Markdown、PowerShell。

## Global Constraints

- 唯一支持模型为 `gpt-image-2`；其他模型必须在联网前拒绝。
- 默认 `size` 为 `auto`；显式尺寸格式为小写 `WIDTHxHEIGHT`。
- 最长边不超过 `3840px`，两边均为 `16px` 的倍数，长短边之比不超过 `3:1`。
- 总像素必须在 `655,360` 到 `8,294,400` 之间。
- 显式尺寸总像素大于 `3,686,400` 时警告但允许执行；`auto` 不预判、不警告。
- `quality` 仅允许 `low`、`medium`、`high`、`auto`，默认 `medium`；不兼容 `standard`。
- 分辨率档位只写入 `SKILL.md`，不得进入 Python CLI 选项或请求参数。
- 不增加第三方依赖，不改变 API 端点、请求重试、结果回执、批处理或图片保存行为。
- 创建请求不得自动重试；真实 API 测试不得输出、记录或提交密钥。

---

### Task 1: Enforce the official model, quality, and size contract

**Files:**
- Modify: `tests/test_public_skill.py:244-265`
- Modify: `tests/test_public_skill.py:400-421`
- Modify: `skills/lumenverba-image/scripts/lumenverba_image.py:25-111`
- Modify: `skills/lumenverba-image/scripts/lumenverba_image.py:476-502`

**Interfaces:**
- Consumes: existing `_select(value, allowed, default, label)` for enumerated model and quality values.
- Produces: `_size_dimensions(size: str) -> tuple[int, int]` and `_select_size(value: str | None) -> str` for request construction and CLI parsing.
- Produces: `build_generation_request(...)` with defaults `model=gpt-image-2`, `size=auto`, `quality=medium`.

- [ ] **Step 1: Write failing tests for defaults and accepted values**

Replace the default assertions and add focused acceptance tests inside `PortableClientTests`:

```python
def test_defaults_are_used_for_a_generation_payload(self):
    client = load_public_client()

    payload = client.build_generation_request("海鸥在码头吃薯条")

    self.assertEqual(payload["model"], "gpt-image-2")
    self.assertEqual(payload["size"], "auto")
    self.assertEqual(payload["quality"], "medium")
    self.assertEqual(payload["n"], 1)
    self.assertTrue(payload["stream"])
    self.assertEqual(payload["partial_images"], 1)

def test_gpt_image_2_accepts_auto_and_flexible_sizes(self):
    client = load_public_client()
    valid_sizes = (
        "auto",
        "1024x640",
        "1536x512",
        "1280x768",
        "1024x1024",
        "1536x1024",
        "1024x1536",
        "2048x1152",
        "2048x2048",
        "3840x2160",
        "2160x3840",
    )

    for size in valid_sizes:
        with self.subTest(size=size):
            payload = client.build_generation_request("测试", size=size)
            self.assertEqual(payload["size"], size)

def test_gpt_image_2_accepts_official_quality_values(self):
    client = load_public_client()

    for quality in ("low", "medium", "high", "auto"):
        with self.subTest(quality=quality):
            payload = client.build_generation_request("测试", quality=quality)
            self.assertEqual(payload["quality"], quality)
```

Update the edit request fixture to pass `"medium"` instead of `"standard"`:

```python
body, content_type = client.build_edit_request(
    "保留人物姿势",
    [first, second],
    "gpt-image-2",
    "1024x1024",
    "medium",
)
```

- [ ] **Step 2: Write failing tests for every rejection boundary**

Add these methods to `PortableClientTests`:

```python
def test_custom_sizes_enforce_official_constraints(self):
    client = load_public_client()
    invalid_sizes = (
        ("1024", "WIDTHxHEIGHT"),
        ("1024X1024", "WIDTHxHEIGHT"),
        ("0x1024", "大于 0"),
        ("1025x1024", "16"),
        ("3856x1024", "3840"),
        ("2048x512", "3:1"),
        ("1024x512", "655,360"),
        ("3840x2176", "8,294,400"),
    )

    for size, message in invalid_sizes:
        with self.subTest(size=size):
            with self.assertRaisesRegex(ValueError, message):
                client.build_generation_request("测试", size=size)

def test_rejects_non_gpt_image_2_models_and_nonofficial_quality(self):
    client = load_public_client()

    for model in ("gpt-image-1", "gpt-image-1.5", "unknown"):
        with self.subTest(model=model):
            with self.assertRaisesRegex(ValueError, "不支持的模型"):
                client.build_generation_request("测试", model=model)

    for quality in ("standard", "ultra"):
        with self.subTest(quality=quality):
            with self.assertRaisesRegex(ValueError, "不支持的质量"):
                client.build_generation_request("测试", quality=quality)
```

- [ ] **Step 3: Run the focused tests and verify the red state**

Run:

```powershell
python -m unittest tests.test_public_skill.PortableClientTests.test_defaults_are_used_for_a_generation_payload tests.test_public_skill.PortableClientTests.test_gpt_image_2_accepts_auto_and_flexible_sizes tests.test_public_skill.PortableClientTests.test_gpt_image_2_accepts_official_quality_values tests.test_public_skill.PortableClientTests.test_custom_sizes_enforce_official_constraints tests.test_public_skill.PortableClientTests.test_rejects_non_gpt_image_2_models_and_nonofficial_quality -v
```

Expected: failures show the old `1536x1024`/`standard` defaults, rejected custom sizes, accepted old models, or accepted `standard`.

- [ ] **Step 4: Implement one reusable size validator**

Add `import re`, replace the parameter constants, retain `_select` for model and quality, and add the following helpers:

```python
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_SIZE = "auto"
DEFAULT_QUALITY = "medium"
ALLOWED_MODELS = {"gpt-image-2"}
ALLOWED_QUALITIES = {"auto", "high", "low", "medium"}
MIN_OUTPUT_PIXELS = 655_360
MAX_OUTPUT_PIXELS = 8_294_400
MAX_OUTPUT_EDGE = 3840
OUTPUT_EDGE_MULTIPLE = 16
MAX_OUTPUT_ASPECT_RATIO = 3


def _size_dimensions(size: str) -> tuple[int, int]:
    match = re.fullmatch(r"([0-9]+)x([0-9]+)", size)
    if match is None:
        raise ValueError(f"尺寸必须使用 WIDTHxHEIGHT 格式: {size}")
    return int(match.group(1)), int(match.group(2))


def _select_size(value: str | None) -> str:
    selected = value or DEFAULT_SIZE
    if selected == "auto":
        return selected

    width, height = _size_dimensions(selected)
    if width <= 0 or height <= 0:
        raise ValueError("尺寸两边必须大于 0。")
    if max(width, height) > MAX_OUTPUT_EDGE:
        raise ValueError("尺寸最长边不能超过 3840px。")
    if width % OUTPUT_EDGE_MULTIPLE or height % OUTPUT_EDGE_MULTIPLE:
        raise ValueError("尺寸两边必须是 16px 的倍数。")
    if max(width, height) > min(width, height) * MAX_OUTPUT_ASPECT_RATIO:
        raise ValueError("尺寸长边与短边之比不能超过 3:1。")

    pixels = width * height
    if pixels < MIN_OUTPUT_PIXELS:
        raise ValueError("尺寸总像素不能少于 655,360。")
    if pixels > MAX_OUTPUT_PIXELS:
        raise ValueError("尺寸总像素不能超过 8,294,400。")
    return selected
```

Use it in `build_generation_request`:

```python
return {
    "model": _select(model, ALLOWED_MODELS, DEFAULT_MODEL, "模型"),
    "prompt": prompt,
    "size": _select_size(size),
    "quality": _select(quality, ALLOWED_QUALITIES, DEFAULT_QUALITY, "质量"),
    "n": _select_count(count),
    "stream": True,
    "partial_images": 1,
}
```

Remove `ALLOWED_SIZES`. In `_parser()`, replace both `--size` declarations with `type=_select_size` while keeping model and quality as enumerated choices:

```python
current.add_argument("--model", choices=sorted(ALLOWED_MODELS))
current.add_argument("--size", type=_select_size)
current.add_argument("--quality", choices=sorted(ALLOWED_QUALITIES))
```

```python
batch_parser.add_argument("--model", choices=sorted(ALLOWED_MODELS))
batch_parser.add_argument("--size", type=_select_size)
batch_parser.add_argument("--quality", choices=sorted(ALLOWED_QUALITIES))
```

- [ ] **Step 5: Add a parser test covering every command**

Add to `PortableClientTests`:

```python
def test_every_command_accepts_the_same_flexible_size(self):
    client = load_public_client()
    commands = (
        ["generate", "--prompt", "测试", "--size", "1280x768"],
        ["edit", "--prompt", "测试", "--reference", "reference.png", "--size", "1280x768"],
        ["text", "--text", "测试", "--description", "海报", "--size", "1280x768"],
        ["batch", "--prompt", "一", "--prompt", "二", "--size", "1280x768"],
    )

    for argv in commands:
        with self.subTest(command=argv[0]):
            self.assertEqual(client._parser().parse_args(argv).size, "1280x768")
```

- [ ] **Step 6: Run targeted and full unit tests**

Run:

```powershell
python -m unittest tests.test_public_skill.PortableClientTests -v
python -m unittest discover -v
```

Expected: all `PortableClientTests` and the complete suite pass.

- [ ] **Step 7: Commit the parameter contract**

```powershell
git add -- skills/lumenverba-image/scripts/lumenverba_image.py tests/test_public_skill.py
git commit -m "feat: validate flexible gpt-image-2 parameters"
```

### Task 2: Warn once for explicit experimental resolutions

**Files:**
- Modify: `tests/test_public_skill.py:328-340`
- Modify: `skills/lumenverba-image/scripts/lumenverba_image.py:25-45`
- Modify: `skills/lumenverba-image/scripts/lumenverba_image.py:577-610`

**Interfaces:**
- Consumes: `_size_dimensions(size: str) -> tuple[int, int]` and `_select_size(value: str | None) -> str` from Task 1.
- Produces: `_is_experimental_size(value: str | None) -> bool`.
- Preserves: warnings go only to `stderr`; result receipt `errors`, status, exit code, request fields, and retry behavior are unchanged.

- [ ] **Step 1: Write failing tests for warning behavior and receipt isolation**

Add to `PortableClientTests`:

```python
def test_experimental_size_warns_once_without_changing_success_receipt(self):
    client = load_public_client()
    returned = [Path("C:/generated/experimental.png")]
    stderr = StringIO()

    with tempfile.TemporaryDirectory() as directory:
        result_file = Path(directory) / "result.json"
        with patch.object(client, "generate", return_value=returned):
            with redirect_stdout(StringIO()), redirect_stderr(stderr):
                exit_code = client.main([
                    "generate",
                    "--prompt",
                    "测试",
                    "--size",
                    "2048x2048",
                    "--result-file",
                    str(result_file),
                ])
        receipt = json.loads(result_file.read_text(encoding="utf-8"))

    self.assertEqual(exit_code, 0)
    self.assertEqual(stderr.getvalue().count("WARNING: 实验分辨率"), 1)
    self.assertEqual(receipt["status"], "success")
    self.assertEqual(receipt["errors"], [])

def test_auto_and_regular_sizes_do_not_warn(self):
    client = load_public_client()
    returned = [Path("C:/generated/regular.png")]

    for size in ("auto", "2048x1152"):
        stderr = StringIO()
        with self.subTest(size=size):
            with patch.object(client, "generate", return_value=returned):
                with redirect_stdout(StringIO()), redirect_stderr(stderr):
                    exit_code = client.main([
                        "generate",
                        "--prompt",
                        "测试",
                        "--size",
                        size,
                    ])
            self.assertEqual(exit_code, 0)
            self.assertNotIn("实验分辨率", stderr.getvalue())
```

- [ ] **Step 2: Run the warning tests and verify the red state**

Run:

```powershell
python -m unittest tests.test_public_skill.PortableClientTests.test_experimental_size_warns_once_without_changing_success_receipt tests.test_public_skill.PortableClientTests.test_auto_and_regular_sizes_do_not_warn -v
```

Expected: the experimental warning test fails because no warning exists yet; the normal-size test may already pass.

- [ ] **Step 3: Add a pure threshold helper and one CLI warning**

Add the threshold constant and helper near the size validation code:

```python
EXPERIMENTAL_OUTPUT_PIXELS = 2560 * 1440


def _is_experimental_size(value: str | None) -> bool:
    selected = _select_size(value)
    if selected == "auto":
        return False
    width, height = _size_dimensions(selected)
    return width * height > EXPERIMENTAL_OUTPUT_PIXELS
```

In `main()`, after validating `result_file` and before entering the request `try` block, add exactly one warning site:

```python
if _is_experimental_size(arguments.size):
    print(
        "WARNING: 实验分辨率的总像素超过 3,686,400，官方标记为 experimental；请求将继续执行。",
        file=sys.stderr,
    )
```

Do not append this warning to `errors` and do not call the helper inside `generate_batch`, `generate`, `edit`, or `build_generation_request`; one CLI invocation must print at most once.

- [ ] **Step 4: Run warning, receipt, and full tests**

Run:

```powershell
python -m unittest tests.test_public_skill.PortableClientTests.test_experimental_size_warns_once_without_changing_success_receipt tests.test_public_skill.PortableClientTests.test_auto_and_regular_sizes_do_not_warn tests.test_regressions.CommandModeReceiptTests -v
python -m unittest discover -v
```

Expected: all selected tests and the complete suite pass; the successful receipt keeps an empty `errors` list.

- [ ] **Step 5: Commit the warning behavior**

```powershell
git add -- skills/lumenverba-image/scripts/lumenverba_image.py tests/test_public_skill.py
git commit -m "feat: warn on experimental image sizes"
```

### Task 3: Document model boundaries and resolution presets

**Files:**
- Modify: `tests/test_public_skill.py:526-684`
- Modify: `skills/lumenverba-image/SKILL.md:12-64`
- Modify: `README.md:61-71`

**Interfaces:**
- Consumes: Task 1 parameter contract and Task 2 warning prefix.
- Produces: agent-facing mappings from semantic resolution presets to exact `--size` values.
- Preserves: `SKILL.md` stays on the current stable version marker; this task does not publish or tag a version.

- [ ] **Step 1: Write failing documentation contract tests**

Update `test_skill_documents_secure_first_use_and_all_modes` so the parameter expectations use `auto` and `medium`, then add:

```python
def test_documentation_declares_flexible_gpt_image_2_sizes(self):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    for content in (readme, skill):
        for expected in (
            "gpt-image-2",
            "auto",
            "medium",
            "3840",
            "16",
            "3:1",
            "655,360",
            "8,294,400",
            "3,686,400",
            "https://developers.openai.com/api/docs/guides/image-generation#size-and-quality-options",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, content)
        self.assertNotIn("`standard`", content)
        self.assertNotIn("`gpt-image-1`", content)
        self.assertNotIn("`gpt-image-1.5`", content)

    for preset in (
        "1024x1024",
        "1536x1024",
        "1024x1536",
        "2048x2048",
        "2048x1152",
        "3840x2160",
        "2160x3840",
    ):
        with self.subTest(preset=preset):
            self.assertIn(preset, skill)
```

- [ ] **Step 2: Run the documentation test and verify the red state**

Run:

```powershell
python -m unittest tests.test_public_skill.PackagedSkillTests.test_skill_documents_secure_first_use_and_all_modes tests.test_public_skill.PackagedSkillTests.test_documentation_declares_flexible_gpt_image_2_sizes -v
```

Expected: failures identify old models, `standard`, missing official constraints, and missing preset sizes.

- [ ] **Step 3: Replace the README parameter summary**

Replace the current one-line parameter paragraph with:

```markdown
默认使用模型 `gpt-image-2`、尺寸 `auto` 和质量 `medium`。这是唯一支持的模型；指定其他模型时客户端会在联网前拒绝。质量可选 `low`、`medium`、`high`、`auto`，质量控制渲染质量、速度和成本，不代表输出分辨率。

尺寸可使用 `auto` 或自定义 `WIDTHxHEIGHT`。自定义尺寸的最长边不得超过 `3840px`，两边必须是 `16px` 的倍数，长短边之比不得超过 `3:1`，总像素必须在 `655,360` 到 `8,294,400` 之间。显式尺寸总像素超过 `3,686,400` 时属于官方标记的实验范围，客户端会警告但仍允许执行。约束来源见 [OpenAI Image Generation 文档](https://developers.openai.com/api/docs/guides/image-generation#size-and-quality-options)。用户显式指定的合法参数始终优先。
```

- [ ] **Step 4: Update the skill model and warning rules**

In `SKILL.md`, make the model boundary explicit before parameter selection:

```markdown
- 仅支持 `gpt-image-2`。用户指定其他模型时，明确回复当前技能不支持该模型，不执行脚本、不发起 API 请求。
- 用户显式指定的合法 `size`、`quality` 优先。显式尺寸总像素超过 `3,686,400` 时，执行前说明该分辨率属于官方标记的实验范围，稳定性可能下降，但按用户要求继续执行。
```

Replace the parameter table and obsolete 16:9 note with:

```markdown
| 参数 | 默认 | 选择规则 |
| --- | --- | --- |
| `model` | `gpt-image-2` | 唯一支持的模型。 |
| `size` | `auto` | 可使用 `auto`、下方档位或符合官方约束的自定义 `WIDTHxHEIGHT`。 |
| `quality` | `medium` | `low` 用于草图和快速迭代；`medium` 用于常规生成；`high` 用于精细主视觉；`auto` 交给模型选择。质量不代表分辨率。 |

自定义尺寸的最长边不得超过 `3840px`，两边必须是 `16px` 的倍数，长短边之比不得超过 `3:1`，总像素必须在 `655,360` 到 `8,294,400` 之间。

尺寸与质量约束来源：[OpenAI Image Generation 文档](https://developers.openai.com/api/docs/guides/image-generation#size-and-quality-options)。

| 分辨率档位 | `--size` | 状态 |
| --- | --- | --- |
| 自动 | `auto` | 默认 |
| 标准方图 | `1024x1024` | 常规 |
| 标准横图 | `1536x1024` | 常规 |
| 标准竖图 | `1024x1536` | 常规 |
| 2K 方图 | `2048x2048` | 实验 |
| 2K 横图 | `2048x1152` | 常规 |
| 4K 横图 | `3840x2160` | 实验 |
| 4K 竖图 | `2160x3840` | 实验 |

档位只用于参数选择，执行脚本时必须传对应的原始 `--size` 值，不能把档位名称传给 CLI。其他比例使用符合约束的自定义 `WIDTHxHEIGHT`。显式尺寸总像素超过 `3,686,400` 时属于实验分辨率，必须在执行前提示风险；脚本也会向 `stderr` 输出非阻断警告。`auto` 的实际尺寸无法预判，不预先标记为实验分辨率。
```

- [ ] **Step 5: Run documentation and full tests**

Run:

```powershell
python -m unittest tests.test_public_skill.PackagedSkillTests -v
python -m unittest discover -v
```

Expected: all package contract tests and the complete suite pass.

- [ ] **Step 6: Commit the public documentation**

```powershell
git add -- README.md skills/lumenverba-image/SKILL.md tests/test_public_skill.py
git commit -m "docs: document flexible gpt-image-2 sizes"
```

### Task 4: Run the release gate and one low-cost live smoke test

**Files:**
- Verify: all changed files
- Runtime output only: Windows temporary directory outside the repository

**Interfaces:**
- Consumes: Tasks 1-3 and the configured `LUMENVERBA_API_KEY` environment variable.
- Produces: a clean, locally verified feature branch and one JSON receipt proving a non-legacy custom size reached the real endpoint.
- Does not produce: commits, tags, releases, repository images, or stored credentials.

- [ ] **Step 1: Run the complete offline gate**

Run each command from the repository root:

```powershell
python --version
python -m unittest discover -s tests -v
python -m unittest discover -v
python -m compileall -q skills tests
python skills/lumenverba-image/scripts/lumenverba_image.py --help
python skills/lumenverba-image/scripts/lumenverba_image.py generate --help
python skills/lumenverba-image/scripts/lumenverba_image.py edit --help
python skills/lumenverba-image/scripts/lumenverba_image.py text --help
python skills/lumenverba-image/scripts/lumenverba_image.py batch --help
git diff --check HEAD~3..HEAD
```

Expected: Python is `3.11` or newer; both discovery commands run the full suite; every command exits `0`; help shows only `gpt-image-2`, official quality values, and free-form `--size SIZE` rather than a fixed choice list.

- [ ] **Step 2: Check for stale public parameters and credential patterns**

Run:

```powershell
rg -n "gpt-image-1|gpt-image-1.5|standard" README.md skills/lumenverba-image/SKILL.md skills/lumenverba-image/scripts/lumenverba_image.py
rg -n "LUMENVERBA_API_KEY\s*=|Bearer\s+[A-Za-z0-9._-]{16,}" README.md CONTEXT.md docs skills tests
```

Expected: the stale parameter scan returns no matches. The credential scan returns no assigned key or literal Bearer credential; documentation may mention the environment variable name without a value.

- [ ] **Step 3: Perform one authorized low-cost custom-size smoke test**

Use `1280x768`, which is outside the old three-size allowlist but remains below the experimental threshold:

```powershell
$smokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) "lumenverba-flexible-size-smoke-20260817"
$smokeImages = Join-Path $smokeRoot "images"
$smokeReceipt = Join-Path $smokeRoot "result.json"
New-Item -ItemType Directory -Force -Path $smokeRoot | Out-Null
python skills/lumenverba-image/scripts/lumenverba_image.py generate --prompt 'A single matte blue ceramic cube on a neutral white background, no text.' --model gpt-image-2 --size 1280x768 --quality low --count 1 --output-dir $smokeImages --result-file $smokeReceipt
```

Expected: exactly one PNG path on `stdout`, exit code `0`, and no experimental warning. If the creation request encounters a network failure or its result channel is lost, do not retry the command because generation and billing state may be unknown.

- [ ] **Step 4: Validate the smoke receipt without exposing credentials**

Run:

```powershell
$smokeResult = Get-Content -Raw -Encoding utf8 $smokeReceipt | ConvertFrom-Json
$smokeResult.status
$smokeResult.exit_code
$smokeResult.paths
Get-Item -LiteralPath $smokeResult.paths | Select-Object FullName, Length
```

Expected: `status` is `success`, `exit_code` is `0`, `paths` contains one absolute path, and the file exists with nonzero length. Do not print environment variables, request headers, or the API key.

- [ ] **Step 5: Verify final repository state**

Run:

```powershell
git status --short --branch
git log --oneline --decorate -5
```

Expected: branch is `codex/gpt-image-2-flexible-sizes`, the worktree is clean, and the three implementation commits follow the design commit. Do not push, merge, tag, or create a release without separate authorization.
