"""OpenEMR REST API client for lab order (procedure order) integration."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from pathlib import Path

import aiomysql
import httpx
from dotenv import dotenv_values
from pymysql.constants import CLIENT as _MYSQL_CLIENT_FLAGS

logger = logging.getLogger(__name__)

# Load OpenEMR-specific env from .env.openemr (separate from main .env to avoid
# pydantic-settings conflicts with AppSettings which forbids extra fields).
# Falls back to OS env vars (OPENEMR_*) when .env.openemr is missing — needed
# for Docker compose where the file isn't bind-mounted into the container.
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_OPENEMR_ENV: dict[str, str | None] = {
    k: v for k, v in os.environ.items() if k.startswith("OPENEMR_")
}
_OPENEMR_ENV.update(dotenv_values(_PROJECT_ROOT / ".env.openemr"))

# OpenEMR doktor username → specialty mapping
# Bu mapping KlinikAsistan auth ile OpenEMR kullanıcılarını eşleştirir
OPENEMR_DOCTORS: dict[str, dict] = {
    "dahiliye": {
        "openemr_username": "doktor1",
        "openemr_user_id": 5,
        "openemr_npi": "",
        "facility_id": "3",
    },
    "ortopedi": {
        "openemr_username": "doktor2",
        "openemr_user_id": 6,
        "openemr_npi": "",
        "facility_id": "3",
    },
}


@dataclass
class OpenEMRConfig:
    """OpenEMR connection configuration loaded from environment."""

    base_url: str = ""
    username: str = "admin"
    password: str = "pass"
    client_id: str = ""
    client_secret: str = ""
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "openemr"
    mysql_password: str = "openemr"
    mysql_db: str = "openemr"

    def __post_init__(self) -> None:
        self.base_url = _OPENEMR_ENV.get("OPENEMR_BASE_URL", "http://localhost/openemr/apis/default")
        self.username = _OPENEMR_ENV.get("OPENEMR_USERNAME", "administrator")
        self.password = _OPENEMR_ENV.get("OPENEMR_PASSWORD", "administrator")
        self.client_id = _OPENEMR_ENV.get("OPENEMR_CLIENT_ID", "")
        self.client_secret = _OPENEMR_ENV.get("OPENEMR_CLIENT_SECRET", "")
        self.mysql_host = _OPENEMR_ENV.get("OPENEMR_MYSQL_HOST", "127.0.0.1")
        self.mysql_port = int(_OPENEMR_ENV.get("OPENEMR_MYSQL_PORT", "3306"))
        self.mysql_user = _OPENEMR_ENV.get("OPENEMR_MYSQL_USER", "openemr")
        self.mysql_password = _OPENEMR_ENV.get("OPENEMR_MYSQL_PASSWORD", "openemr")
        self.mysql_db = _OPENEMR_ENV.get("OPENEMR_MYSQL_DB", "openemr")


@dataclass
class OpenEMROrderResult:
    """Result of sending a procedure order to OpenEMR."""

    success: bool
    order_id: str = ""
    patient_id: str = ""
    error: str = ""


@dataclass
class OpenEMRService:
    """Client for OpenEMR REST API - handles auth, patients, and procedure orders."""

    config: OpenEMRConfig = field(default_factory=OpenEMRConfig)
    _access_token: str = ""
    _client: httpx.AsyncClient | None = None

    async def initialize(self) -> None:
        """Initialize HTTP client and test connection."""
        self._client = httpx.AsyncClient(timeout=30.0, verify=False)
        try:
            await self._authenticate()
            logger.info("OpenEMR baglantisi basarili: %s", self.config.base_url)
        except Exception as e:
            logger.warning("OpenEMR baglantisi basarisiz: %s", e)

    async def shutdown(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _authenticate(self) -> None:
        """Get access token via OAuth2 password grant with stored client credentials."""
        if not self._client:
            raise RuntimeError("OpenEMR client not initialized")

        token_url = self.config.base_url.replace("/apis/default", "") + "/oauth2/default/token"

        if not self.config.client_id or not self.config.client_secret:
            logger.warning(
                "OPENEMR_CLIENT_ID/SECRET .env.openemr'de tanimli degil - "
                "OpenEMR Admin > API Clients'tan kayit yapip env'e eklenmeli"
            )
            return

        try:
            resp = await self._client.post(
                token_url,
                data={
                    "grant_type": "password",
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "user_role": "users",
                    "scope": (
                        "openid offline_access api:oemr "
                        "user/patient.read user/patient.write "
                        "user/practitioner.read user/facility.read"
                    ),
                    "username": self.config.username,
                    "password": self.config.password,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                self._access_token = data.get("access_token", "")
                if self._access_token:
                    logger.info("OpenEMR OAuth2 token alindi")
                    return
            logger.warning(
                "OpenEMR token alinamadi: %d %s",
                resp.status_code, resp.text[:200],
            )
        except Exception as e:
            logger.warning("OpenEMR auth hatasi: %s", e)

    def _headers(self) -> dict[str, str]:
        """Return auth headers for API requests."""
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def _ensure_auth(self) -> None:
        """Re-authenticate if token is missing."""
        if not self._access_token:
            await self._authenticate()

    async def search_patient(self, patient_id: str) -> dict | None:
        """Search for a patient by their external ID (TC Kimlik or MRN)."""
        if not self._client:
            return None

        await self._ensure_auth()

        try:
            resp = await self._client.get(
                f"{self.config.base_url}/api/patient",
                params={"pubpid": patient_id},
                headers=self._headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                patients = data.get("data", data) if isinstance(data, dict) else data
                if isinstance(patients, list) and len(patients) > 0:
                    return patients[0]
            return None
        except Exception as e:
            logger.error("OpenEMR hasta arama hatasi: %s", e)
            return None

    async def create_patient(
        self, patient_id: str, patient_name: str
    ) -> dict | None:
        """Create a new patient in OpenEMR if not exists."""
        if not self._client:
            return None

        await self._ensure_auth()

        # Parse name (assume "Ad Soyad" format)
        parts = patient_name.strip().split(maxsplit=1)
        fname = parts[0] if parts else "Bilinmiyor"
        lname = parts[1] if len(parts) > 1 else ""

        try:
            resp = await self._client.post(
                f"{self.config.base_url}/api/patient",
                json={
                    "pubpid": patient_id,
                    "fname": fname,
                    "lname": lname,
                    "sex": "Unknown",
                    "DOB": "2000-01-01",
                },
                headers=self._headers(),
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                return data.get("data", data)
            logger.error("OpenEMR hasta olusturma hatasi: %d %s", resp.status_code, resp.text)
            return None
        except Exception as e:
            logger.error("OpenEMR hasta olusturma hatasi: %s", e)
            return None

    async def get_or_create_patient(
        self, patient_id: str, patient_name: str
    ) -> str | None:
        """Get OpenEMR patient UUID, creating the patient if needed."""
        patient = await self.search_patient(patient_id)
        if patient:
            return patient.get("uuid") or patient.get("id") or patient.get("pid")

        patient = await self.create_patient(patient_id, patient_name)
        if patient:
            return patient.get("uuid") or patient.get("id") or patient.get("pid")

        return None

    async def create_procedure_order(
        self,
        patient_uuid: str,
        tetkik_codes: list[dict[str, str]],
        doctor_brans: str,
        notes: str = "",
    ) -> OpenEMROrderResult:
        """Create a procedure order (lab order) in OpenEMR.

        Args:
            patient_uuid: OpenEMR patient UUID
            tetkik_codes: List of {"kodu": "...", "adi": "..."} dicts
            doctor_brans: Doctor's specialty for provider mapping
            notes: Additional clinical notes
        """
        if not self._client:
            return OpenEMROrderResult(success=False, error="OpenEMR client not initialized")

        await self._ensure_auth()

        doctor_info = OPENEMR_DOCTORS.get(doctor_brans, {})

        # Build procedure order for OpenEMR
        # OpenEMR procedure order uses /api/patient/{puuid}/procedure_order
        order_items = []
        for i, tetkik in enumerate(tetkik_codes, 1):
            order_items.append({
                "procedure_order_seq": i,
                "procedure_code": tetkik["kodu"],
                "procedure_name": tetkik["adi"],
                "diagnoses": "",
            })

        order_data = {
            "procedure_order_type": "laboratory",
            "provider_id": doctor_info.get("openemr_user_id", 1),
            "order_status": "pending",
            "clinical_hx": notes,
            "order_diagnosis": "",
            "procedure_order_details": order_items,
        }

        try:
            resp = await self._client.post(
                f"{self.config.base_url}/api/patient/{patient_uuid}/procedure_order",
                json=order_data,
                headers=self._headers(),
            )

            if resp.status_code in (200, 201):
                data = resp.json()
                order_id = ""
                if isinstance(data, dict):
                    order_id = str(data.get("data", {}).get("uuid", data.get("id", "")))
                logger.info(
                    "OpenEMR lab order olusturuldu: patient=%s, order=%s, tetkik=%d",
                    patient_uuid, order_id, len(tetkik_codes),
                )
                return OpenEMROrderResult(
                    success=True,
                    order_id=order_id,
                    patient_id=patient_uuid,
                )

            logger.error(
                "OpenEMR order olusturma hatasi: %d %s", resp.status_code, resp.text
            )
            return OpenEMROrderResult(
                success=False,
                error=f"OpenEMR API hatasi: {resp.status_code}",
            )
        except Exception as e:
            logger.error("OpenEMR order olusturma hatasi: %s", e)
            return OpenEMROrderResult(success=False, error=str(e))

    async def send_tetkik_orders(
        self,
        patient_id: str,
        patient_name: str,
        tetkik_list: list[dict[str, str]],
        doctor_brans: str,
        notes: str = "",
    ) -> OpenEMROrderResult:
        """High-level method: ensure patient exists and create procedure order.

        Args:
            patient_id: KlinikAsistan patient ID
            patient_name: Patient display name
            tetkik_list: List of {"kodu": "...", "adi": "...", "brans": "..."} dicts
            doctor_brans: Logged-in doctor's specialty
            notes: Clinical notes
        """
        # Filter tetkik by doctor's specialty
        # "her ikisi" means both specialties can order it
        filtered = [
            t for t in tetkik_list
            if t.get("brans") in (doctor_brans, "her ikisi", "")
        ]

        if not filtered:
            return OpenEMROrderResult(
                success=False,
                error=f"Bu branş ({doctor_brans}) için uygun tetkik bulunamadı",
            )

        # Get or create patient in OpenEMR
        patient_uuid = await self.get_or_create_patient(patient_id, patient_name)
        if not patient_uuid:
            return OpenEMROrderResult(
                success=False,
                error="OpenEMR'de hasta bulunamadı veya oluşturulamadı",
            )

        # Create procedure order
        return await self.create_procedure_order(
            patient_uuid=patient_uuid,
            tetkik_codes=filtered,
            doctor_brans=doctor_brans,
            notes=notes,
        )

    async def list_practitioners(self) -> list[dict]:
        """List all practitioners/doctors from OpenEMR.

        Falls back to direct MySQL query if API auth fails.
        Returns list of dicts with: username, fname, lname, specialty, active, id
        """
        if not self._client:
            return await self._list_practitioners_from_db()

        await self._ensure_auth()

        if self._access_token:
            try:
                resp = await self._client.get(
                    f"{self.config.base_url}/api/practitioner",
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    practitioners = data.get("data", data) if isinstance(data, dict) else data
                    if isinstance(practitioners, list):
                        return [
                            {
                                "username": p.get("username", ""),
                                "fname": p.get("fname", ""),
                                "lname": p.get("lname", ""),
                                "specialty": p.get("specialty", ""),
                                "id": p.get("id") or p.get("uuid", ""),
                            }
                            for p in practitioners
                            if p.get("username")  # skip system/empty users
                        ]
            except Exception as e:
                logger.warning("OpenEMR practitioner API failed: %s", e)

        # Fallback: direct DB query
        return await self._list_practitioners_from_db()

    @staticmethod
    async def _list_practitioners_from_db() -> list[dict]:
        """Fallback: query OpenEMR MySQL directly."""
        try:
            raw = await OpenEMRService._mysql_exec(
                "SELECT id, username, fname, lname, COALESCE(specialty,'') "
                "FROM users WHERE username != '' AND username NOT IN "
                "('admin','administrator','phimail-service','portal-user','oe-system') "
                "AND active = 1 ORDER BY id;"
            )

            practitioners = []
            for line in raw.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) >= 4:
                    practitioners.append({
                        "id": parts[0],
                        "username": parts[1],
                        "fname": parts[2],
                        "lname": parts[3],
                        "specialty": parts[4] if len(parts) > 4 else "",
                    })
            return practitioners
        except Exception as e:
            logger.error("OpenEMR DB query failed: %s", e)
            return []

    @staticmethod
    async def list_appointments(
        date: str,
        provider_id: int | None = None,
    ) -> list[dict]:
        """Fetch appointments from OpenEMR MySQL for a given date.

        Args:
            date: ISO date string (YYYY-MM-DD)
            provider_id: OpenEMR user ID to filter by doctor. None = all.
        """
        provider_filter = ""
        if provider_id is not None:
            provider_filter = f"AND e.pc_aid = {int(provider_id)}"

        query = (
            "SELECT "
            "e.pc_eid, e.pc_title, e.pc_eventDate, e.pc_startTime, e.pc_endTime, "
            "e.pc_duration, e.pc_aid, e.pc_pid, e.pc_apptstatus, e.pc_catid, "
            "c.pc_catname, c.pc_catcolor, "
            "u.fname AS dr_fname, u.lname AS dr_lname, u.username AS dr_username, "
            "p.fname AS pt_fname, p.lname AS pt_lname, p.pubpid AS pt_id, "
            "COALESCE(e.pc_hometext,'') AS reason "
            "FROM openemr_postcalendar_events e "
            "LEFT JOIN openemr_postcalendar_categories c ON e.pc_catid = c.pc_catid "
            "LEFT JOIN users u ON e.pc_aid = u.id "
            "LEFT JOIN patient_data p ON e.pc_pid = p.id "
            f"WHERE e.pc_eventDate = '{date}' {provider_filter} "
            "ORDER BY e.pc_startTime ASC;"
        )

        try:
            raw = await OpenEMRService._mysql_exec(query)

            appointments = []
            for line in raw.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) < 16:
                    continue
                appointments.append({
                    "id": int(parts[0]),
                    "title": parts[1],
                    "date": parts[2],
                    "start_time": parts[3],
                    "end_time": parts[4],
                    "duration_seconds": int(parts[5]) if parts[5] else 900,
                    "provider_id": int(parts[6]) if parts[6] else 0,
                    "patient_id": parts[7],
                    "status": parts[8],
                    "category_id": int(parts[9]) if parts[9] else 0,
                    "category_name": parts[10],
                    "category_color": parts[11],
                    "provider_fname": parts[12],
                    "provider_lname": parts[13],
                    "provider_username": parts[14],
                    "patient_fname": parts[15],
                    "patient_lname": parts[16] if len(parts) > 16 else "",
                    "patient_ext_id": parts[17] if len(parts) > 17 else "",
                    "reason": parts[18] if len(parts) > 18 else "",
                })
            return appointments
        except Exception as e:
            logger.error("OpenEMR appointment query failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # MySQL helper
    # ------------------------------------------------------------------

    @staticmethod
    async def _mysql_exec(query: str) -> str:
        """Execute a MySQL query against the native OpenEMR DB.

        Returns the LAST result set as a TSV string (rows separated by \\n,
        columns by \\t). Multi-statement queries (e.g. ``INSERT ...; SELECT
        LAST_INSERT_ID();``) are supported - the last SELECT's rows are
        returned. INSERT/UPDATE/DELETE alone returns an empty string.
        """
        cfg = OpenEMRConfig()

        conn = await aiomysql.connect(
            host=cfg.mysql_host,
            port=cfg.mysql_port,
            user=cfg.mysql_user,
            password=cfg.mysql_password,
            db=cfg.mysql_db,
            charset="utf8mb4",
            client_flag=_MYSQL_CLIENT_FLAGS.MULTI_STATEMENTS,
            autocommit=True,
        )
        try:
            async with conn.cursor() as cur:
                await cur.execute(query)

                last_output = ""
                while True:
                    if cur.description:
                        rows = await cur.fetchall()
                        last_output = "\n".join(
                            "\t".join("" if v is None else str(v) for v in row)
                            for row in rows
                        )
                    if not await cur.nextset():
                        break
                return last_output
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Push report data to OpenEMR
    # ------------------------------------------------------------------

    @staticmethod
    def _sql_escape(val: str) -> str:
        """Escape single quotes for MySQL."""
        return val.replace("\\", "\\\\").replace("'", "\\'")

    @staticmethod
    async def push_report_to_openemr(
        patient_pid: int,
        provider_id: int,
        report_sections: dict[str, str],
        icd10_codes: list[dict[str, str]],
        sut_codes: list[dict[str, str]] | None = None,
        facility_id: int = 3,
    ) -> dict:
        """Push a complete report to OpenEMR: encounter + vitals + SOAP + ICD-10 + procedure orders.

        Args:
            patient_pid: OpenEMR patient pid (patient_data.pid)
            provider_id: OpenEMR provider/doctor user ID
            report_sections: dict of section_key -> content
            icd10_codes: list of {"code": "K29.0", "text": "Akut gastrit"}
            sut_codes: list of {"code": "902050", "name": "Hemogram"}
            facility_id: OpenEMR facility ID

        Returns:
            dict with encounter_id and status
        """
        esc = OpenEMRService._sql_escape
        mysql = OpenEMRService._mysql_exec

        result = {
            "success": False,
            "encounter_id": 0,
            "vitals_id": 0,
            "soap_id": 0,
            "icd10_count": 0,
            "procedure_order_id": 0,
            "tetkik_count": 0,
            "updated": False,
            "error": "",
        }

        try:
            reason = esc(report_sections.get("hastanin_yakinmasi", "Muayene")[:255])

            # ---- 1. Find existing encounter for this patient today, or create ----
            existing = await mysql(
                f"SELECT id FROM form_encounter "
                f"WHERE pid = {patient_pid} AND provider_id = {provider_id} "
                f"AND DATE(date) = CURDATE() "
                f"ORDER BY id DESC LIMIT 1;"
            )

            if existing.strip():
                # Use existing encounter — update reason
                encounter_id = int(existing.strip().split("\n")[0].strip())
                await mysql(
                    f"UPDATE form_encounter SET reason = '{reason}', last_update = NOW() "
                    f"WHERE id = {encounter_id} AND pid = {patient_pid};"
                )
                result["updated"] = True

                # Clean old data for this encounter so we don't duplicate
                await mysql(f"DELETE FROM billing WHERE encounter = {encounter_id} AND pid = {patient_pid};")
                await mysql(f"DELETE FROM procedure_order WHERE encounter_id = {encounter_id} AND patient_id = {patient_pid};")
                await mysql(f"DELETE FROM procedure_order_code WHERE procedure_order_id IN (SELECT procedure_order_id FROM procedure_order WHERE encounter_id = {encounter_id} AND patient_id = {patient_pid});")
                # Delete old SOAP and vitals forms + form entries
                await mysql(
                    f"DELETE fv FROM form_vitals fv "
                    f"INNER JOIN forms f ON f.form_id = fv.id AND f.formdir = 'vitals' "
                    f"WHERE f.encounter = {encounter_id} AND f.pid = {patient_pid};"
                )
                await mysql(
                    f"DELETE fs FROM form_soap fs "
                    f"INNER JOIN forms f ON f.form_id = fs.id AND f.formdir = 'soap' "
                    f"WHERE f.encounter = {encounter_id} AND f.pid = {patient_pid};"
                )
                await mysql(
                    f"DELETE FROM forms WHERE encounter = {encounter_id} AND pid = {patient_pid} "
                    f"AND formdir IN ('vitals', 'soap');"
                )

                logger.info("Mevcut encounter guncelleniyor: %d", encounter_id)
            else:
                # Create new encounter
                enc_query = (
                    f"INSERT INTO form_encounter "
                    f"(date, reason, facility_id, pid, provider_id, class_code, pc_catid) "
                    f"VALUES (NOW(), '{reason}', {facility_id}, {patient_pid}, {provider_id}, 'AMB', 5); "
                    f"SELECT LAST_INSERT_ID();"
                )
                raw = await mysql(enc_query)
                encounter_id = int(raw.strip().split("\n")[-1].strip())
                # Set encounter = id (OpenEMR expects this)
                await mysql(f"UPDATE form_encounter SET encounter = {encounter_id} WHERE id = {encounter_id};")

                # Register in forms table
                await mysql(
                    f"INSERT INTO forms (date, encounter, form_name, form_id, pid, user, "
                    f"groupname, authorized, formdir, provider_id) "
                    f"VALUES (NOW(), {encounter_id}, 'New Patient Encounter', {encounter_id}, "
                    f"{patient_pid}, 'admin', 'Default', 1, 'newpatient', {provider_id});"
                )

            result["encounter_id"] = encounter_id

            # ---- 2. Push Vitals ----
            vital_map = {
                "sistolik": "bps",
                "diyastolik": "bpd",
                "nabiz": "pulse",
                "ates": "temperature",
                "solunum_sayisi": "respiration",
                "spo2": "oxygen_saturation",
                "kilo": "weight",
                "boy": "height",
            }

            vital_cols = ["date", "pid", "user", "groupname", "authorized", "activity"]
            vital_vals = [f"NOW()", str(patient_pid), "'admin'", "'Default'", "1", "1"]

            has_vitals = False
            for section_key, db_col in vital_map.items():
                val = report_sections.get(section_key, "").strip()
                if val and val not in ("BELIRTILMEDI", "BELIRTILMEDI.", ""):
                    try:
                        numeric = float(val.replace(",", "."))
                        vital_cols.append(db_col)
                        vital_vals.append(str(numeric))
                        has_vitals = True
                    except ValueError:
                        pass

            if has_vitals:
                vitals_query = (
                    f"INSERT INTO form_vitals ({', '.join(vital_cols)}) "
                    f"VALUES ({', '.join(vital_vals)}); "
                    f"SELECT LAST_INSERT_ID();"
                )
                raw = await mysql(vitals_query)
                vitals_id = int(raw.strip().split("\n")[-1].strip())
                result["vitals_id"] = vitals_id

                # Register in forms
                await mysql(
                    f"INSERT INTO forms (date, encounter, form_name, form_id, pid, user, "
                    f"groupname, authorized, formdir, provider_id) "
                    f"VALUES (NOW(), {encounter_id}, 'Vitals', {vitals_id}, "
                    f"{patient_pid}, 'admin', 'Default', 1, 'vitals', {provider_id});"
                )

            # ---- 3. Push SOAP note ----
            subjective_parts = []
            for key in ("hastanin_yakinmasi", "hastanin_oykusu", "oz_gecmisi_soy_gecmisi",
                        "alerji", "sigara", "alkol"):
                val = report_sections.get(key, "").strip()
                if val and val not in ("BELIRTILMEDI", "BELIRTILMEDI.", ""):
                    subjective_parts.append(val.replace("----", ", "))

            objective_parts = []
            for key in ("fizik_muayene", "konsultasyon_muayene"):
                val = report_sections.get(key, "").strip()
                if val and val not in ("BELIRTILMEDI", "BELIRTILMEDI.", ""):
                    objective_parts.append(val.replace("----", ", "))

            assessment = report_sections.get("konsultasyon_sonuc", "").strip()
            if assessment in ("BELIRTILMEDI", "BELIRTILMEDI.", ""):
                assessment = ""

            plan_parts = []
            for key in ("tedavi", "oneri", "uyari", "kontrol_zamani"):
                val = report_sections.get(key, "").strip()
                if val and val not in ("BELIRTILMEDI", "BELIRTILMEDI.", ""):
                    plan_parts.append(val.replace("----", ", "))

            soap_query = (
                f"INSERT INTO form_soap (date, pid, user, groupname, authorized, activity, "
                f"subjective, objective, assessment, plan) "
                f"VALUES (NOW(), {patient_pid}, 'admin', 'Default', 1, 1, "
                f"'{esc(chr(10).join(subjective_parts))}', "
                f"'{esc(chr(10).join(objective_parts))}', "
                f"'{esc(assessment)}', "
                f"'{esc(chr(10).join(plan_parts))}'); "
                f"SELECT LAST_INSERT_ID();"
            )
            raw = await mysql(soap_query)
            soap_id = int(raw.strip().split("\n")[-1].strip())
            result["soap_id"] = soap_id

            # Register in forms
            await mysql(
                f"INSERT INTO forms (date, encounter, form_name, form_id, pid, user, "
                f"groupname, authorized, formdir, provider_id) "
                f"VALUES (NOW(), {encounter_id}, 'SOAP', {soap_id}, "
                f"{patient_pid}, 'admin', 'Default', 1, 'soap', {provider_id});"
            )

            # ---- 4. Push ICD-10 diagnoses to billing ----
            icd_count = 0
            for icd in icd10_codes:
                code = esc(icd.get("code", ""))
                text = esc(icd.get("text", ""))
                if not code:
                    continue
                await mysql(
                    f"INSERT INTO billing (date, code_type, code, code_text, pid, "
                    f"provider_id, user, encounter, authorized, activity, groupname) "
                    f"VALUES (NOW(), 'ICD10', '{code}', '{text}', {patient_pid}, "
                    f"{provider_id}, 1, {encounter_id}, 1, 1, 'Default');"
                )
                icd_count += 1
            result["icd10_count"] = icd_count

            # ---- 5. Push SUT tetkik as procedure order ----
            if sut_codes:
                # Build ICD diagnosis string for the order
                icd_diag = ";".join(f"ICD10:{c['code']}" for c in icd10_codes) if icd10_codes else ""

                order_query = (
                    f"INSERT INTO procedure_order "
                    f"(provider_id, patient_id, encounter_id, date_ordered, "
                    f"order_priority, order_status, procedure_order_type, "
                    f"clinical_hx, order_diagnosis, activity) "
                    f"VALUES ({provider_id}, {patient_pid}, {encounter_id}, NOW(), "
                    f"'normal', 'pending', 'laboratory_test', "
                    f"'{esc(reason[:255])}', '{esc(icd_diag[:255])}', 1); "
                    f"SELECT LAST_INSERT_ID();"
                )
                raw = await mysql(order_query)
                order_id = int(raw.strip().split("\n")[-1].strip())
                result["procedure_order_id"] = order_id

                # Insert each tetkik as a line item
                for seq, sut in enumerate(sut_codes, 1):
                    sut_code = esc(sut.get("code", ""))
                    sut_name = esc(sut.get("name", ""))
                    if not sut_code:
                        continue
                    await mysql(
                        f"INSERT INTO procedure_order_code "
                        f"(procedure_order_id, procedure_order_seq, procedure_code, "
                        f"procedure_name, diagnoses) "
                        f"VALUES ({order_id}, {seq}, '{sut_code}', '{sut_name}', "
                        f"'{esc(icd_diag[:255])}');"
                    )
                result["tetkik_count"] = len(sut_codes)

                logger.info(
                    "OpenEMR procedure order olusturuldu: order=%d, tetkik=%d",
                    order_id, len(sut_codes),
                )

            # ---- 6. Update patient history_data ----
            history_updates: list[str] = []

            # Tobacco / Sigara
            sigara = report_sections.get("sigara", "").strip()
            if sigara and sigara not in ("BELIRTILMEDI", "BELIRTILMEDI.", ""):
                history_updates.append(f"tobacco = '{esc(sigara)}'")

            # Alcohol / Alkol
            alkol = report_sections.get("alkol", "").strip()
            if alkol and alkol not in ("BELIRTILMEDI", "BELIRTILMEDI.", ""):
                history_updates.append(f"alcohol = '{esc(alkol)}'")

            # Öz geçmiş → additional_history
            oz_gecmis = report_sections.get("oz_gecmisi_soy_gecmisi", "").strip()
            if oz_gecmis and oz_gecmis not in ("BELIRTILMEDI", "BELIRTILMEDI.", ""):
                history_updates.append(f"additional_history = '{esc(oz_gecmis.replace(chr(10), ', '))}'")

            # Soy geçmiş → family history fields
            soy_gecmis = report_sections.get("soy_gecmisi", "").strip()
            if soy_gecmis and soy_gecmis not in ("BELIRTILMEDI", "BELIRTILMEDI.", ""):
                soy_lower = soy_gecmis.lower()
                if "diyabet" in soy_lower or "seker" in soy_lower:
                    history_updates.append("relatives_diabetes = 'Var'")
                if "hipertansiyon" in soy_lower or "tansiyon" in soy_lower:
                    history_updates.append("relatives_high_blood_pressure = 'Var'")
                if "kalp" in soy_lower or "kardiy" in soy_lower:
                    history_updates.append("relatives_heart_problems = 'Var'")
                if "kanser" in soy_lower:
                    history_updates.append("relatives_cancer = 'Var'")
                if "inme" in soy_lower or "felc" in soy_lower:
                    history_updates.append("relatives_stroke = 'Var'")

            # Alerji → Risk Factors (exams alanı)
            alerji = report_sections.get("alerji", "").strip()
            if alerji and alerji not in ("BELIRTILMEDI", "BELIRTILMEDI.", ""):
                history_updates.append(f"exams = '{esc(alerji.replace(chr(10), ', '))}'")

            if history_updates:
                update_sql = ", ".join(history_updates)
                await mysql(
                    f"UPDATE history_data SET {update_sql}, date = NOW() "
                    f"WHERE pid = {patient_pid} ORDER BY id DESC LIMIT 1;"
                )
                result["history_updated"] = True
                logger.info("OpenEMR history_data guncellendi: pid=%d", patient_pid)

            result["success"] = True
            logger.info(
                "OpenEMR push basarili: encounter=%d, vitals=%d, soap=%d, icd10=%d",
                encounter_id, result["vitals_id"], soap_id, icd_count,
            )

        except Exception as e:
            result["error"] = str(e)
            logger.error("OpenEMR push hatasi: %s", e)

        return result
