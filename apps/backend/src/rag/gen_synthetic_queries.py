"""Generate synthetic doctor-speech queries via Claude Haiku.

Used to enrich the eval set with realistic ASR-style transcripts (e.g.
'hasta 45 yaşında erkek, 3 gündür ateş halsizlik öksürük diyor, baktım
boğazı kırmızı'). Output is a JSON list of {query_id, query_text, scenario}.

This is the only place we send synthetic generation requests to the API.
We never send real anamnez text in this script — only abstract scenario
prompts. PHI risk: zero.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_OUT_PATH = _PROJECT_ROOT / "apps" / "backend" / "src" / "rag" / "eval_queries_synthetic.json"

_SCENARIOS: list[dict[str, str]] = [
    {"id": "uri_acute", "desc": "akut üst solunum yolu enfeksiyonu, genç erişkin"},
    {"id": "uri_chronic", "desc": "tekrarlayan boğaz ağrısı, 1 hafta+, sigara öyküsü"},
    {"id": "gastrit_acute", "desc": "akut gastrit, mide bulantısı + epigastrik ağrı"},
    {"id": "gastrit_chronic", "desc": "kronik gastrit + reflü, NSAID kullanımı"},
    {"id": "dm_kontrol", "desc": "DM kontrol vizitesi, kan şekeri yüksek, halsizlik"},
    {"id": "dm_yeni", "desc": "yeni teşhis edilmiş DM şüphesi, polidipsi+poliuri"},
    {"id": "ht_kontrol", "desc": "HT kontrol, baş ağrısı + tansiyon yüksekliği"},
    {"id": "ht_kriz", "desc": "hipertansif acil, baş dönmesi + bulantı + 180/110 TA"},
    {"id": "anemi_dem", "desc": "demir eksikliği anemisi, kadın hasta, yorgunluk + saç dökülmesi"},
    {"id": "anemi_b12", "desc": "B12 eksikliği şüphesi, yaşlı hasta, parestezi + halsizlik"},
    {"id": "tiroid_hipo", "desc": "hipotiroidi, soğuk intoleransı + kilo alımı"},
    {"id": "tiroid_hiper", "desc": "hipertiroidi, çarpıntı + kilo kaybı + sıcak intoleransı"},
    {"id": "akut_karin", "desc": "akut karın, sağ alt kadran ağrısı, defans"},
    {"id": "ishal_akut", "desc": "akut gastroenterit, sulu ishal + bulantı"},
    {"id": "uti_kadin", "desc": "kadın hastada idrar yolu enfeksiyonu, dizüri + sıkışma"},
    {"id": "vertigo", "desc": "baş dönmesi, periferik vertigo şüphesi"},
    {"id": "kbb_sinüzit", "desc": "akut sinüzit, yüz ağrısı + nazal akıntı"},
    {"id": "kas_iskelet", "desc": "lomber bel ağrısı, kronik, sedanter işçi"},
    {"id": "alerjik_rinit", "desc": "alerjik rinit, mevsimsel"},
    {"id": "anksiyete", "desc": "yaygın anksiyete + somatik şikayetler"},
    {"id": "obezite_metabolik", "desc": "obezite + metabolik sendrom kontrolü"},
    {"id": "kolesterol", "desc": "hiperlipidemi takibi, statin kullanımı"},
    {"id": "asthma_kronik", "desc": "kronik astım, hışıltı + nefes darlığı"},
    {"id": "kopd_alev", "desc": "KOAH alevlenmesi, sigara öyküsü"},
    {"id": "konstipasyon", "desc": "kronik konstipasyon, yaşlı hasta"},
    {"id": "gut", "desc": "gut atağı, başparmak şişme + ağrı"},
    {"id": "egzama", "desc": "atopik egzama, kaşıntı"},
    {"id": "uyku_problem", "desc": "uyku problemi + halsizlik + sabah yorgun uyanma"},
    {"id": "kabızlık_diyare", "desc": "değişken bağırsak alışkanlığı, IBS şüphesi"},
    {"id": "vitamin_d", "desc": "vitamin D eksikliği, kemik ağrıları"},
    {"id": "menopause", "desc": "perimenopozal kadın, sıcak basması + ruh hali değişimi"},
    {"id": "soguk_alg", "desc": "viral soğuk algınlığı, çocuk teması"},
    {"id": "akciger_pnomoni", "desc": "alt solunum yolu enfeksiyonu şüphesi, ateş + öksürük + balgam"},
    {"id": "tetanoz_yaralanma", "desc": "yaralanma sonrası tetanoz aşı sorgusu"},
    {"id": "checkup_yillik", "desc": "yıllık genel kontrol, asemptomatik"},
    {"id": "kalp_carpinti", "desc": "çarpıntı, atipik göğüs ağrısı"},
    {"id": "renal_takip", "desc": "kronik böbrek hastalığı takibi, kreatinin yüksek"},
    {"id": "tiroid_nodul", "desc": "tiroid nodülü tespit, asemptomatik"},
    {"id": "kilo_kayb", "desc": "açıklanamayan kilo kaybı, malignite şüphesi"},
    {"id": "pedi_atesli", "desc": "pediatrik ateşli hasta, viral şüphesi"},
    {"id": "kabızlık_yaşlı", "desc": "yaşlı hastada kronik kabızlık + abdominal rahatsızlık"},
    {"id": "ödem_alt", "desc": "alt ekstremite ödemi, kalp yetmezliği şüphesi"},
    {"id": "depresyon_somatik", "desc": "depresyon ile ilişkili somatik şikayetler"},
    {"id": "halsizlik_b12_demir", "desc": "yorgunluk + halsizlik, çoklu vitamin eksikliği şüphesi"},
    {"id": "akut_gut", "desc": "monoartiküler akut başlangıç + kırmızı şişme"},
    {"id": "fmf", "desc": "ailevi akdeniz ateşi şüphesi, periyodik karın ağrısı + ateş"},
    {"id": "gerd", "desc": "gastroözofageal reflü, retrosternal yanma"},
    {"id": "ülser_dyspepsia", "desc": "peptik ülser şüphesi, açlık ağrısı + bulantı"},
    {"id": "h_pylori", "desc": "H. pylori taraması, kronik gastrik şikayetler"},
    {"id": "ishal_kronik", "desc": "kronik ishal + kilo kaybı, IBD şüphesi"},
]

SYSTEM_PROMPT = """Sen Türk dahiliye polikliniğinde çalışan bir doktorsun. Bir hasta seninle konuşurken sen muayene odasında ne söylersin onu yazıyorsun. ASR (konuşma tanıma) ile transkribe edilmiş bir konuşma gibi olmalı:
- Doğal Türkçe, doktor diline yakın ama günlük
- Hastanın yakınmaları + öykü süresi + muayene bulguları geçsin
- 1-3 cümle, tıpkı doktorun hızlıca özetlediği gibi
- Tıbbi terim kullan ama abartma; halk dili karışık olabilir
- HİÇBİR isim, TC, telefon, e-mail, adres yazma
- Sayısal değerler için sadece genel ifade (yüksek, normal, vb.) — spesifik tarih/yaş yok"""

USER_TEMPLATE = """Senaryo: {desc}

