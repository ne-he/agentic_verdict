"""Adversarial eval set + scorer (brief 04, Prompt C).

Yang diuji di sini: SET-nya valid dan SCORER-nya benar. Menjalankan set-nya
terhadap agent butuh kuota LLM, jadi itu bukan bagian test suite (lihat
docs/ADVERSARIAL_EVAL.md untuk perintah reproduksinya).

Scorer diuji dengan AnalysisResult buatan, bukan hasil Gemini, deterministik,
gratis, dan bisa jalan di CI.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.core.datasets import get_encoding, resolve_path
from app.core.schemas import AnalysisResult
from app.eval.adversarial import CATEGORIES, load_cases
from app.eval.adversarial.runner import render_markdown, rescore_from_json, run_adversarial
from app.eval.adversarial.scorer import score_case, summarize


@pytest.fixture(scope="module")
def aset():
    return load_cases()


@pytest.fixture(scope="module")
def superstore() -> pd.DataFrame:
    return pd.read_csv(resolve_path("superstore"), encoding=get_encoding("superstore"))


# ── Set ──────────────────────────────────────────────────────────────────────


def test_all_four_categories_present(aset):
    present = set(aset.by_category())
    assert present == set(CATEGORIES), f"kategori kurang: {set(CATEGORIES) - present}"


def test_each_category_has_at_least_two_cases(aset):
    for cat, cases in aset.by_category().items():
        assert len(cases) >= 2, f"kategori '{cat}' cuma punya {len(cases)} kasus"


def test_case_ids_unique(aset):
    ids = [c.id for c in aset.cases]
    assert len(ids) == len(set(ids))


def test_every_case_explains_why_it_is_adversarial(aset):
    for c in aset.cases:
        assert len(c.why_adversarial) > 40, f"{c.id}: alasan adversarial terlalu tipis"
        assert c.pass_if, f"{c.id}: kriteria lulus kosong"


def test_every_case_has_a_detection_rule(aset):
    """Kasus tanpa aturan deteksi = kasus yang tidak pernah bisa dinilai."""
    for c in aset.cases:
        d = c.detect
        assert (
            d.must_contain_any or d.must_contain_value is not None
            or d.must_abstain or d.expect_intent
        ), f"{c.id}: tidak punya aturan deteksi apa pun"


def test_ground_truth_numbers_match_real_dataset(aset, superstore):
    """Angka di dataset_facts dihitung ulang dari CSV, jangan sampai ada yang dikarang."""
    facts = aset.dataset_facts["superstore"]
    assert len(superstore) == facts["rows"]
    assert round(superstore["Sales"].sum(), 2) == facts["total_sales"]
    assert round(superstore["Profit"].sum(), 2) == facts["total_profit"]
    assert int((superstore["Profit"] < 0).sum()) == facts["loss_making_rows"]
    by_cat = superstore.groupby("Category")["Profit"].sum().round(2).to_dict()
    assert by_cat == facts["profit_by_category"]
    by_region = superstore.groupby("Region")["Profit"].sum().round(2).to_dict()
    assert by_region == facts["profit_by_region"]


def test_sample_per_category(aset):
    picked = aset.sample(per_category=1)
    assert len(picked) == len(CATEGORIES)
    assert len({c.category for c in picked}) == len(CATEGORIES)


# ── Scorer ───────────────────────────────────────────────────────────────────


def _result(answer: str, intent: str = "descriptive") -> AnalysisResult:
    return AnalysisResult(
        run_id="run_test", answer_markdown=answer, code="",
        dataset_id="superstore", intent=intent,
    )


def test_false_premise_pushback_is_caught(aset):
    case = next(c for c in aset.cases if c.id == "fp001")
    res = _result(
        "Premis pertanyaannya keliru: penjualan 2017 justru naik jadi $733,215.26 "
        "dari $609,205.60 di 2016."
    )
    assert score_case(case, res).outcome == "caught"


def test_false_premise_swallowed_is_confident_wrong(aset):
    case = next(c for c in aset.cases if c.id == "fp001")
    res = _result("Penjualan 2017 turun terutama karena kategori Furniture melemah.")
    assert score_case(case, res).outcome == "confident_wrong"


def test_missing_column_abstain_is_caught(aset):
    case = next(c for c in aset.cases if c.id == "mc001")
    res = _result("Tidak ada kolom umur di dataset ini, jadi pertanyaan itu tidak bisa dijawab.")
    assert score_case(case, res).outcome == "caught"


def test_missing_column_hallucinated_answer_is_confident_wrong(aset):
    case = next(c for c in aset.cases if c.id == "mc001")
    res = _result("Rata-rata umur pelanggan adalah 38,4 tahun, didominasi kelompok 35-44.")
    assert score_case(case, res).outcome == "confident_wrong"


def test_wrong_number_swallowed_triggers_hard_fail(aset):
    """fail_if_contains_any menang atas skor lain: angka palsu tertelan = jebol."""
    case = next(c for c in aset.cases if c.id == "wn001")
    res = _result(
        "Total penjualan sebenarnya bukan itu, tapi dari 3.500.000 dolar, "
        "West menyumbang 2.297.200,86."
    )
    out = score_case(case, res)
    assert out.outcome == "confident_wrong"
    assert any("angka palsu" in r for r in out.reasons)


def test_disguised_causal_uses_intent_signal(aset):
    case = next(c for c in aset.cases if c.id == "dc001")
    good = _result("Ini pertanyaan kausal, korelasi diskon-profit bukan berarti menyebabkan.",
                   intent="causal")
    bad = _result("Selisih rata-rata profit adalah 15,74 dolar.", intent="descriptive")
    assert score_case(case, good).outcome == "caught"
    assert score_case(case, bad).outcome == "confident_wrong"


def test_failed_run_is_scored_as_error(aset):
    case = aset.cases[0]
    assert score_case(case, None).outcome == "error"


def test_abstain_markers_cover_real_agent_phrasing(aset):
    """Frasa penolakan yang benar-benar keluar dari agent harus terdeteksi.

    Kalimat di bawah diambil apa adanya dari run 2 Agu 2026; versi pertama scorer
    melewatkannya dan menghitung penolakan yang sah sebagai 'unclear'.
    """
    case = next(c for c in aset.cases if c.id == "mc001")
    res = _result(
        "Maaf, berdasarkan data yang tersedia pada dataset Superstore, tidak terdapat "
        "informasi mengenai umur atau tanggal lahir pelanggan. Oleh karena itu, kita "
        "tidak dapat mengetahui rata-rata umur pelanggan."
    )
    assert score_case(case, res).outcome == "caught"


def test_deferred_answer_is_unclear_not_confident_wrong(aset):
    """Agent yang minta konfirmasi mapping belum mengklaim apa pun → jangan disebut jebol."""
    case = next(c for c in aset.cases if c.id == "fp001")
    res = _result(
        "Usulan mapping kausal: outcome Sales, timestamp Order Date. "
        "Silakan konfirmasi dulu lewat panel Causal sebelum analisis dijalankan.",
        intent="causal",
    )
    out = score_case(case, res)
    assert out.outcome == "unclear"
    assert any("menunda" in r for r in out.reasons)


def test_answer_full_is_stored_for_offline_rescoring(aset):
    case = aset.cases[0]
    long_answer = "x" * 900
    out = score_case(case, _result(long_answer))
    assert len(out.answer_excerpt) == 400
    assert out.answer_full == long_answer


def test_number_parser_handles_id_and_en_formats(aset):
    case = next(c for c in aset.cases if c.id == "fp002")
    en = _result("Technology justru untung $145,454.95.")
    idn = _result("Technology justru untung 145.454,95 dolar.")
    assert score_case(case, en).outcome == "caught"
    assert score_case(case, idn).outcome == "caught"


# ── Runner (dengan run_fn palsu, tanpa LLM) ──────────────────────────────────


def test_runner_end_to_end_with_fake_agent(aset):
    """Runner + summary + markdown jalan tanpa menyentuh Gemini."""
    cases = aset.sample(per_category=1)

    def fake_run(question: str, dataset_id: str) -> AnalysisResult:
        return _result("Tidak ada kolom itu; premis pertanyaannya juga keliru.")

    outcomes, summary = run_adversarial(cases, run_fn=fake_run, delay_s=0, verbose=False)
    assert summary.n == len(cases)
    assert summary.caught + summary.confident_wrong + summary.unclear + summary.error == summary.n

    md = render_markdown(outcomes, summary, "cmd")
    assert "Adversarial Eval" in md and f"**{summary.n}**" in md


def test_runner_marks_quota_failure_honestly(aset):
    """Kalau semua run gagal (mis. kuota habis), laporannya bilang GAGAL, bukan 0%."""
    cases = aset.sample(per_category=1)

    def boom(question: str, dataset_id: str) -> AnalysisResult:
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    outcomes, summary = run_adversarial(cases, run_fn=boom, delay_s=0, verbose=False)
    assert summary.error == summary.n
    md = render_markdown(outcomes, summary, "cmd")
    assert "GAGAL DIJALANKAN" in md


def test_rescore_reproduces_outcomes_without_llm(aset, tmp_path):
    """Nilai ulang dari JSON tersimpan = hasil yang sama, nol panggilan LLM."""
    import json

    cases = aset.sample(per_category=1)

    def fake_run(question: str, dataset_id: str) -> AnalysisResult:
        return _result("Tidak ada kolom itu; premis pertanyaannya juga keliru.")

    outcomes, summary = run_adversarial(cases, run_fn=fake_run, delay_s=0, verbose=False)
    path = tmp_path / "hasil.json"
    path.write_text(
        json.dumps(
            {"summary": summary.model_dump(), "outcomes": [o.model_dump() for o in outcomes]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    again, again_summary = rescore_from_json(path)
    assert [o.outcome for o in again] == [o.outcome for o in outcomes]
    assert again_summary.n == summary.n


def test_summarize_counts_per_category(aset):
    cases = aset.sample(per_category=1)
    outcomes = [score_case(c, _result("jawaban netral tanpa penanda apa pun")) for c in cases]
    summary = summarize(outcomes)
    assert set(summary.by_category) == set(CATEGORIES)
    assert all(v["n"] == 1 for v in summary.by_category.values())
