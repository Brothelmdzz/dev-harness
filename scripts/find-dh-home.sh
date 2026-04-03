#!/bin/bash
# 自动发现 dev-harness 安装路径
for dir in \
  "$HOME/.claude/plugins/cache/dev-harness-marketplace/dev-harness"/*/ \
  "$HOME/.claude/plugins/cache/dev-harness-local/dev-harness"/*/ \
  "$HOME/.claude/plugins/dev-harness/" \
  ; do
    if [ -f "${dir}scripts/harness.py" ]; then
        echo "${dir%/}"
        exit 0
    fi
done
echo "NOT_FOUND"
exit 1
