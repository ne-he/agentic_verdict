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


def _retry_delay_from_error(err: Exception) -> float:
    """Ambil detik tunggu dari pesan 429 (retryDelay) kalau ada."""
    m = re.search(r"retry in ([\d.]+)s|'retryDelay': '(\d+)s'", str(err))
    if m:
        return float(m.group(1) or m.group(2)) + 1.0
    return _DEFAULT_BACKOFF


def _is_daily_quota_exhausted(err: Exception) -> bool:
    """True kalau 429 karena daily quota habis (bukan per-minute).

    Deteksi via e.details (dict parsed dari response JSON) → quotaId 'PerDay'.
    Kalau daily quota habis, retry tidak akan membantu — fail-fast dengan pesan jelas.
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


def make_gemini_generate(model: str | None = None) -> GenerateFn:
    """Bikin fungsi generate yang memanggil Gemini (JSON mode) dgn retry saat rate-limit."""
    settings = get_settings()
    model_name = model or settings.gemini_model

    def generate(prompt: str) -> str:  # pragma: no cover - butuh API key
        from google import genai
        from google.genai import types
        from google.genai.errors import ClientError

        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY belum di-set di .env")
        client = genai.Client(api_key=settings.gemini_api_key)
        config = types.GenerateContentConfig(
            response_mime_type="application/json", temperature=0
        )
        from requests.exceptions import ConnectionError as ReqConnectionError

        last_err: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = client.models.generate_content(
                    model=model_name, contents=prompt, config=config
                )
                return resp.text or ""
            except ClientError as e:
                # Attribute di google-genai SDK adalah `code`, bukan `status_code`
                if getattr(e, "code", None) != 429:
                    raise
                last_err = e
                if _is_daily_quota_exhausted(e):
                    raise RuntimeError(
                        f"Gemini daily quota habis untuk model '{model_name}'. "
                        "Ganti GEMINI_MODEL di .env ke model lain atau tunggu reset besok.\n"
                        "Cek kuota di: https://ai.dev/rate-limit"
                    ) from e
                wait = _retry_delay_from_error(e)
                print(f"[llm] rate-limit 429, tunggu {wait:.0f}s (percobaan {attempt + 1}/{_MAX_RETRIES})")
                time.sleep(wait)
            except ReqConnectionError as e:
                # Transient network error (RemoteDisconnected, connection reset, dsb)
                last_err = e
                wait = 5.0 * (attempt + 1)  # backoff bertahap: 5s, 10s, 15s...
                print(f"[llm] connection error, retry {attempt + 1}/{_MAX_RETRIES} dalam {wait:.0f}s: {e}")
                time.sleep(wait)
        raise RuntimeError(f"Gemini gagal setelah {_MAX_RETRIES}x retry") from last_err

    return generate
