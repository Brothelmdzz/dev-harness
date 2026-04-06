#!/bin/bash
# Dev Harness — Skill 脚手架 + 项目配置生成
#
# 用法:
#   bash scaffold.sh <skill-name>                创建 L1 Skill 骨架
#   bash scaffold.sh --config <template-name>    复制项目配置模板
#   bash scaffold.sh --list                      列出可用模板
#
# 示例:
#   bash scaffold.sh my-audit                    → .claude/skills/my-audit/SKILL.md
#   bash scaffold.sh --config springboot         → .claude/dev-config.yml

set -euo pipefail

DH_HOME="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATES_DIR="$DH_HOME/templates"

# ==================== Skill 脚手架 ====================

create_skill() {
    local name="$1"
    local target=".claude/skills/$name"

    if [ -d "$target" ]; then
        echo "[WARN] $target 已存在，跳过"
        return 1
    fi

    mkdir -p "$target"
    cat > "$target/SKILL.md" << 'EOF'
---
name: SKILL_NAME_PLACEHOLDER
description: 一句话描述。Use when: 用户说"xxx"。
---

# SKILL_NAME_PLACEHOLDER

## 角色
你是 [角色名]。你的职责是 [一句话]，不做 [边界]。

## 执行流程

### 第一步: [动作名]
[具体步骤、命令、检查项]

### 第二步: [动作名]
[具体步骤]

### 第三步: [动作名]
[具体步骤]

## 产出
保存到 `.claude/reports/SKILL_NAME_PLACEHOLDER-{date}.md`

## 约束
- [不做什么]
- [什么时候停下来找人]
- [最多重试几次]
EOF

    # 替换占位符
    if command -v sed >/dev/null 2>&1; then
        sed -i "s/SKILL_NAME_PLACEHOLDER/$name/g" "$target/SKILL.md"
    fi

    echo "[OK] 已创建: $target/SKILL.md"
    echo ""
    echo "下一步:"
    echo "  1. 编辑 $target/SKILL.md 填写具体内容"
    echo "  2. 下次 /dev 时该 Skill 会自动作为 L1 优先级被识别"
    echo ""
    echo "编写规范:"
    echo "  - 一个 Skill 一个文件，不超过 200 行"
    echo "  - 必须包含: 角色定义 + 执行流程 + 产出 + 约束"
    echo "  - 脚本引用用 \$DH_HOME/scripts/xxx"
}

# ==================== 配置模板 ====================

copy_config() {
    local template="$1"
    local source="$TEMPLATES_DIR/dev-config-${template}.yml"
    local target=".claude/dev-config.yml"

    if [ ! -f "$source" ]; then
        echo "[ERROR] 模板不存在: $source"
        echo "可用模板:"
        list_templates
        return 1
    fi

    if [ -f "$target" ]; then
        echo "[WARN] $target 已存在"
        echo "是否覆盖? 备份为 ${target}.bak"
        cp "$target" "${target}.bak"
    fi

    mkdir -p "$(dirname "$target")"
    cp "$source" "$target"
    echo "[OK] 已创建: $target (模板: $template)"
    echo "请编辑其中的项目名、门禁命令等字段"
}

list_templates() {
    echo "可用配置模板:"
    for f in "$TEMPLATES_DIR"/dev-config-*.yml; do
        if [ -f "$f" ]; then
            local name=$(basename "$f" | sed 's/dev-config-//;s/.yml//')
            local desc=$(head -2 "$f" | tail -1 | sed 's/^# *//')
            echo "  $name  — $desc"
        fi
    done
}

# ==================== 入口 ====================

case "${1:-}" in
    --config)
        copy_config "${2:-}"
        ;;
    --list)
        list_templates
        ;;
    --help|-h|"")
        echo "Dev Harness 脚手架"
        echo ""
        echo "用法:"
        echo "  bash scaffold.sh <skill-name>            创建 L1 Skill 骨架"
        echo "  bash scaffold.sh --config <template>     复制项目配置模板"
        echo "  bash scaffold.sh --list                  列出可用模板"
        ;;
    *)
        create_skill "$1"
        ;;
esac
