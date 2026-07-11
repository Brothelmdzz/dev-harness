---
name: generic-test
description: Test-suite execution with automatic framework detection across pytest/jest/gradle/cargo. Use when the pipeline enters the test stage or a suite must be run. Do not use for test-first work (generic-tdd).
model_context: claude-opus-4.5+
---

# 通用测试

## 约束

- 必须先用 `detect-stack.sh` 检测技术栈再选择测试策略
- 测试全部通过才能标记 DONE
- 新增代码必须有对应测试覆盖
- P0 问题自动修复最多 3 轮

## 语言特化

检测技术栈后，读取本目录下对应文件获取测试命令和策略：
- Java/Gradle → 读取 lang-java.md
- Python → 读取 lang-python.md
- TypeScript/Node → 读取 lang-typescript.md
- Go → 读取 lang-go.md
- Rust → 读取 lang-rust.md

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-stack.sh"
```

## 参考

遇到具体情况时读取本目录下对应文件：
- 写报告时 → 读取 report-template.md
- P0 问题自动修复 → 读取 playbook-p0-fix.md
- 测试无法运行（缺环境/服务）→ 读取 playbook-fallback.md

## 产出

报告输出到 `.claude/reports/test-{module}-{date}.md`（格式见 report-template.md）。
