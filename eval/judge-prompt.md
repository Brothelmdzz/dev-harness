# LLM-as-Judge 评分 Rubric

> 用于 L2 Task Set B（真实任务，无标准答案）的质量评判
> Judge 模型: claude-opus-4-6

---

## 评判模式

**Pairwise Comparison + 绝对评分**

同时进行两种评判：
1. 两份实现哪个更好（pairwise）
2. 每份实现的绝对质量分（1-10）

---

## 输入格式

```
<requirement>
{需求描述，自然语言}
</requirement>

<implementation_a>
{对照组（裸模型）产出的代码 diff}
</implementation_a>

<implementation_b>
{实验组（Harness 增强）产出的代码 diff}
</implementation_b>

<reference>
{用户最终实现的代码 diff（参考，非标准答案）}
</reference>

<context>
技术栈: {stack}
文件数: A={n} / B={n} / Ref={n}
测试结果: A={pass/fail} / B={pass/fail}
</context>
```

---

## 评分维度

### 1. 需求覆盖 (completeness) — 1-10

需求文档中描述的每个功能点是否都实现了。

| 分数 | 标准 |
|------|------|
| 9-10 | 所有功能点完整实现，含边界和异常处理 |
| 7-8 | 核心功能完整，缺少部分边界处理 |
| 5-6 | 主流程实现，缺少 1-2 个功能点 |
| 3-4 | 只实现部分功能，核心流程有缺失 |
| 1-2 | 几乎未实现需求 |

### 2. 代码质量 (code_quality) — 1-10

可读性、错误处理、边界条件、命名规范。

| 分数 | 标准 |
|------|------|
| 9-10 | 生产级质量，错误处理完善，命名清晰 |
| 7-8 | 良好质量，少量可改进点 |
| 5-6 | 能工作但有明显质量问题 |
| 3-4 | 质量差，多处硬编码或遗漏错误处理 |
| 1-2 | 代码杂乱，无法维护 |

### 3. 架构合理性 (architecture) — 1-10

职责划分、耦合度、可扩展性、设计模式运用。

| 分数 | 标准 |
|------|------|
| 9-10 | 职责清晰，低耦合，符合项目现有架构风格 |
| 7-8 | 基本合理，少量职责模糊 |
| 5-6 | 能工作但架构有问题（如 God class） |
| 3-4 | 严重架构问题，与项目风格不一致 |
| 1-2 | 无架构可言 |

### 4. 测试覆盖 (test_coverage) — 1-10

是否有测试、测试质量、覆盖核心路径和边界。

| 分数 | 标准 |
|------|------|
| 9-10 | 核心+边界+异常路径均有测试，测试名称清晰 |
| 7-8 | 核心路径有测试，缺少部分边界 |
| 5-6 | 有测试但覆盖不足 |
| 3-4 | 极少测试或测试质量差 |
| 1-2 | 无测试 |

### 5. 健壮性 (robustness) — 1-10

异常处理、输入验证、并发安全、资源管理。

| 分数 | 标准 |
|------|------|
| 9-10 | 完善的异常处理和输入验证，资源正确释放 |
| 7-8 | 主要异常有处理，少量遗漏 |
| 5-6 | 部分异常处理，有潜在风险 |
| 3-4 | 缺少关键异常处理 |
| 1-2 | 无异常处理，极易崩溃 |

---

## 输出格式

```json
{
  "pairwise": {
    "winner": "A" | "B" | "tie",
    "confidence": "high" | "medium" | "low",
    "reasoning": "B 在需求覆盖和测试方面优于 A，因为..."
  },
  "scores_a": {
    "completeness": 6,
    "code_quality": 7,
    "architecture": 5,
    "test_coverage": 4,
    "robustness": 5,
    "total": 27
  },
  "scores_b": {
    "completeness": 8,
    "code_quality": 8,
    "architecture": 7,
    "test_coverage": 7,
    "robustness": 7,
    "total": 37
  },
  "vs_reference": {
    "a_similarity": "low" | "medium" | "high",
    "b_similarity": "low" | "medium" | "high",
    "note": "B 的架构选择更接近参考实现..."
  }
}
```

---

## 评判原则

1. **只看 diff，不看意图** — 评判实际代码，不评判"它想做什么"
2. **Build/test 失败直接扣分** — 构建失败的实现 completeness 不超过 4 分
3. **参考实现是参考不是标准** — 用户实现不一定是最优的，允许比参考更好
4. **不因代码量多而加分** — 简洁正确优于冗长正确
5. **pairwise 判断基于总体印象** — 不是分数加和，是整体哪个你更愿意 merge
