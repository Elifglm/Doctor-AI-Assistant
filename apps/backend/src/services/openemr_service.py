"""OpenEMR REST API client for lab order (procedure order) integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pathlib import Path

import httpx
from dotenv import dotenv_values

logger = logging.getLogger(__name__)

# Load OpenEMR-specific env from .env.openemr (separate from main .env to avoid
# pydantic-settings conflicts with AppSettings which forbids extra fields).
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_OPENEMR_ENV = dotenv_values(_PROJECT_ROOT / ".env.openemr")

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

    def __post_init__(self) -> None:
        self.base_url = _OPENEMR_ENV.get("OPENEMR_BASE_URL", "http://localhost:8300/apis/default")
        self.username = _OPENEMR_ENV.get("OPENEMR_USERNAME", "admin")
        self.password = _OPENEMR_ENV.get("OPENEMR_PASSWORD", "pass")


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
        """Get access token from OpenEMR using password grant."""
        if not self._client:
            raise RuntimeError("OpenEMR client not initialized")

        # OpenEMR 7.x uses /oauth2/default/token for auth
        # But for simpler setups, it also supports basic /api auth
        # Try the standard OpenEMR API auth endpoint
        token_url = self.config.base_url.replace("/apis/default", "") + "/oauth2/default/token"

        # First, we need to register a client or use password grant
        # OpenEMR 7.x supports password grant with registered clients
        # For prototype, we'll use the standard API with session-based auth
        auth_url = f"{self.config.base_url}/portal/login"

        # Try direct API authentication (OpenEMR supports Basic Auth for API)
        response = await self._client.post(
            f"{self.config.base_url}/fhir/metadata",
            headers={"Accept": "application/json"},
        )

        # For OpenEMR, we'll use the credentials-based approach
        # The standard REST API uses /api/auth endpoint
        auth_data = {
            "grant_type": "password",
            "username": self.config.username,
            "password": self.config.password,
        }

        try:
            resp = await self._client.post(token_url, data=auth_data)
            if resp.status_code == 200:
                data = resp.json()
                self._access_token = data.get("access_token", "")
                logger.info("OpenEMR OAuth2 token alindi")
                return
        except Exception:
            pass

        # Fallback: try registration flow first, then token
        # OpenEMR 7.x requires client registration before OAuth2
        reg_url = self.config.base_url.replace("/apis/default", "") + "/oauth2/default/registration"
        try:
            reg_resp = await self._client.post(
                reg_url,
                json={
                    "application_type": "private",
                    "redirect_uris": ["http://localhost:8700/callback"],
                    "client_name": "KlinikAsistan",
                    "token_endpoint_auth_method": "client_secret_post",
                    "contacts": ["admin@klinikasistan.local"],
                    "scope": "openid api:oemr api:fhir api:port",
                },
                headers={"Accept": "application/json"},
            )
            if reg_resp.status_code in (200, 201):
                reg_data = reg_resp.json()
                client_id = reg_data.get("client_id", "")
                client_secret = reg_data.get("client_secret", "")

                # Now get token with client credentials
                resp = await self._client.post(
                    token_url,
                    data={
                        "grant_type": "password",
                        "username": self.config.username,
                        "password": self.config.password,
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "scope": "openid api:oemr api:fhir",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self._access_token = data.get("access_token", "")
                    logger.info("OpenEMR OAuth2 token alindi (registration flow)")
                    return
        except Exception as e:
            logger.debug("OpenEMR registration flow failed: %s", e)

        logger.warning("OpenEMR authentication failed - orders will be queued locally")

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
        """Fallback: query OpenEMR MySQL directly via docker exec."""
        import asyncio

        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "exec", "-T", "mysql",
                "mysql", "-u", "openemr", "-popenemr", "openemr",
                "-sN", "-e",
                "SELECT id, username, fname, lname, COALESCE(specialty,'') "
                "FROM users WHERE username != '' AND username != 'admin' "
                "AND active = 1 ORDER BY id;",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            practitioners = []
            for line in stdout.decode().strip().split("\n"):
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
        import asyncio

        provider_filter = ""
        if provider_id is not None:
            provider_filter = f"AND e.pc_aid = {int(provider_id)}"

        query = (
            "SELECT "
            "e.pc_eid, e.pc_title, e.pc_eventDate, e.pc_startTime, e.pc_endTime, "
            "e.pc_duration, e.pc_aid, e.pc_pid, e.pc_apptstatus, e.pc_catid, "
            "c.pc_catname, c.pc_catcolor, "
            "u.fname AS dr_fname, u.lname AS dr_lname, u.username AS dr_username, "
            "p.fname AS pt_fname, p.lname AS pt_lname, p.pubpid AS pt_id "
            "FROM openemr_postcalendar_events e "
            "LEFT JOIN openemr_postcalendar_categories c ON e.pc_catid = c.pc_catid "
            "LEFT JOIN users u ON e.pc_aid = u.id "
            "LEFT JOIN patient_data p ON e.pc_pid = p.id "
            f"WHERE e.pc_eventDate = '{date}' {provider_filter} "
            "ORDER BY e.pc_startTime ASC;"
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "exec", "-T", "mysql",
                "mysql", "-u", "openemr", "-popenemr", "openemr",
                "-sN", "-e", query,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            appointments = []
            for line in stdout.decode().strip().split("\n"):
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
                })
            return appointments
        except Exception as e:
            logger.error("OpenEMR appointment query failed: %s", e)
            return []
