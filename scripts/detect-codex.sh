#!/usr/bin/env bash
# 检测 codex cli 是否就绪可用于跨厂商对抗审查（Layer 2）
#
# 退出码:
#   0 - 就绪（cli 可用 + 配置完整 + 模型已设置）
#   1 - 未就绪（缺少任一条件）
#
# 使用：
#   bash detect-codex.sh           # 静默检测
#   bash detect-codex.sh --verbose # 输出详细诊断
#
# 集成到 generic-review/SKILL.md Layer 2，受 dev-config.yml 的
# review.cross_vendor.enabled 控制（auto/true/false）。

set -u

VERBOSE=0
if [ "${1:-}" = "--verbose" ] || [ "${1:-}" = "-v" ]; then
  VERBOSE=1
fi

log() {
  if [ "$VERBOSE" -eq 1 ]; then
    echo "[detect-codex] $*" >&2
  fi
}

# ==================== 1. cli 可执行 ====================
if ! command -v codex >/dev/null 2>&1; then
  log "codex cli 未安装"
  exit 1
fi
log "codex cli: $(command -v codex)"

# 版本检测（顺便确认 cli 不是损坏的）
if ! codex --version >/dev/null 2>&1; then
  log "codex cli 损坏（--version 失败）"
  exit 1
fi
log "codex 版本: $(codex --version 2>&1 | head -1)"

# ==================== 2. 配置文件存在 ====================
CONFIG_PATH="${HOME}/.codex/config.toml"
# Windows 兼容：~ 在 git bash 下展开 ok，但 cmd 下用 %USERPROFILE%
if [ ! -f "$CONFIG_PATH" ] && [ -n "${USERPROFILE:-}" ]; then
  CONFIG_PATH="${USERPROFILE}/.codex/config.toml"
fi

if [ ! -f "$CONFIG_PATH" ]; then
  log "配置文件不存在: $CONFIG_PATH"
  exit 1
fi
log "配置文件: $CONFIG_PATH"

# ==================== 3. 配置中有 model + provider ====================
if ! grep -qE '^[[:space:]]*model[[:space:]]*=' "$CONFIG_PATH"; then
  log "配置缺少 model 字段"
  exit 1
fi

if ! grep -qE '^[[:space:]]*model_provider[[:space:]]*=' "$CONFIG_PATH"; then
  log "配置缺少 model_provider 字段"
  exit 1
fi

MODEL=$(grep -E '^[[:space:]]*model[[:space:]]*=' "$CONFIG_PATH" | head -1 | sed 's/.*=[[:space:]]*"\(.*\)".*/\1/')
PROVIDER=$(grep -E '^[[:space:]]*model_provider[[:space:]]*=' "$CONFIG_PATH" | head -1 | sed 's/.*=[[:space:]]*"\(.*\)".*/\1/')
log "model: $MODEL"
log "provider: $PROVIDER"

# ==================== 4. 在 git 仓库里（codex review 必需）====================
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  log "当前不在 git 仓库，codex review 无法工作"
  exit 1
fi
log "git 仓库: $(git rev-parse --show-toplevel)"

# 全部检查通过
log "✓ codex cli 就绪，可启用跨厂商对抗审查"
if [ "$VERBOSE" -eq 1 ]; then
  echo "ready" >&2
fi
exit 0
