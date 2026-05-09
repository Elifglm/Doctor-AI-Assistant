#!/usr/bin/env bash
# Ablation matrix runner — 4 conditions × 3 eval scripts on synthetic dataset.
#
# Conditions: {Haiku, Opus} × {strict, db_rescue}
# Layers:     SUT intent, ICD-10 codes, Anamnez 26 fields
#
# Total: 12 result files in data/eval_{intent,icd10,anamnez}/run_*.json
# Estimated cost: ~$10-12 (Haiku ~$0.70, Opus ~$10)
# Estimated time: ~30-45 min
#
# Usage:
#   bash apps/backend/src/scripts/run_ablation.sh
#   bash apps/backend/src/scripts/run_ablation.sh --skip-opus   # cheaper, Haiku only
#   bash apps/backend/src/scripts/run_ablation.sh --only-condition haiku_strict

set -uo pipefail   # NOT -e — we want to continue even if one eval fails

PYTHON="/c/Users/Huckleberry/miniconda3/envs/asr/python.exe"
cd "$(dirname "$0")/../../../.."

SKIP_OPUS=false
SKIP_HAIKU=false
ONLY=""
for arg in "$@"; do
    case $arg in
        --skip-opus) SKIP_OPUS=true ;;
        --skip-haiku) SKIP_HAIKU=true ;;
        --only-condition) shift; ONLY="$1" ;;
    esac
done

run_condition() {
    local condition=$1
    local model=$2
    local val_mode=$3

    if [[ -n "$ONLY" && "$ONLY" != "$condition" ]]; then
        echo "[SKIP] $condition (only-condition=$ONLY)"
        return
    fi

    echo ""
    echo "========================================================================"
    echo "  CONDITION: $condition  (model=$model, validation=$val_mode)"
    echo "  Started: $(date '+%H:%M:%S')"
    echo "========================================================================"

    export ASR_LLM__ANTHROPIC_MODEL="$model"
    export ASR_ICD__VALIDATION_MODE="$val_mode"
    export ASR_SUT__VALIDATION_MODE="$val_mode"

    local logdir="data/eval_logs"
    mkdir -p "$logdir"

    # Layer 1: Anamnez (full pipeline, ~5 LLM calls per transcript)
    echo "[$condition] Running anamnez eval... (log: $logdir/${condition}_anam.log)"
    "$PYTHON" -m apps.backend.src.scripts.eval_anamnez_fields \
        --label "${condition}_anam" > "$logdir/${condition}_anam.log" 2>&1
    grep -E "SUMMARY|ERROR|FAILED|exact_match" "$logdir/${condition}_anam.log" | tail -10

    # Layer 2: ICD-10 (isolated mode, ~2 LLM calls per transcript)
    echo "[$condition] Running ICD-10 eval... (log: $logdir/${condition}_icd.log)"
    "$PYTHON" -m apps.backend.src.scripts.eval_icd10_codes \
        --label "${condition}_icd" > "$logdir/${condition}_icd.log" 2>&1
    grep -E "SUMMARY|ERROR|FAILED|micro_" "$logdir/${condition}_icd.log" | tail -10

    # Layer 3: SUT intent (~2 LLM calls per transcript)
    echo "[$condition] Running SUT eval... (log: $logdir/${condition}_sut.log)"
    "$PYTHON" -m apps.backend.src.scripts.eval_sut_intent \
        --synthetic --label "${condition}_sut" > "$logdir/${condition}_sut.log" 2>&1
    grep -E "SUMMARY|ERROR|FAILED|micro_" "$logdir/${condition}_sut.log" | tail -10

    echo "[$condition] DONE at $(date '+%H:%M:%S')"
}

echo "=========================================================="
echo "  ABLATION MATRIX RUNNER"
echo "  Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================================="

# Run 1: Haiku + strict
if [[ "$SKIP_HAIKU" != true ]]; then
    run_condition "haiku_strict" "claude-haiku-4-5-20251001" "strict"
    run_condition "haiku_dbrescue" "claude-haiku-4-5-20251001" "db_rescue"
fi

if [[ "$SKIP_OPUS" == true ]]; then
    echo "[--skip-opus] Stopping after Haiku conditions."
    exit 0
fi

# Run 3: Opus 4.7 + strict (model upgraded from 4.6 per user request)
run_condition "opus_strict" "claude-opus-4-7" "strict"

# Run 4: Opus 4.7 + db_rescue
run_condition "opus_dbrescue" "claude-opus-4-7" "db_rescue"

echo ""
echo "=========================================================="
echo "  ALL CONDITIONS COMPLETE"
echo "  Finished: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================================="
echo ""
echo "Results:"
ls -lt data/eval_anamnez/run_*.json 2>/dev/null | head -4
ls -lt data/eval_icd10/run_*.json 2>/dev/null | head -4
ls -lt data/eval_intent/run_*synthetic*.json 2>/dev/null | head -4
