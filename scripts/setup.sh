#!/bin/bash
# Dev Harness 安装入口（v4.5 起为薄包装）
#
# 逻辑已迁到 scripts/setup_report.py（doctor + fix 双模式、结构化报告）。
# 本文件保留仅为兼容旧文档/hook 中对 setup.sh 的引用，不再承载检测逻辑。
# 直跑 setup.sh == 跑 setup_report.py --fix（执行安装动作）。
#
# 只读体检请用：/dev-harness:setup      或
#   bash scripts/dh-python.sh scripts/setup_report.py

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 兼容旧文档里的 --with-eval：eval 已独立出安装流程，此处剥离该 flag 并提示新入口，
# 其余参数原样透传给 setup_report.py --fix（不因未知参数硬崩 exit 2）
ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--with-eval" ]; then
        echo "[Dev Harness] --with-eval 已废弃：eval 已独立成单独命令，运行 python eval/eval-runner.py run-all"
    else
        ARGS+=("$arg")
    fi
done

echo "[Dev Harness] setup.sh 已迁移到 setup_report.py（--fix 模式），正在执行安装..."
echo "  下次可直接用 /dev-harness:setup（先 doctor 体检，确认后再修复）"
echo ""

exec bash "$SCRIPT_DIR/dh-python.sh" "$SCRIPT_DIR/setup_report.py" --fix "${ARGS[@]}"
