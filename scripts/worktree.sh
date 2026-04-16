#!/bin/bash
# Dev Harness — implement 阶段 Git Worktree 隔离
#
# 用法:
#   bash worktree.sh create [branch-name]   创建隔离 worktree，输出 JSON
#   bash worktree.sh merge                  合并 worktree 回当前分支
#   bash worktree.sh cleanup                清理 worktree（失败回滚时用）
#   bash worktree.sh status                 检查 worktree 状态
#
# 设计原则:
#   - 非 git 仓库 → 降级为直接操作（输出 {"fallback": true}）
#   - 创建失败 → 降级为直接操作（不阻断 Pipeline）
#   - cleanup 始终安全（幂等操作）

set -euo pipefail

ACTION="${1:-status}"
BRANCH="${2:-dh-implement-$(date +%Y%m%d-%H%M%S)}"
STATE_FILE=".claude/harness-state.json"

is_git_repo() {
    git rev-parse --is-inside-work-tree >/dev/null 2>&1
}

get_worktree_info() {
    if [ -f "$STATE_FILE" ]; then
        python -c "
import json, sys
try:
    s = json.load(open(sys.argv[1], encoding='utf-8'))
    wt = s.get('worktree', {})
    print(wt.get('path', ''))
    print(wt.get('branch', ''))
except Exception:
    print('')
    print('')
" "$STATE_FILE" 2>/dev/null
    fi
}

save_worktree_info() {
    local wt_path="$1"
    local wt_branch="$2"
    if [ -f "$STATE_FILE" ]; then
        python -c "
import json, sys
try:
    sf, wp, wb = sys.argv[1], sys.argv[2], sys.argv[3]
    s = json.load(open(sf, encoding='utf-8'))
    s['worktree'] = {'path': wp, 'branch': wb}
    json.dump(s, open(sf, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
except Exception as e:
    print(f'WARN: {e}')
" "$STATE_FILE" "$wt_path" "$wt_branch" 2>/dev/null
    fi
}

clear_worktree_info() {
    if [ -f "$STATE_FILE" ]; then
        python -c "
import json, sys
try:
    sf = sys.argv[1]
    s = json.load(open(sf, encoding='utf-8'))
    s.pop('worktree', None)
    json.dump(s, open(sf, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
except Exception:
    pass
" "$STATE_FILE" 2>/dev/null
    fi
}

cmd_create() {
    if ! is_git_repo; then
        echo '{"fallback": true, "reason": "not a git repository"}'
        return 0
    fi
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
        git stash push -m "dh-worktree-auto-stash" >/dev/null 2>&1 || true
    fi
    local wt_dir=".claude/worktrees/$BRANCH"
    mkdir -p "$(dirname "$wt_dir")"
    if git worktree add "$wt_dir" -b "$BRANCH" >/dev/null 2>&1; then
        save_worktree_info "$wt_dir" "$BRANCH"
        echo "{\"created\": true, \"path\": \"$wt_dir\", \"branch\": \"$BRANCH\"}"
    else
        echo '{"fallback": true, "reason": "git worktree add failed"}'
    fi
}

cmd_merge() {
    if ! is_git_repo; then
        echo '{"fallback": true, "reason": "not a git repository"}'
        return 0
    fi
    local info
    info=$(get_worktree_info)
    local wt_path=$(echo "$info" | head -1)
    local wt_branch=$(echo "$info" | tail -1)
    if [ -z "$wt_path" ] || [ -z "$wt_branch" ]; then
        echo '{"skipped": true, "reason": "no worktree info in state"}'
        return 0
    fi
    if [ "$(git rev-parse --abbrev-ref HEAD)" = "$wt_branch" ]; then
        echo '{"error": "currently on worktree branch, cannot merge into self"}'
        return 1
    fi
    if git merge --no-ff "$wt_branch" -m "merge: implement via dev-harness [${wt_branch}]" >/dev/null 2>&1; then
        git worktree remove "$wt_path" --force >/dev/null 2>&1 || true
        git branch -D "$wt_branch" >/dev/null 2>&1 || true
        clear_worktree_info
        echo "{\"merged\": true, \"branch\": \"$wt_branch\"}"
    else
        echo "{\"error\": \"merge conflict\", \"branch\": \"$wt_branch\"}"
        return 1
    fi
}

cmd_cleanup() {
    if ! is_git_repo; then
        echo '{"fallback": true}'
        return 0
    fi
    local info
    info=$(get_worktree_info)
    local wt_path=$(echo "$info" | head -1)
    local wt_branch=$(echo "$info" | tail -1)
    [ -n "$wt_path" ] && git worktree remove "$wt_path" --force >/dev/null 2>&1 || true
    [ -n "$wt_branch" ] && git branch -D "$wt_branch" >/dev/null 2>&1 || true
    git stash list 2>/dev/null | grep -q "dh-worktree-auto-stash" && \
        git stash pop >/dev/null 2>&1 || true
    clear_worktree_info
    echo '{"cleaned": true}'
}

cmd_status() {
    if ! is_git_repo; then
        echo '{"git": false}'
        return 0
    fi
    local info
    info=$(get_worktree_info)
    local wt_path=$(echo "$info" | head -1)
    local wt_branch=$(echo "$info" | tail -1)
    if [ -n "$wt_path" ] && [ -d "$wt_path" ]; then
        echo "{\"active\": true, \"path\": \"$wt_path\", \"branch\": \"$wt_branch\"}"
    else
        echo '{"active": false}'
    fi
}

case "$ACTION" in
    create)  cmd_create ;;
    merge)   cmd_merge ;;
    cleanup) cmd_cleanup ;;
    status)  cmd_status ;;
    *)
        echo "用法: bash worktree.sh {create|merge|cleanup|status} [branch-name]"
        exit 1
        ;;
esac
