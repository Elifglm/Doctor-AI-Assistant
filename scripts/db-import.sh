#!/usr/bin/env bash
# Import a klinik_dump_*.sql file produced by scripts/db-export.sh into the
# local MariaDB container. WARNING: overwrites any existing rows in the
# imported tables.

set -euo pipefail

CONTAINER="klinikasistan-mysql-1"
ROOT_USER="root"
ROOT_PASS="root"

# ---- color helpers ----------------------------------------------------------
if [[ -t 1 ]]; then
  C_GREEN="\033[0;32m"; C_YELLOW="\033[0;33m"; C_RED="\033[0;31m"
  C_BOLD="\033[1m"; C_RESET="\033[0m"
else
  C_GREEN=""; C_YELLOW=""; C_RED=""; C_BOLD=""; C_RESET=""
fi
ok()   { printf "${C_GREEN}✓${C_RESET} %s\n" "$*"; }
warn() { printf "${C_YELLOW}⚠${C_RESET} %s\n" "$*"; }
err()  { printf "${C_RED}✗${C_RESET} %s\n" "$*" >&2; }

# ---- args -------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
  err "Kullanim: $0 <dump.sql>"
  echo  "Ornek:   $0 data/dumps/klinik_dump_2026-05-01_2030.sql"
  exit 1
fi

DUMP="$1"
if [[ ! -f "${DUMP}" ]]; then
  err "Dosya bulunamadi: ${DUMP}"
  exit 1
fi

if ! command -v docker >/dev/null; then
  err "docker bulunamadi."
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  err "Container '${CONTAINER}' calismiyor."
  echo  "  Once: docker compose up -d mysql"
  exit 1
fi

SIZE_HUMAN="$(du -h "${DUMP}" | cut -f1)"

# ---- counts (before) --------------------------------------------------------
count() {
  docker exec "${CONTAINER}" mariadb -u"${ROOT_USER}" -p"${ROOT_PASS}" \
    -sN -e "SELECT COUNT(*) FROM ${1};" 2>/dev/null || echo "?"
}

before_sessions="$(count klinikasistan.sessions)"
before_reports="$(count klinikasistan.reports)"
before_patients="$(count openemr.patient_data)"

printf "${C_BOLD}KlinikAsistan DB import${C_RESET}\n"
echo  "Dosya     : ${DUMP} (${SIZE_HUMAN})"
echo  "Container : ${CONTAINER}"
echo
warn  "Bu islem mevcut openemr ve klinikasistan veritabanlarinin"
warn  "icindeki tablolari OVERWRITE eder."
printf "Devam edilsin mi? [e/H] "
read -r REPLY
case "${REPLY}" in
  e|E|y|Y) ;;
  *) echo "Iptal edildi."; exit 0 ;;
esac

echo
echo  "Yukleniyor..."
docker exec -i "${CONTAINER}" mariadb -u"${ROOT_USER}" -p"${ROOT_PASS}" < "${DUMP}"

ok "Tamamlandi"
echo
echo  "Kayit sayilari (oncesi → sonrasi):"
printf "  %-30s %s → %s\n" "openemr.patient_data"      "${before_patients}" "$(count openemr.patient_data)"
printf "  %-30s %s → %s\n" "klinikasistan.sessions"    "${before_sessions}" "$(count klinikasistan.sessions)"
printf "  %-30s %s → %s\n" "klinikasistan.reports"     "${before_reports}"  "$(count klinikasistan.reports)"
echo
echo  "Backend calisyorsa restart et — cache invalidation icin:"
echo  "  kill \$(lsof -ti:8700) && cd $(pwd) && source venv/bin/activate \\"
echo  "    && python -m uvicorn apps.backend.src.main:app --reload --host 127.0.0.1 --port 8700"
