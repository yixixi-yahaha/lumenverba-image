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
