#!/usr/bin/env bash
# Run ONLY opus_dbrescue {anam, icd, sut}. Skips strict per user decision.
# Anthropic 529 errors handled by retry/backoff in anthropic_service.py.

set -uo pipefail

PYTHON="/c/Users/Huckleberry/miniconda3/envs/asr/python.exe"
cd "$(dirname "$0")/../../../.."

LOGDIR="data/eval_logs"
mkdir -p "$LOGDIR"

export ASR_LLM__ANTHROPIC_MODEL="claude-opus-4-7"
export ASR_ICD__VALIDATION_MODE="db_rescue"
export ASR_SUT__VALIDATION_MODE="db_rescue"

run_layer() {
    local layer=$1
    local label="opus_dbrescue_${layer}"
    local logfile="$LOGDIR/${label}.log"

    echo ""
    echo "[$(date '+%H:%M:%S')] Running $label..."
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
echo "  OPUS 4.7 db_rescue ONLY — strict skipped per user"
echo "  Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================================="

run_layer "anam"
run_layer "icd"
run_layer "sut"

echo ""
echo "=========================================================="
echo "  ALL 3 db_rescue EVALS COMPLETE"
echo "  Finished: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================================="
