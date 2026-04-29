---
name: generic-tdd
description: TDD 模式实现 — RED-GREEN-REFACTOR 循环，先写测试再写代码。与 implement 阶段集成，强制测试优先。
---

# TDD 模式实现

## 核心循环

```
RED    → 写一个会失败的测试
GREEN  → 写最小代码让测试通过
REFACTOR → 优化代码（测试保持绿色）
```

## 约束

- 必须先写测试再写实现（RED 确认后才能写代码）
- 每次只写让测试通过的最小代码，不提前优化
- 重构时不加新功能
- 测试不依赖实现细节（不过度 Mock）

## 语言特化

检测技术栈后，读取本目录下对应文件获取测试命令：
- Java/Gradle → 读取 lang-java.md
- Python → 读取 lang-python.md
- TypeScript/Node → 读取 lang-typescript.md
- Go → 读取 lang-go.md
- Rust → 读取 lang-rust.md

## 参考

- 常见错误和对比 → 读取 playbook-anti-patterns.md

## 状态上报

每个 RED-GREEN-REFACTOR 循环完成后：

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update implement IN_PROGRESS \
  --phase {N} --gate build=pass --gate test=pass
```

## 启用方式

`.claude/dev-config.yml` 中设置 `tdd: true`。
