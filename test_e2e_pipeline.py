"""E2E test: Session creation -> WebSocket audio -> ASR -> AI Report generation."""
import asyncio
import json
import sys
import time
import httpx
import websockets

BASE_URL = "http://127.0.0.1:8700"
WS_BASE = "ws://127.0.0.1:8700"
TOKEN = None
AUDIO_FILE = "test_audio/ornek_diyalog.wav"
CHUNK_SIZE = 4096  # bytes per WS binary frame


async def login():
    global TOKEN
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.post("/api/v1/auth/login", json={
            "username": "admin", "password": "admin"
        })
        resp.raise_for_status()
        TOKEN = resp.json()["access_token"]
        print(f"[OK] Login basarili, token alindi")


async def create_session() -> int:
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.post("/api/v1/sessions", json={
            "patient_id": "E2E-TEST-002",
            "patient_name": "E2E Test Hasta",
            "doctor_name": "Dr. Admin",
            "session_type": "initial",
            "kvkk_consent": True,
            "notes": "Automated E2E test"
        }, headers={"Authorization": f"Bearer {TOKEN}"})
        resp.raise_for_status()
        session = resp.json()
        print(f"[OK] Session olusturuldu: id={session['id']}")
        return session["id"]


async def test_ws_audio(session_id: int) -> bool:
    """Connect to WS, send audio file as binary chunks, send stop, wait for result."""
    url = f"{WS_BASE}/api/v1/sessions/ws/{session_id}"
    print(f"\n--- WebSocket ASR Test (session {session_id}) ---")
    print(f"[..] WebSocket'e baglaniliyor: {url}")

    result_received = False
    error_received = False
    error_msg = ""
    progress_stages = []

    try:
        async with websockets.connect(url, max_size=50 * 1024 * 1024) as ws:
            print(f"[OK] WebSocket baglandi")

            # Read initial status message
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            print(f"[<<] {data.get('type')}: {data.get('message', '')}")

            # Send audio file as binary chunks
            print(f"[..] Audio dosyasi gonderiliyor: {AUDIO_FILE}")
            chunk_count = 0
            with open(AUDIO_FILE, "rb") as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    await ws.send(chunk)
                    chunk_count += 1

            print(f"[OK] {chunk_count} chunk gonderildi")

            # Send stop signal
            print(f"[>>] Stop sinyali gonderiliyor...")
            await ws.send(json.dumps({"type": "stop"}))

            # Wait for progress and result messages
            start_time = time.time()
            timeout = 300  # 5 minute timeout for ASR processing

            while True:
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    print(f"[HATA] Timeout! {timeout}s gecti, sonuc alinamadi")
                    break

                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=30)
                    data = json.loads(msg)
                    msg_type = data.get("type", "")

                    if msg_type == "progress":
                        stage = data.get("stage", "")
                        message = data.get("message", "")
                        progress = data.get("progress", 0)
                        progress_stages.append(stage)
                        print(f"  [{stage}] {message} ({progress:.0%})")

                    elif msg_type == "result":
                        result_received = True
                        segments = data.get("segments", [])
                        full_text = data.get("full_text", "")
                        elapsed_total = time.time() - start_time
                        print(f"\n[OK] ASR Sonuc alindi! ({elapsed_total:.1f}s)")
                        print(f"  Segment sayisi: {len(segments)}")
                        print(f"  Toplam metin uzunlugu: {len(full_text)} karakter")
                        if segments:
                            print(f"  Ilk segment: {segments[0].get('text', '')[:100]}...")
                            speakers = set(s.get("speaker_label", "") for s in segments)
                            print(f"  Konusmacilar: {speakers}")
                        break

                    elif msg_type == "error":
                        error_received = True
                        error_msg = data.get("message", "Bilinmeyen hata")
                        print(f"\n[HATA] WS Error: {error_msg}")
                        break

                    else:
                        print(f"  [?] Bilinmeyen mesaj tipi: {msg_type}")

                except asyncio.TimeoutError:
                    print(f"  [..] Bekleniyor... ({elapsed:.0f}s gecti)")

    except websockets.exceptions.ConnectionClosed as e:
        print(f"[HATA] WebSocket baglanti kapandi: code={e.code}, reason={e.reason}")
        if not result_received:
            error_received = True
            error_msg = f"WS closed unexpectedly: {e.code}"
    except Exception as e:
        print(f"[HATA] WebSocket hatasi: {e}")
        error_received = True
        error_msg = str(e)

    print(f"\n  Sonuc: result={'ALINDI' if result_received else 'ALINMADI'}, "
          f"error={'VAR: ' + error_msg if error_received else 'YOK'}")
    print(f"  Progress asamalari: {progress_stages}")
    return result_received


