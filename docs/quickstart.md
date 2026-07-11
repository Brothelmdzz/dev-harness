# Dev Harness 快速上手

## 1. 安装 (1 分钟)

在 Claude Code 中执行:

```bash
# 注册 marketplace
/plugin marketplace add https://github.com/brothelmdzz/dev-harness

# 安装插件
/plugin install dev-harness
```

验证安装成功:
```
/dev
```
看到技术栈检测和 Skill 解析输出即成功。

## 2. 第一个任务 (5 分钟)

```
/dev
```

选择路线 **C-lite**（最简模式，只有 implement + test + remember）。

输入任务信息:
- 任务名称: `fix-login-bug`
- 类型: bugfix
- 涉及模块: portal

观察 Pipeline 自动推进:
```
[>>] implement  IN_PROGRESS
[  ] test       PENDING
[  ] remember   PENDING
```

## 3. 配置项目 (3 分钟)

```bash
# 复制配置模板（按你的技术栈选择）
bash $DH_HOME/scripts/scaffold.sh --config springboot
# 或: nextjs / python / monorepo / minimal

# 编辑配置
# 文件位置: .claude/dev-config.yml
```

关键配置项:
- `gates.build`: 你的构建命令
- `gates.test`: 你的测试命令
- `default_profile`: 默认角色 (backend/frontend/product/qa)

## 4. 写第一个 L1 Skill (15 分钟)

```bash
# 生成骨架
bash $DH_HOME/scripts/scaffold.sh my-audit

# 编辑 .claude/skills/my-audit/SKILL.md
# 填写角色定义、执行流程、产出和约束
```

下次 `/dev` 时，audit 阶段会自动使用你的 Skill（L1 优先级）。

## 5. 查看 HUD

在另一个终端窗口:
```bash
# 基础版
python $DH_HOME/scripts/harness.py hud --watch

# Rich 增强版（需要 pip install rich）
python $DH_HOME/scripts/harness.py hud --watch --rich
```

## 6. 多角色模式

```bash
# 前端开发
/dev --profile frontend

# 产品需求
/dev --profile product

# QA 测试
/dev --profile qa
```

## 7. /goal 一句话启动（v4.5）

除了直接输入 `/dev`，也可以用 Claude Code 内置的 `/goal` 把 dev-harness 流水线整个带出来——把下面这句话粘进干净会话，改掉方括号里的任务描述即可：

```
/goal 用 dev-harness 流水线完成【<任务一句话>】。达成标准：最近一次
`python harness.py hud` 输出显示所有 stage = DONE 且所有 gate = pass
（build/test 绿、error_count = 0）；没有 hud 输出就不算达成。
请通过 dev-pipeline 技能推进；40 轮未达成则停下报告卡在哪个 stage/gate。
```

机制：条件文本里的"dev-pipeline 技能"字样会触发隐式 Skill 匹配，把 Claude 带进 `/dev` 编排器；此后每一轮只要流水线还没真正跑完，`/goal` 的裁判就会在 block reason 里持续提到"hud 显示未完成"，把 Claude 一轮轮推回去跑 `harness.py hud` 确认状态——即使第一轮没触发技能，这个循环也是自我纠偏的。dev-harness 自己也随插件分发了一个等价的 prompt Stop hook（见 `hooks/hooks.json`），所以就算不手动 `/goal`，同样的完成判定逻辑在 `/dev` 里也是默认生效的。

## 常见问题

**Q: /dev 没反应?**
A: 确认 `bash $DH_HOME/scripts/detect-stack.sh` 输出了正确的技术栈。

**Q: Pipeline 中断了怎么续接?**
A: 再次输入 `/dev`，会自动检测 harness-state.json 并续接。

**Q: 怎么查看 Skill 映射?**
A: `python $DH_HOME/scripts/skill-index.py`

**Q: 怎么强制使用某个 Skill?**
A: 在 `.claude/dev-config.yml` 的 `skill_overrides` 中指定。
