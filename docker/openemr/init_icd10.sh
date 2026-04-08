#!/bin/bash
# OpenEMR'a Turkce ICD-10 kodlarini yukler (sadece ilk kurulumda)

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
until mysql -h "$HOST" -u "$USER" -p"$PASS" "$DB" -e "SELECT 1 FROM codes LIMIT 1" &>/dev/null; do
  sleep 5
done

# Zaten yuklu mu kontrol et
COUNT=$(mysql -h "$HOST" -u "$USER" -p"$PASS" "$DB" -sN -e "SELECT COUNT(*) FROM codes WHERE code_type = 102;")

if [ "$COUNT" -gt "0" ]; then
  echo "ICD-10 kodlari zaten yuklu ($COUNT kayit). Atlaniyor."
else
  echo "Turkce ICD-10 kodlari yukleniyor..."
  mysql -h "$HOST" -u "$USER" -p"$PASS" "$DB" < /tmp/icd10_tr.sql
  NEW_COUNT=$(mysql -h "$HOST" -u "$USER" -p"$PASS" "$DB" -sN -e "SELECT COUNT(*) FROM codes WHERE code_type = 102;")
  echo "Tamamlandi! $NEW_COUNT ICD-10 kodu yuklendi."
fi
