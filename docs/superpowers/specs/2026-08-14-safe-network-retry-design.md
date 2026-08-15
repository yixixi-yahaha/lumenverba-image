# Safe Network Retry Design

## Goal

Allow one automatic retry when a Lumenverba request fails before it could have been accepted by the service. If the retry ultimately yields images, deliver every successful image and tell the user the safe category of the first failure.

## Retry Boundary

The client retries at most once per HTTP operation and reuses the exact same method, URL, headers, and body.

Retryable first-failure categories are:

- `DNS 解析失败`
- `TLS 连接失败`
- `连接被拒绝`
- `代理连接失败`

The client must not automatically retry:

- `网络连接超时`
- a connection closed after request transmission may have begun
- generic `网络连接失败`
- HTTP responses, API task failures, parsing failures, or missing images
- any failure whose generation status is unknown

No retry may change the prompt, model, size, quality, count, references, output directory, or generation mode.

## Client Behavior

`_send()` classifies the first `URLError`. For a retryable category it immediately makes one identical second call. It never performs a third call.

When the second call returns an HTTP response, the client writes one stable, safe notice to stderr:

```text
RETRY_NOTICE: 首次调用失败：TLS 连接失败；已自动重试 1 次。
```

Raw exception text, host details, proxy credentials, tokens, and API keys must never appear in this notice.

If the second call also fails, the command exits nonzero and reports safe categories for both attempts. If the first failure is not retryable, existing single-attempt failure behavior remains, without telling the user to retry an unknown-status request.

## Skill Delivery Behavior

The skill treats `RETRY_NOTICE:` as metadata, not as a failed batch item.

- When stdout contains one or more successful PNG paths, show every image first and then append the retry notice in plain Chinese, for example: `首次失败原因：TLS 连接失败；自动重试一次后成功。`
- When no image was produced, report the command failure normally; do not claim that generation succeeded.
- Preserve partial batch successes and their existing numbered failure diagnostics.
- Do not visually inspect images, rewrite prompts, or issue another command-level retry.

## Documentation

Update `SKILL.md` and README to replace the blanket automatic-retry prohibition with the exact one-retry boundary and the successful-delivery notice requirement.

## Verification

Tests must prove:

1. A retryable first error followed by success calls `urlopen` exactly twice and emits a safe retry notice.
2. A non-retryable timeout calls `urlopen` exactly once.
3. Two retryable failures call `urlopen` exactly twice, exit as a failure, and expose only safe categories.
4. The packaged skill requires retry notices to be included when images are delivered.
5. README documents the same retry boundary.
6. The complete offline test suite and `git diff --check` pass.

## Non-Goals

- Configurable retry counts or backoff
- Retrying HTTP status codes or asynchronous task failures
- Retrying an entire multi-image or multi-prompt command
- Persisting retry state across processes
- Prompt rewriting, image inspection, or MCP changes
