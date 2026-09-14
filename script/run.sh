#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$PROJECT_ROOT"

# 可通过同名环境变量覆盖的模拟参数。
USER_COUNT="${USER_COUNT:-1000}"
START_DATE="${START_DATE:-2023-06-15}"
END_DATE="${END_DATE:-2023-06-30}"
MAX_WORKERS="${MAX_WORKERS:-32}"
ACTIVATE_PROB="${ACTIVATE_PROB:-0.8}"
PROB_OF_TECHNICAL="${PROB_OF_TECHNICAL:-0.5}"
PREPARE_ONLY="${PREPARE_ONLY:-0}"
CONFIG_PATH="${CONFIG_PATH:-config/api.yaml}"
TEMPLATE_DB="${TEMPLATE_DB:-data/sys_1000.db}"
BELIEF_SOURCE="${BELIEF_SOURCE:-util/belief/belief_1000_0129.csv}"
RUN_DIR="${RUN_DIR:-logs_${USER_COUNT}_qwen3_30b_10td}"
PYTHON="${PYTHON:-venv/bin/python}"

if [[ ! "$USER_COUNT" =~ ^[0-9]+$ ]] || (( USER_COUNT < 1 || USER_COUNT > 1000 )); then
    echo "USER_COUNT 必须是 1 到 1000 之间的整数" >&2
    exit 2
fi

if [[ "$PREPARE_ONLY" != "0" && "$PREPARE_ONLY" != "1" ]]; then
    echo "PREPARE_ONLY 只能为 0 或 1" >&2
    exit 2
fi

if [[ "$START_DATE" != "2023-06-15" ]]; then
    echo "当前脚本用于全新运行，START_DATE 必须为 2023-06-15" >&2
    echo "从其他日期续跑时请按照 docs/SIMULATION_GUIDE_ZH.md 操作" >&2
    exit 2
fi

for required_path in "$PYTHON" "$CONFIG_PATH" "$TEMPLATE_DB" "$BELIEF_SOURCE"; do
    if [[ ! -e "$required_path" ]]; then
        echo "缺少运行文件: $required_path" >&2
        exit 2
    fi
done

if [[ -e "$RUN_DIR" ]]; then
    echo "运行目录已存在，拒绝覆盖: $RUN_DIR" >&2
    echo "请设置新的 RUN_DIR，或先手动归档原目录" >&2
    exit 2
fi

mkdir -p "$RUN_DIR"

USER_DB="$RUN_DIR/user_${USER_COUNT}.db"
FORUM_DB="$RUN_DIR/forum_${USER_COUNT}.db"
BELIEF_FILE="$RUN_DIR/belief_${USER_COUNT}.csv"
LOG_FILE="$RUN_DIR/simulation.log"
MPL_CACHE_DIR="$RUN_DIR/.matplotlib"
mkdir -p "$MPL_CACHE_DIR"

"$PYTHON" script/prepare_simulation_run.py \
    --template-db "$TEMPLATE_DB" \
    --belief-source "$BELIEF_SOURCE" \
    --user-count "$USER_COUNT" \
    --user-db "$USER_DB" \
    --belief-output "$BELIEF_FILE"

echo "=== TwinMarket 模拟配置 ==="
echo "用户数量: $USER_COUNT"
echo "日期范围: $START_DATE -> $END_DATE"
echo "并发线程: $MAX_WORKERS"
echo "激活概率: $ACTIVATE_PROB"
echo "运行目录: $RUN_DIR"
echo "观察命令: $PYTHON script/monitor_simulation.py --log-dir $RUN_DIR"
echo "==========================="

if [[ "$PREPARE_ONLY" == "1" ]]; then
    echo "PREPARE_ONLY=1：数据准备完成，未启动模拟"
    exit 0
fi

MPLCONFIGDIR="$MPL_CACHE_DIR" "$PYTHON" simulation.py \
    --log_dir "$RUN_DIR" \
    --forum_db "$FORUM_DB" \
    --user_db "$USER_DB" \
    --user_graph_save_name "user_graph_${USER_COUNT}" \
    --start_date "$START_DATE" \
    --end_date "$END_DATE" \
    --max_workers "$MAX_WORKERS" \
    --node "$USER_COUNT" \
    --config_path "$CONFIG_PATH" \
    --belief_init_path "$BELIEF_FILE" \
    --activate_prob "$ACTIVATE_PROB" \
    --prob_of_technical "$PROB_OF_TECHNICAL" \
    2>&1 | tee "$LOG_FILE"

echo "模拟完成，结果目录: $RUN_DIR"
