#!/bin/bash
# OpenEMR'a SUT tetkik kodlarini procedure_type tablosuna yukler

set -e

HOST="${MYSQL_HOST:-mysql}"
USER="${MYSQL_USER:-openemr}"
PASS="${MYSQL_PASS:-openemr}"
DB="${MYSQL_DATABASE:-openemr}"

echo "MySQL'in hazir olmasini bekleniyor..."
until mysql -h "$HOST" -u "$USER" -p"$PASS" "$DB" -e "SELECT 1" &>/dev/null; do
  sleep 2
done

echo "OpenEMR tablolarinin olusmasini bekleniyor..."
until mysql -h "$HOST" -u "$USER" -p"$PASS" "$DB" -e "SELECT 1 FROM procedure_type LIMIT 1" &>/dev/null; do
  sleep 5
done

# Zaten yuklu mu kontrol et
COUNT=$(mysql -h "$HOST" -u "$USER" -p"$PASS" "$DB" -sN -e "SELECT COUNT(*) FROM procedure_type WHERE standard_code LIKE '8%' OR standard_code LIKE '9%';")

if [ "$COUNT" -gt "100" ]; then
  echo "SUT tetkik kodlari zaten yuklu ($COUNT kayit). Atlaniyor."
else
  echo "SUT tetkik kodlari yukleniyor..."
  mysql -h "$HOST" -u "$USER" -p"$PASS" "$DB" < /tmp/sut_tetkik.sql
  NEW_COUNT=$(mysql -h "$HOST" -u "$USER" -p"$PASS" "$DB" -sN -e "SELECT COUNT(*) FROM procedure_type WHERE standard_code LIKE '8%' OR standard_code LIKE '9%';")
  echo "Tamamlandi! $NEW_COUNT SUT tetkik kodu yuklendi."
fi
