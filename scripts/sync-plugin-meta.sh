#!/bin/bash
# ==================== 插件元数据同步 ====================
# 从 .claude-plugin/plugin.json 读取版本号，同步到:
#   - .cursor-plugin/plugin.json
#   - .cursor-plugin/marketplace.json
#   - .claude-plugin/marketplace.json
#   - package.json
# 用法: bash scripts/sync-plugin-meta.sh [version]
#   无参数: 从 .claude-plugin/plugin.json 读取当前版本
#   有参数: 使用指定版本号覆盖所有文件

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

CLAUDE_PLUGIN="$PROJECT_ROOT/.claude-plugin/plugin.json"
CURSOR_PLUGIN="$PROJECT_ROOT/.cursor-plugin/plugin.json"
CLAUDE_MARKET="$PROJECT_ROOT/.claude-plugin/marketplace.json"
CURSOR_MARKET="$PROJECT_ROOT/.cursor-plugin/marketplace.json"
PACKAGE_JSON="$PROJECT_ROOT/package.json"

# ==================== 解析版本号 ====================
if [ -n "${1:-}" ]; then
    VERSION="$1"
    echo "[sync] 使用指定版本号: $VERSION"
else
    # 从 .claude-plugin/plugin.json 提取 version 字段
    if ! command -v python >/dev/null 2>&1; then
        echo "ERROR: python not found, cannot parse JSON" >&2
        exit 1
    fi
    VERSION=$(python -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$CLAUDE_PLUGIN")
    echo "[sync] 从 $CLAUDE_PLUGIN 读取版本号: $VERSION"
fi

# ==================== 版本号格式校验 ====================
if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$'; then
    echo "ERROR: 版本号格式无效: $VERSION (期望 semver 格式如 3.3.0)" >&2
    exit 1
fi

# ==================== 同步函数 ====================
sync_version() {
    local file="$1"
    local label="$2"

    if [ ! -f "$file" ]; then
        echo "  [跳过] $label — 文件不存在"
        return
    fi

    # 使用 python 精确替换 JSON 中的 version 字段
    python -c "
import json, sys

path = sys.argv[1]
version = sys.argv[2]

with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 顶层 version
if 'version' in data:
    data['version'] = version

# marketplace.json 中 plugins[].version
if 'plugins' in data and isinstance(data['plugins'], list):
    for p in data['plugins']:
        if 'version' in p:
            p['version'] = version

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write('\n')
" "$file" "$VERSION"

    echo "  [OK] $label → $VERSION"
}

# ==================== 执行同步 ====================
echo "[sync] 同步版本号 $VERSION 到所有元数据文件..."

sync_version "$CLAUDE_PLUGIN"  ".claude-plugin/plugin.json"
sync_version "$CURSOR_PLUGIN"  ".cursor-plugin/plugin.json"
sync_version "$CLAUDE_MARKET"  ".claude-plugin/marketplace.json"
sync_version "$CURSOR_MARKET"  ".cursor-plugin/marketplace.json"
sync_version "$PACKAGE_JSON"   "package.json"

echo "[sync] 完成。所有文件版本号已同步为 $VERSION"
