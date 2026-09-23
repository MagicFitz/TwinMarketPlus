#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$PROJECT_ROOT"

# 可通过同名环境变量覆盖的模拟参数。
USER_COUNT="${USER_COUNT:-1000}"
START_DATE="${START_DATE:-2023-06-15}"
END_DATE="${END_DATE:-2023-06-30}"
RESUME_DATE="${RESUME_DATE:-}"
RUN_ID="${RUN_ID:-run_$(date -u +%Y%m%dT%H%M%SZ)-$$}"
RANDOM_SEED="${RANDOM_SEED:-20260916}"
MAX_WORKERS="${MAX_WORKERS:-32}"
ACTIVATE_PROB="${ACTIVATE_PROB:-0.8}"
PROB_OF_TECHNICAL="${PROB_OF_TECHNICAL:-0.5}"
PREPARE_ONLY="${PREPARE_ONLY:-0}"
CONFIG_PATH="${CONFIG_PATH:-config/api.yaml}"
TEMPLATE_DB="${TEMPLATE_DB:-data/sys_1000.db}"
BELIEF_SOURCE="${BELIEF_SOURCE:-util/belief/belief_1000_0129.csv}"
RUN_DIR="runs/${RUN_ID}"
PYTHON="${PYTHON:-venv/bin/python}"

if [[ ! "$USER_COUNT" =~ ^[0-9]+$ ]] || (( USER_COUNT < 1 || USER_COUNT > 1000 )); then
    echo "USER_COUNT 必须是 1 到 1000 之间的整数" >&2
    exit 2
fi

if [[ "$PREPARE_ONLY" != "0" && "$PREPARE_ONLY" != "1" ]]; then
    echo "PREPARE_ONLY 只能为 0 或 1" >&2
    exit 2
fi

if [[ -n "$RESUME_DATE" ]]; then
    START_DATE="$RESUME_DATE"
elif [[ "$START_DATE" != "2023-06-15" ]]; then
    echo "全新运行的 START_DATE 必须为 2023-06-15；续跑请设置 RESUME_DATE" >&2
    exit 2
fi

for required_path in "$PYTHON" "$CONFIG_PATH" "$TEMPLATE_DB" "$BELIEF_SOURCE"; do
    if [[ ! -e "$required_path" ]]; then
        echo "缺少运行文件: $required_path" >&2
        exit 2
    fi
done

USER_DB="$RUN_DIR/user_${USER_COUNT}.db"
FORUM_DB="$RUN_DIR/forum_${USER_COUNT}.db"
BELIEF_FILE="$RUN_DIR/belief_${USER_COUNT}.csv"
LOG_FILE="$RUN_DIR/simulation.log"
MPL_CACHE_DIR="$RUN_DIR/.matplotlib"
if [[ -z "$RESUME_DATE" ]]; then
    "$PYTHON" script/run_contract.py create \
        --run-id "$RUN_ID" \
        --template-db "$TEMPLATE_DB" \
        --belief-source "$BELIEF_SOURCE" \
        --config-path "$CONFIG_PATH" \
        --user-count "$USER_COUNT" \
        --start-date "$START_DATE" \
        --end-date "$END_DATE" \
        --max-workers "$MAX_WORKERS" \
        --activate-prob "$ACTIVATE_PROB" \
        --prob-of-technical "$PROB_OF_TECHNICAL" \
        --random-seed "$RANDOM_SEED" \
        --command-summary "bash script/run.sh RUN_ID=$RUN_ID USER_COUNT=$USER_COUNT START_DATE=$START_DATE END_DATE=$END_DATE"

    "$PYTHON" script/prepare_simulation_run.py \
        --template-db "$TEMPLATE_DB" \
        --belief-source "$BELIEF_SOURCE" \
        --user-count "$USER_COUNT" \
        --user-db "$USER_DB" \
        --belief-output "$BELIEF_FILE"

    "$PYTHON" script/run_contract.py record-prepared \
        --run-dir "$RUN_DIR" \
        --user-db "$USER_DB" \
        --belief-file "$BELIEF_FILE"
fi

mkdir -p "$MPL_CACHE_DIR"

echo "=== TwinMarket 模拟配置 ==="
echo "用户数量: $USER_COUNT"
echo "日期范围: $START_DATE -> $END_DATE"
echo "并发线程: $MAX_WORKERS"
echo "激活概率: $ACTIVATE_PROB"
echo "运行目录: $RUN_DIR"
echo "运行 ID: $RUN_ID"
echo "随机种子: $RANDOM_SEED"
echo "观察命令: $PYTHON script/monitor_simulation.py --log-dir $RUN_DIR"
echo "==========================="

if [[ "$PREPARE_ONLY" == "1" ]]; then
    echo "PREPARE_ONLY=1：数据准备完成，未启动模拟"
    exit 0
fi

RESUME_ARGS=()
if [[ -n "$RESUME_DATE" ]]; then
    RESUME_ARGS=(--resume-date "$RESUME_DATE")
fi

MPLCONFIGDIR="$MPL_CACHE_DIR" "$PYTHON" script/run_contract.py launch \
    --run-dir "$RUN_DIR" \
    --user-count "$USER_COUNT" \
    "${RESUME_ARGS[@]}" \
    --log-file "$LOG_FILE" \
    -- "$PYTHON" simulation.py \
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
    --random_seed "$RANDOM_SEED" \
    --checkpoint_state_path "$RUN_DIR/state.json"

echo "模拟完成，结果目录: $RUN_DIR"
