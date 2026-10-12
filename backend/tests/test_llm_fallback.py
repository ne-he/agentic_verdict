"""Rantai model Gemini di `make_gemini_generate`.

Kasus nyata 11 Okt 2026: Google mematikan `gemini-2.0-flash`, semua analisis di Space gagal
dengan 404 padahal `/health` tetap ok. Test ini menjaga dua hal: model yang dipensiunkan
(404) atau kehabisan kuota harian pindah ke cadangan, dan error lain tetap dilempar apa adanya.
Klien Gemini diganti fake, jadi tidak ada kuota yang terpakai.
"""

from __future__ import annotations

import pytest
from google import genai
from google.genai import errors

from app.agent import llm
from app.core import config


def _client_error(code: int, details: dict | None = None, cls: type = errors.ClientError) -> errors.APIError:
    # Konstruktor error beda-beda antar versi google-genai, jadi atributnya diisi langsung.
    err = cls.__new__(cls)
    Exception.__init__(err, f"{code} fake error")
    err.code = code
    err.details = details or {}
    return err


DAILY_QUOTA = {
    "error": {
        "details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]
    }
}


def _busy() -> errors.APIError:
    return _client_error(503, cls=errors.ServerError)


class _FakeModels:
    """Tiap model punya jawaban tetap, atau daftar jawaban yang dipakai berurutan per panggilan."""

    def __init__(self, behaviour: dict[str, object]) -> None:
        self.behaviour = behaviour
        self.calls: list[str] = []

    def generate_content(self, model: str, contents: str, config: object) -> object:
        self.calls.append(model)
        out = self.behaviour[model]
        if isinstance(out, list):
            out = out.pop(0)
        if isinstance(out, Exception):
            raise out
        return type("Resp", (), {"text": out})()


@pytest.fixture
def fake_gemini(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "model-a")
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "model-b, model-c,model-a")
    # Settings di-cache sebagai singleton, jadi dikosongkan supaya env di atas terbaca.
    monkeypatch.setattr(config, "_settings", None)
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)

    def install(behaviour: dict[str, object]) -> _FakeModels:
        models = _FakeModels(behaviour)
        monkeypatch.setattr(genai, "Client", lambda api_key: type("C", (), {"models": models})())
        return models

    return install


def test_model_chain_urut_tanpa_duplikat(fake_gemini) -> None:
    assert llm.model_chain() == ["model-a", "model-b", "model-c"]
    assert llm.model_chain("model-c") == ["model-c", "model-b", "model-a"]


def test_model_dipensiunkan_pindah_ke_cadangan(fake_gemini) -> None:
    models = fake_gemini({"model-a": _client_error(404), "model-b": '{"ok": true}', "model-c": "x"})
    assert llm.make_gemini_generate()("p") == '{"ok": true}'
    assert models.calls == ["model-a", "model-b"]


def test_kuota_harian_habis_pindah_ke_cadangan(fake_gemini) -> None:
    models = fake_gemini(
        {"model-a": _client_error(429, DAILY_QUOTA), "model-b": _client_error(404), "model-c": "jawab"}
    )
    assert llm.make_gemini_generate()("p") == "jawab"
    assert models.calls == ["model-a", "model-b", "model-c"]


def test_semua_model_dipensiunkan_tetap_gagal(fake_gemini) -> None:
    fake_gemini({m: _client_error(404) for m in ("model-a", "model-b", "model-c")})
    with pytest.raises(errors.ClientError):
        llm.make_gemini_generate()("p")


def test_error_lain_tidak_ditutupi(fake_gemini) -> None:
    models = fake_gemini({"model-a": _client_error(400), "model-b": "tidak boleh dipanggil", "model-c": "x"})
    with pytest.raises(errors.ClientError):
        llm.make_gemini_generate()("p")
    assert models.calls == ["model-a"]


def test_server_sibuk_sekali_dicoba_ulang_di_model_yang_sama(fake_gemini) -> None:
    models = fake_gemini({"model-a": [_busy(), "pulih"], "model-b": "x", "model-c": "x"})
    assert llm.make_gemini_generate()("p") == "pulih"
    assert models.calls == ["model-a", "model-a"]


def test_server_terus_sibuk_pindah_ke_cadangan(fake_gemini) -> None:
    models = fake_gemini({"model-a": [_busy(), _busy()], "model-b": "cadangan", "model-c": "x"})
    assert llm.make_gemini_generate()("p") == "cadangan"
    assert models.calls == ["model-a", "model-a", "model-b"]
