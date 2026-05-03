-- v1 basic filter:
--   - yakinma >= 10ch
--   - oyku >= 40ch
--   - muayene >= 20ch
--   - exact dedup (keep first FORM_ID per identical (yakinma, oyku, muayene))
-- Output: ic_anamnez_filt_v1_basic

DROP TABLE IF EXISTS ic_anamnez_filt_v1_basic;

CREATE TABLE ic_anamnez_filt_v1_basic AS
SELECT
  FORM_ID,
  TARIH,
  "HASTANIN YAKINMASI"        AS yakinma,
  "HASTANIN ÖYKÜSÜ"           AS oyku,
  "MUAYENE BULGULARI"         AS muayene,
  "ÖZ GEÇMİŞİ\SOY GEÇMİŞİ"    AS oz_gecmisi,
  "SOYGEÇMİŞİ"                AS soy_gecmisi,
  "Sigara"                    AS sigara,
  "Alkol"                     AS alkol,
  "Alerji"                    AS alerji,
  "Sistolik Kan Basıncı"      AS sistolik,
  "Diyastolik Kan Basıncı"    AS diyastolik,
  "Nabız"                     AS nabiz,
  "Ateş"                      AS ates,
  "SO2"                       AS so2,
  "BOY"                       AS boy,
  "KİLO"                      AS kilo,
  "Ağrı skalası"              AS agri_skalasi
FROM ic_anamnez
WHERE
  LENGTH(TRIM(COALESCE("HASTANIN YAKINMASI", ''))) >= 10
  AND LENGTH(TRIM(COALESCE("HASTANIN ÖYKÜSÜ", ''))) >= 40
  AND LENGTH(TRIM(COALESCE("MUAYENE BULGULARI", ''))) >= 20;

-- Exact dedup: keep first FORM_ID per identical core text triple
DELETE FROM ic_anamnez_filt_v1_basic
WHERE FORM_ID NOT IN (
  SELECT MIN(FORM_ID) FROM ic_anamnez_filt_v1_basic
  GROUP BY yakinma, oyku, muayene
);

CREATE INDEX IF NOT EXISTS idx_filt_v1_form_id
  ON ic_anamnez_filt_v1_basic(FORM_ID);
