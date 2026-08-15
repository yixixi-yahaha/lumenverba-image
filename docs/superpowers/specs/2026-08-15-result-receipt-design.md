# Result Receipt Design

## Goal

Deliver images even when Codex loses a completed command's stdout, stderr, and exit code, without scanning the output directory or repeating the generation request.

## Root Cause

The image client saves every returned PNG before printing its absolute path. In the reported failure, the command completed and the PNG files existed, but the command execution channel returned no stdout, stderr, or exit code to the conversation. The `v1.2.2` skill correctly refused to infer results from directory contents, but it had no second trusted result channel.

## Receipt Contract

Every skill invocation passes one unique, absolute `--result-file` path to the existing command. The client writes a UTF-8 JSON receipt after the command outcome is known:

```json
{
  "version": 1,
  "status": "success",
  "exit_code": 0,
  "paths": ["C:\\absolute\\image.png"],
  "errors": []
}
```

`status` is `success`, `partial`, or `error`. `paths` contains only PNG paths returned by the current process. `errors` contains the same safe diagnostics that the client writes to stderr. The receipt is written to a temporary sibling and atomically replaced so a reader never accepts a partially written JSON document.

The existing stdout and stderr contract remains unchanged. `--result-file` is optional for direct CLI users, but the packaged skill always supplies it.

## Delivery Behavior

1. When the command execution channel returns complete stdout, stderr, and an exit code, deliver results exactly as before.
2. When that channel returns no usable outcome, read only the preselected receipt path without network access.
3. Validate the receipt schema and the specific PNG paths it names, then deliver those images and any recorded safe errors.
4. If the receipt is absent, invalid, or incomplete, report an unknown execution state.

The skill never scans the output directory, infers results from file timestamps, or repeats a generation request because command output was lost.

## Error Handling

- A generation or batch failure still writes an `error` receipt when the client reaches its normal exception handler.
- A partial multi-image or batch result writes all successful paths and numbered failure messages with `status: partial`.
- Receipt write failure is reported on stderr and makes the command nonzero, but never deletes generated PNG files.
- Raw API keys, authorization headers, network exception details, and response bodies are never written to the receipt.

## Verification

Tests must prove:

1. Every command mode accepts `--result-file`.
2. A successful command preserves stdout and atomically writes the current invocation's paths.
3. A failed and a partial command write safe `error` or `partial` receipts.
4. The skill requires a unique absolute result path and reads that exact receipt when command output is missing.
5. The skill still forbids directory scans and command-level retries.
6. The complete offline suite and `git diff --check` pass.

## Non-Goals

- Repairing Codex's command execution transport
- Scanning or reconciling existing output directories
- A persistent job database or background service
- Retrying generation after an unknown execution state
- Changing prompts, API request bodies, image validation, or visual inspection
