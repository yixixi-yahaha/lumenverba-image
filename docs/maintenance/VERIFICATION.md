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
