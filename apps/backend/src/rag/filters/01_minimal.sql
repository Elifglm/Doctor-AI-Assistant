-- v1 minimal filter (only baseline corpus; no length thresholds):
--   - yakinma must be non-empty (basic sanity)
--   - exact dedup on (yakinma, oyku, muayene) tuple
-- Output: ic_anamnez_filt_v1_minimal
--
-- Rationale: This hospital's docs are telegraphic; oyku is mostly "X GUNDUR"
-- (median 8ch). Length thresholds discard valid clinical content. Field
-- presence is the trustworthy signal — if a field was filled, the doctor
-- intended it.
--
-- v3 (MinHash fuzzy dedup) is applied separately by dedup_anamnez.py over
-- this table.

DROP TABLE IF EXISTS ic_anamnez_filt_v1_minimal;

CREATE TABLE ic_anamnez_filt_v1_minimal AS
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
WHERE TRIM(COALESCE("HASTANIN YAKINMASI", '')) <> '';

-- Exact dedup: keep first FORM_ID per identical core text triple
DELETE FROM ic_anamnez_filt_v1_minimal
WHERE FORM_ID NOT IN (
  SELECT MIN(FORM_ID) FROM ic_anamnez_filt_v1_minimal
  GROUP BY yakinma, COALESCE(oyku, ''), COALESCE(muayene, '')
);

CREATE INDEX IF NOT EXISTS idx_filt_v1min_form_id
  ON ic_anamnez_filt_v1_minimal(FORM_ID);
