"""Helper Gemini bersama (dipakai planner & react loop).

Mengembalikan callable `generate(prompt) -> str` (mode JSON). Di-inject ke komponen agar
test bisa mengganti dengan fake (hemat kuota).
"""

from __future__ import annotations

import re
import time
from typing import Callable

from app.core.config import get_settings

GenerateFn = Callable[[str], str]

# Free tier Gemini = 5 request/menit. Retry otomatis saat 429 supaya loop tak crash.
_MAX_RETRIES = 5
_DEFAULT_BACKOFF = 20.0  # detik, kalau API tak kasih retryDelay
# 503 "high demand" biasanya sementara. Dua percobaan per model, lalu pindah ke cadangan.
_SERVER_RETRIES = 2


def _retry_delay_from_error(err: Exception) -> float:
    """Ambil detik tunggu dari pesan 429 (retryDelay) kalau ada."""
    m = re.search(r"retry in ([\d.]+)s|'retryDelay': '(\d+)s'", str(err))
    if m:
        return float(m.group(1) or m.group(2)) + 1.0
    return _DEFAULT_BACKOFF


def _is_daily_quota_exhausted(err: Exception) -> bool:
    """True kalau 429 karena daily quota habis (bukan per-minute).

    Deteksi via e.details (dict parsed dari response JSON) → quotaId 'PerDay'.
    Kalau daily quota habis, retry tidak akan membantu: fail-fast dengan pesan jelas.
    """
    details = getattr(err, "details", {}) or {}
    error_details = details.get("error", {}).get("details", []) if isinstance(details, dict) else []
    has_per_day = False
    has_per_minute = False
    for item in error_details:
        for violation in item.get("violations", []):
            quota_id = violation.get("quotaId", "")
            if "PerDay" in quota_id:
                has_per_day = True
            if "PerMinute" in quota_id:
                has_per_minute = True
    # Daily exhausted + tidak ada per-minute = murni daily limit, langsung stop.
    # Daily + per-minute bersamaan = retry boleh (per-minute akan reset).
    # Tapi kalau retryDelay > 120s, hampir pasti daily bukan per-minute.
    retry_delay = _retry_delay_from_error(err)
    return has_per_day and (not has_per_minute or retry_delay > 120)


def model_chain(primary: str | None = None) -> list[str]:
    """Model utama lalu cadangan dari GEMINI_FALLBACK_MODELS, urut dan tanpa duplikat."""
    settings = get_settings()
    names = [primary or settings.gemini_model, *settings.gemini_fallback_models.split(",")]
    chain: list[str] = []
    for name in (n.strip() for n in names):
        if name and name not in chain:
            chain.append(name)
    return chain


def make_gemini_generate(model: str | None = None) -> GenerateFn:
    """Bikin fungsi generate yang memanggil Gemini (JSON mode) dgn retry saat rate-limit.

    Kalau model sudah dipensiunkan Google (404), kuota hariannya habis, atau terus sibuk (5xx),
    panggilan pindah ke model berikutnya di `model_chain`. Tanpa ini demo publik mati total: 11 Okt 2026 semua
    analisis gagal karena `gemini-2.0-flash` sudah tidak tersedia.
    """
    settings = get_settings()
    models = model_chain(model)

    def generate(prompt: str) -> str:  # pragma: no cover - butuh API key
        from google import genai
        from google.genai import types
        from google.genai.errors import ClientError, ServerError

        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY belum di-set di .env")
        client = genai.Client(api_key=settings.gemini_api_key)
        config = types.GenerateContentConfig(
            response_mime_type="application/json", temperature=0
        )
        from requests.exceptions import ConnectionError as ReqConnectionError

        last_err: Exception | None = None
        for i, model_name in enumerate(models):
            next_model = models[i + 1] if i + 1 < len(models) else None
            for attempt in range(_MAX_RETRIES):
                try:
                    resp = client.models.generate_content(
                        model=model_name, contents=prompt, config=config
                    )
                    return resp.text or ""
                except ClientError as e:
                    # Attribute di google-genai SDK adalah `code`, bukan `status_code`
                    code = getattr(e, "code", None)
                    last_err = e
                    if code == 404 and next_model:
                        print(f"[llm] model '{model_name}' tidak tersedia (404), pindah ke '{next_model}'")
                        break
                    if code != 429:
                        raise
                    if _is_daily_quota_exhausted(e):
                        if next_model:
                            print(f"[llm] kuota harian '{model_name}' habis, pindah ke '{next_model}'")
                            break
                        raise RuntimeError(
                            f"Gemini daily quota habis untuk model '{model_name}' (model terakhir di rantai). "
                            "Ganti GEMINI_MODEL / GEMINI_FALLBACK_MODELS atau tunggu reset besok.\n"
                            "Cek kuota di: https://ai.dev/rate-limit"
                        ) from e
                    wait = _retry_delay_from_error(e)
                    print(f"[llm] rate-limit 429, tunggu {wait:.0f}s (percobaan {attempt + 1}/{_MAX_RETRIES})")
                    time.sleep(wait)
                except ServerError as e:
                    # 12 Okt 2026: run di Space berhenti di tengah jalan karena satu 503 dari Gemini.
                    last_err = e
                    code = getattr(e, "code", "5xx")
                    if next_model and attempt + 1 >= _SERVER_RETRIES:
                        print(f"[llm] '{model_name}' sibuk ({code}), pindah ke '{next_model}'")
                        break
                    wait = 3.0 * (attempt + 1)
                    print(f"[llm] server error {code}, retry {attempt + 1}/{_MAX_RETRIES} dalam {wait:.0f}s")
                    time.sleep(wait)
                except ReqConnectionError as e:
                    # Transient network error (RemoteDisconnected, connection reset, dsb)
                    last_err = e
                    wait = 5.0 * (attempt + 1)  # backoff bertahap: 5s, 10s, 15s...
                    print(f"[llm] connection error, retry {attempt + 1}/{_MAX_RETRIES} dalam {wait:.0f}s: {e}")
                    time.sleep(wait)
            else:
                # Retry habis tanpa pindah model: limit per menit atau koneksi terus gagal.
                raise RuntimeError(f"Gemini gagal setelah {_MAX_RETRIES}x retry") from last_err
        raise RuntimeError(f"Semua model Gemini gagal: {', '.join(models)}") from last_err

    return generate
