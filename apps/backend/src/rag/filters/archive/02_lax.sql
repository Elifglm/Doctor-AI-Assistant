-- v2 lax filter:
--   - yakinma >= 10ch
--   - oyku OR muayene non-empty (at least one)
--   - exact dedup
-- Output: ic_anamnez_filt_v2_lax
-- Use case: ablation — does dropping rows missing oyku/muayene hurt or help retrieval?

DROP TABLE IF EXISTS ic_anamnez_filt_v2_lax;

CREATE TABLE ic_anamnez_filt_v2_lax AS
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
  AND (
    LENGTH(TRIM(COALESCE("HASTANIN ÖYKÜSÜ", ''))) > 0
    OR LENGTH(TRIM(COALESCE("MUAYENE BULGULARI", ''))) > 0
  );

-- Exact dedup
DELETE FROM ic_anamnez_filt_v2_lax
WHERE FORM_ID NOT IN (
  SELECT MIN(FORM_ID) FROM ic_anamnez_filt_v2_lax
  GROUP BY yakinma, COALESCE(oyku, ''), COALESCE(muayene, '')
);

CREATE INDEX IF NOT EXISTS idx_filt_v2_form_id
  ON ic_anamnez_filt_v2_lax(FORM_ID);