Bu senaryoya uygun, doktorun konsültasyon sırasında konuşmasının ASR transkripsiyonu olabilecek 1 örnek üret. Sadece transkript metnini döndür, açıklama yapma."""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="claude-haiku-4-5-20251001")
    parser.add_argument("--output", default=str(_OUT_PATH))
    parser.add_argument("--max-tokens", type=int, default=300)
    parser.add_argument("--limit", type=int, default=None, help="Use first N scenarios only")
    args = parser.parse_args()

    api_key = os.getenv("ASR_LLM__ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ASR_LLM__ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1

    client = anthropic.Anthropic(api_key=api_key)
    scenarios = _SCENARIOS[: args.limit] if args.limit else _SCENARIOS

    print(f"[gen] model={args.model}  scenarios={len(scenarios)}", flush=True)

    results: list[dict] = []
    total_in_tokens = 0
    total_out_tokens = 0

    for i, sc in enumerate(scenarios):
        prompt = USER_TEMPLATE.format(desc=sc["desc"])
        try:
            resp = client.messages.create(
                model=args.model,
                max_tokens=args.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
            results.append({
                "query_id": f"syn_{i:03d}_{sc['id']}",
                "scenario": sc["desc"],
                "query_text": text,
            })
            total_in_tokens += resp.usage.input_tokens
            total_out_tokens += resp.usage.output_tokens
            print(f"  [{i+1:>2d}/{len(scenarios)}] {sc['id']}: {text[:80]}{'...' if len(text)>80 else ''}", flush=True)
        except Exception as e:
            print(f"  [{i+1}] FAILED: {e}", file=sys.stderr)

    Path(args.output).write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Cost: Haiku 4.5 = $1/MTok input, $5/MTok output
    cost = total_in_tokens / 1_000_000 + total_out_tokens / 1_000_000 * 5
    print(f"\n[gen] wrote {len(results)} queries to {args.output}", flush=True)
    print(f"[gen] tokens: in={total_in_tokens:,}  out={total_out_tokens:,}  cost~${cost:.3f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
