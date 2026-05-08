---
name: generic-review
description: 通用代码审查 — Claude 内部三路并行（code + security + arch）+ 可选第四路跨厂商对抗审查（codex cli），汇总对比。
---

# 通用代码审查

## 约束

- **Layer 1 必跑**：Claude 三路并行（code + security + arch），不得串行
- **Layer 2 可选**：检测到 codex cli 且配置允许时启用跨厂商审查
- 每路独立输出报告，汇总时保留多方对比
- CRITICAL 问题必须自动修复后重编译验证
- 报告文件必须非空（>500 字节 + 至少 2 个 ## 标题），否则 stop-hook 会打回

## Layer 1: Claude 内部三路并行（必跑）

用 `Agent(run_in_background=true)` 同时启动：

| Agent | 模型 | 侧重 | 产出 |
|-------|------|------|------|
| code-reviewer | sonnet | 代码质量、bug、边界条件、可维护性 | `.claude/reports/review-code.md` |
| security-reviewer | sonnet | SQL 注入、XSS、敏感信息泄露、权限缺失 | `.claude/reports/review-security.md` |
| architect | opus | 架构合理性、模块边界、接口设计 | `.claude/reports/review-arch.md` |

模型异构（sonnet × 2 + opus × 1）= 消除单模型偏见 + 成本反而比全 opus 低。

每个问题标注 CRITICAL / WARN / INFO 级别。

## Layer 2: 跨厂商对抗审查（可选）

### 启用条件

满足**所有**：

1. `dev-config.yml` 中 `review.cross_vendor.enabled` 为 `auto`（默认）或 `true`
2. `bash ${CLAUDE_PLUGIN_ROOT}/scripts/detect-codex.sh` 退出码 0（codex cli 就绪 + 配置完整）

### 检测命令

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-codex.sh"
# 退出码 0 = 就绪，可启用 Layer 2
# 退出码 1 = 未装或未配置
# 退出码 2 = enabled=true 但未就绪（必须报错）
```

### 调用

⚠️ 不要用 `codex review` 直接 redirect — 它的输出含 banner 和 deprecated 警告，需要后处理。
✅ 用 `codex exec --output-last-message`，直接把审查结论写入文件（实测干净 markdown）：

```bash
# 在项目根执行
BASE_BRANCH=$(git rev-parse --abbrev-ref origin/HEAD 2>/dev/null | sed 's|origin/||' || echo master)
mkdir -p .claude/reports

codex exec \
  --skip-git-repo-check \
  --output-last-message .claude/reports/review-cross-vendor.md \
  -s read-only \
  "请对 git diff ${BASE_BRANCH}...HEAD 做代码审查。

## 任务
作为独立的非 Claude 模型，审查这次变更，找出：
- CRITICAL：必须修复的 bug、安全漏洞、严重逻辑错误
- WARN：建议修复
- INFO：观察/建议

## 输出格式（严格 markdown）

## CRITICAL
| 文件:行号 | 问题 |
|----------|------|

## WARN
| 文件:行号 | 问题 |
|----------|------|

## INFO
- ...

## 跨厂商视角总结
你作为非 Claude 模型，从你的训练数据 / 推理路径角度，这次变更最值得人类审查者注意的 1-2 个点是什么？" \
  || echo "cross-vendor review failed, fallback to Layer 1 only" \
     > .claude/reports/review-cross-vendor.md
```

**关键 flag 说明**：
- `--skip-git-repo-check`: 不要求项目在 codex trust list（避免每个新项目都要先 trust）
- `--output-last-message <FILE>`: 仅把最终回复写文件（不含 codex 自身 banner、deprecated 警告、tool call 日志）
- `-s read-only`: 沙箱限制，审查不修改文件
- `--config model="..."`（可选）: 临时覆盖 `~/.codex/config.toml` 中的 model

产出：`.claude/reports/review-cross-vendor.md`，使用 codex 配置的非 Claude 模型（如 GPT-5 / GLM / o3 等，由用户 `~/.codex/config.toml` 中 `model_provider` + `model` 决定）。

### enabled 取值

| 值 | 检测到 codex | 行为 |
|---|-------------|------|
| `auto`（默认）| ✅ 装了 | 启用 Layer 2 |
| `auto` | ❌ 没装 | 静默跳过 |
| `true` | ❌ 没装 | 报错，要求安装 codex 或改为 false/auto |
| `false` | -- | 永远跳过 |

## 汇总规则

按以下顺序处理：

1. **去重**：按 `file:line + 问题摘要哈希` 去重
2. **置信度判定**：
   - 任意 ≥ 2 路命中同一问题 → **高置信**，必须修
   - 仅 1 路 Claude reviewer 命中 → 中置信，标注待人决
   - 仅 cross-vendor 单独命中 → **单独 section "异构视角发现"**（不强制修，但保留报告）
3. **CRITICAL 处理**：任一路标 CRITICAL 且置信度高 → 自动修复 → 重编译确认
4. **结论**：无 CRITICAL 高置信问题 → 通过

## 参考

- 报告格式 → 读取 [`report-template.md`](report-template.md)
- Agent 启动失败 / 降级 → 读取 [`playbook-fallback.md`](playbook-fallback.md)
- codex 检测脚本 → [`scripts/detect-codex.sh`](../../scripts/detect-codex.sh)

## 产出

汇总到 `.claude/reports/final-review.md`（格式见 report-template.md）。

汇总报告必须包含：
- 三路 Claude reviewer 对比表
- 如果启用了 Layer 2：单独的"跨厂商视角"section
- 总结性 CRITICAL/WARN/INFO 计数
- 通过/不通过判定
