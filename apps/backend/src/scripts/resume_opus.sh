#!/usr/bin/env bash
# Resume Opus 4.7 ablation — skips already-completed opus_strict_anam.
# Runs: opus_strict {icd, sut} + opus_dbrescue {anam, icd, sut}.
#
# Anthropic 529 errors are now handled by retry/backoff in anthropic_service.py.

set -uo pipefail

PYTHON="/c/Users/Huckleberry/miniconda3/envs/asr/python.exe"
cd "$(dirname "$0")/../../../.."

LOGDIR="data/eval_logs"
mkdir -p "$LOGDIR"

run_eval() {
    local condition=$1
    local model=$2
    local val_mode=$3
    local layer=$4   # anam | icd | sut

    export ASR_LLM__ANTHROPIC_MODEL="$model"
    export ASR_ICD__VALIDATION_MODE="$val_mode"
    export ASR_SUT__VALIDATION_MODE="$val_mode"

    local label="${condition}_${layer}"
    local logfile="$LOGDIR/${label}.log"

    echo ""
    echo "[$(date '+%H:%M:%S')] Running $label (model=$model)..."
    case $layer in
        anam) "$PYTHON" -m apps.backend.src.scripts.eval_anamnez_fields --label "$label" > "$logfile" 2>&1 ;;
        icd)  "$PYTHON" -m apps.backend.src.scripts.eval_icd10_codes   --label "$label" > "$logfile" 2>&1 ;;
        sut)  "$PYTHON" -m apps.backend.src.scripts.eval_sut_intent --synthetic --label "$label" > "$logfile" 2>&1 ;;
    esac
    local errs=$(grep -c "529 <none>\|HTTPStatusError" "$logfile" 2>/dev/null || echo 0)
    local retries=$(grep -c "retrying in" "$logfile" 2>/dev/null || echo 0)
    echo "[$(date '+%H:%M:%S')] $label DONE. 529-errors=$errs retries=$retries"
    grep -E "SUMMARY|micro_|exact_match|F1=" "$logfile" | tail -5
}

echo "=========================================================="
echo "  RESUME OPUS 4.7 ABLATION"
echo "  Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================================="

# opus_strict — anam already done, retry icd + sut
run_eval "opus_strict" "claude-opus-4-7" "strict" "icd"
run_eval "opus_strict" "claude-opus-4-7" "strict" "sut"

# opus_dbrescue — all 3 evals
run_eval "opus_dbrescue" "claude-opus-4-7" "db_rescue" "anam"
run_eval "opus_dbrescue" "claude-opus-4-7" "db_rescue" "icd"
run_eval "opus_dbrescue" "claude-opus-4-7" "db_rescue" "sut"

echo ""
echo "=========================================================="
echo "  ALL 5 RESUME EVALS COMPLETE"
echo "  Finished: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================================="
