#!/usr/bin/env bash
# Dump both OpenEMR and KlinikAsistan databases from the running MariaDB
# container into a timestamped SQL file under data/dumps/.
#
# Share the resulting file with teammates via Whatsapp / Drive — they import
# it via scripts/db-import.sh.

set -euo pipefail

CONTAINER="klinikasistan-mysql-1"
ROOT_USER="root"
ROOT_PASS="root"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DUMP_DIR="${PROJECT_ROOT}/data/dumps"

# ---- color helpers (no-op if not a TTY) -------------------------------------
if [[ -t 1 ]]; then
  C_GREEN="\033[0;32m"; C_YELLOW="\033[0;33m"; C_RED="\033[0;31m"
  C_BOLD="\033[1m"; C_RESET="\033[0m"
else
  C_GREEN=""; C_YELLOW=""; C_RED=""; C_BOLD=""; C_RESET=""
fi
ok()   { printf "${C_GREEN}✓${C_RESET} %s\n" "$*"; }
warn() { printf "${C_YELLOW}⚠${C_RESET} %s\n" "$*"; }
err()  { printf "${C_RED}✗${C_RESET} %s\n" "$*" >&2; }

# ---- preflight --------------------------------------------------------------
if ! command -v docker >/dev/null; then
  err "docker bulunamadi. Docker Desktop kurulu mu?"
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  err "Container '${CONTAINER}' calismiyor."
  echo  "  Once: docker compose up -d mysql"
  exit 1
fi

mkdir -p "${DUMP_DIR}"
TIMESTAMP="$(date +%Y-%m-%d_%H%M)"
OUT_FILE="${DUMP_DIR}/klinik_dump_${TIMESTAMP}.sql"

# ---- counts (before) --------------------------------------------------------
count() {
  docker exec "${CONTAINER}" mariadb -u"${ROOT_USER}" -p"${ROOT_PASS}" \
    -sN -e "SELECT COUNT(*) FROM ${1};" 2>/dev/null || echo "?"
}

printf "${C_BOLD}KlinikAsistan + OpenEMR DB dump${C_RESET}\n"
echo  "Container : ${CONTAINER}"
echo  "Cikti     : ${OUT_FILE}"
echo
echo  "Dump aliniyor..."

# ---- dump -------------------------------------------------------------------
docker exec "${CONTAINER}" mariadb-dump \
  -u"${ROOT_USER}" -p"${ROOT_PASS}" \
  --databases openemr klinikasistan \
  --routines --triggers --single-transaction \
  > "${OUT_FILE}"

if [[ ! -s "${OUT_FILE}" ]]; then
  err "Dump dosyasi bos — bir hata olmus olabilir."
  exit 1
fi

SIZE_HUMAN="$(du -h "${OUT_FILE}" | cut -f1)"

ok "Tamamlandi (${SIZE_HUMAN})"
echo
echo  "Tablodaki kayit sayilari (referans icin):"
printf "  %-30s %s\n" "openemr.patient_data"      "$(count openemr.patient_data)"
printf "  %-30s %s\n" "openemr.users"             "$(count openemr.users)"
printf "  %-30s %s\n" "klinikasistan.users"       "$(count klinikasistan.users)"
printf "  %-30s %s\n" "klinikasistan.sessions"    "$(count klinikasistan.sessions)"
printf "  %-30s %s\n" "klinikasistan.reports"     "$(count klinikasistan.reports)"
echo
echo  "Bu dosyayi ekibe gonder:"
printf "  ${C_BOLD}%s${C_RESET}\n" "${OUT_FILE}"
echo
echo  "Onlar import etmek icin:"
printf "  ${C_BOLD}./scripts/db-import.sh %s${C_RESET}\n" "${OUT_FILE}"
