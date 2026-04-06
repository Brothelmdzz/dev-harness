#!/bin/bash
# 自动发现 dev-harness 安装路径
# 优先级: marketplace 安装 > 本地开发 > plugins 目录 > 递归搜索

# 方式 1: 已知路径模式（版本号或 commit SHA 均可匹配）
for dir in \
  "$HOME/.claude/plugins/cache/dev-harness-marketplace/dev-harness"/*/ \
  "$HOME/.claude/plugins/cache/dev-harness-local/dev-harness"/*/ \
  "$HOME/.claude/plugins/dev-harness/"*/ \
  ; do
    if [ -f "${dir}scripts/harness.py" ]; then
        echo "${dir%/}"
        exit 0
    fi
done

# 方式 2: 递归搜索整个 plugins/cache（兜底，适配未知目录结构）
if [ -d "$HOME/.claude/plugins/cache" ]; then
    found=$(find "$HOME/.claude/plugins/cache" -name "harness.py" -path "*/dev-harness/*/scripts/*" 2>/dev/null | head -1)
    if [ -n "$found" ]; then
        # harness.py 在 scripts/ 下，DH_HOME 是 scripts 的父目录
        echo "$(cd "$(dirname "$found")/.." && pwd)"
        exit 0
    fi
fi

echo "NOT_FOUND"
exit 1