async def test_session_status(session_id: int) -> str:
    """Check session status after ASR processing."""
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.get(
            f"/api/v1/sessions/{session_id}",
            headers={"Authorization": f"Bearer {TOKEN}"}
        )
        resp.raise_for_status()
        session = resp.json()
        status = session.get("status", "?")
        segments = session.get("segments", [])
        print(f"\n[OK] Session durumu: {status}, segment sayisi: {len(segments)}")
        return status


async def test_ai_report(session_id: int) -> bool:
    """Test AI report generation via REST API."""
    print(f"\n--- AI Rapor Olusturma Test (session {session_id}) ---")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=600.0) as client:
        print(f"[..] AI rapor olusturuluyor (NER -> RAG -> LLM)...")
        start_time = time.time()

        resp = await client.post(
            "/api/v1/reports",
            json={"session_id": session_id, "method": "ai_generated"},
            headers={"Authorization": f"Bearer {TOKEN}"}
        )

        elapsed = time.time() - start_time

        if resp.status_code not in (200, 201):
            print(f"[HATA] HTTP {resp.status_code}: {resp.text[:300]}")
            return False

        report = resp.json()
        print(f"[OK] AI Rapor olusturuldu! ({elapsed:.1f}s)")
        print(f"  Report ID: {report.get('id')}")
        print(f"  Method: {report.get('method')}")

        # Parse content to check sections
        content = report.get("content", "{}")
        try:
            if isinstance(content, str):
                sections = json.loads(content)
            else:
                sections = content
        except json.JSONDecodeError:
            print(f"  [UYARI] Content JSON parse edilemedi")
            sections = {}

        if isinstance(sections, dict) and "sections" in sections:
            section_list = sections["sections"]
            print(f"  Bolum sayisi: {len(section_list)}")
            for sec in section_list:
                title = sec.get("title", "?")
                conf = sec.get("confidence", "?")
                content_text = sec.get("content", "")
                warnings = sec.get("warnings", [])
                preview = content_text[:80].replace("\n", " ") + "..." if len(content_text) > 80 else content_text
                warn_str = f" UYARI: {warnings}" if warnings else ""
                print(f"    [{conf:>6}] {title}: {preview}{warn_str}")
        else:
            print(f"  Content anahtarlari: {list(sections.keys()) if isinstance(sections, dict) else type(sections)}")

        return True


async def test_health():
    """Check backend health."""
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.get("/api/v1/health")
        resp.raise_for_status()
        h = resp.json()
        print(f"[OK] Backend saglik durumu:")
        print(f"  GPU: {h.get('gpu_name', 'N/A')} ({h.get('gpu_memory_used_mb', 0):.0f}/{h.get('gpu_memory_total_mb', 0):.0f} MB)")
        print(f"  Ollama: {h.get('ollama_status', '?')}, Model: {h.get('ollama_model_loaded', '?')}")
        print(f"  RAG docs: {h.get('rag_doc_count', 0)}")
        print(f"  ASR ready: {h.get('asr_pipeline_ready', '?')}")


async def main():
    print("=" * 60)
    print("  E2E Pipeline Test: Session -> ASR -> AI Report")
    print("=" * 60)

    # 1. Health check
    print("\n--- Saglik Kontrolu ---")
    await test_health()

    # 2. Login
    print("\n--- Giris ---")
    await login()

    # 3. Create session
    print("\n--- Session Olusturma ---")
    session_id = await create_session()

    # 4. WebSocket audio + ASR
    asr_ok = await test_ws_audio(session_id)

    if not asr_ok:
        print("\n[HATA] ASR basarisiz, AI rapor testi atlanacak")
        sys.exit(1)

    # 5. Check session status
    status = await test_session_status(session_id)
    if status != "AWAITING_REVIEW":
        print(f"[UYARI] Session durumu AWAITING_REVIEW olmali, ama: {status}")

    # 6. AI Report generation
    report_ok = await test_ai_report(session_id)

    # Summary
    print("\n" + "=" * 60)
    print("  SONUC OZETI")
    print("=" * 60)
    print(f"  Session ID: {session_id}")
    print(f"  ASR Processing: {'BASARILI' if asr_ok else 'BASARISIZ'}")
    print(f"  AI Report: {'BASARILI' if report_ok else 'BASARISIZ'}")
    print(f"  Genel: {'BASARILI' if (asr_ok and report_ok) else 'BASARISIZ'}")
    print("=" * 60)

    sys.exit(0 if (asr_ok and report_ok) else 1)


if __name__ == "__main__":
    asyncio.run(main())
