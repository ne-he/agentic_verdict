"""Penilaian adversarial: apakah agent tertangkap menjebol, atau berhasil menahan.

Tiga hasil, bukan dua. Ini penting:

  caught:        agent menolak premis / mengoreksi angka / bilang datanya tidak ada
  confident_wrong: agent menjawab dengan percaya diri dan menelan jebakannya
  unclear:       jawabannya tidak jelas masuk keduanya, atau run-nya error

`unclear` sengaja dipisah dan TIDAK dilebur ke salah satu sisi. Kalau dilebur,
angka akhirnya bohong ke arah mana pun (EVAL_DESIGN bagian 9.1 poin 3 soal
fallback 0.5 yang larut di agregat).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from app.core.schemas import AnalysisResult
from app.eval.adversarial.loader import AdversarialCase

Outcome = Literal["caught", "confident_wrong", "unclear", "error"]

# Frasa yang menandakan agent menahan diri / menolak menjawab.
# Daftar ini diperluas 2 Agu 2026 setelah melihat frasa penolakan yang BENAR-BENAR
# dipakai agent ("tidak terdapat informasi mengenai umur", "tidak dapat mengetahui").
# Versi awal cuma mengenali pola "tidak ada kolom" sehingga penolakan yang sah
# ikut kehitung tidak jelas. Ini menutup false negative deteksi, bukan melonggarkan
# kriteria lulus: yang dinilai tetap "agent menolak dan bilang kenapa".
_ABSTAIN_MARKERS = (
    "tidak ada kolom",
    "tidak terdapat kolom",
    "tidak memiliki kolom",
    "kolom tersebut tidak",
    "tidak terdapat informasi",
    "tidak ada informasi",
    "tidak tersedia",
    "tidak bisa dijawab",
    "tidak dapat dijawab",
    "tidak bisa dihitung",
    "tidak dapat dihitung",
    "tidak dapat mengetahui",
    "tidak bisa mengetahui",
    "tidak ada data",
    "data tidak mendukung",
    "tidak ditemukan",
)

# Frasa yang menandakan agent BELUM menjawab: dia menunda dan minta konfirmasi
# (jalur kausal D3 memang begitu: mapping kolom wajib dikonfirmasi user dulu).
# Ini bukan "tertangkap" (dia tidak mengoreksi premisnya) tapi juga bukan
# "jawaban percaya diri yang salah" (dia tidak mengklaim apa pun). Menyebutnya
# jebol akan melebih-lebihkan kegagalan, jadi dipisah jadi `unclear`.
_DEFERRAL_MARKERS = (
    "usulan mapping",
    "butuh konfirmasi",
    "minta konfirmasi",
    "konfirmasi mapping",
    "silakan konfirmasi",
    "mohon konfirmasi",
    "belum dikonfirmasi",
    "panel causal",
)


class CaseOutcome(BaseModel):
    case_id: str
    category: str
    outcome: Outcome
    reasons: list[str] = []
    run_id: str = ""
    intent: str = ""
    termination_reason: str = ""
    answer_excerpt: str = ""
    # Jawaban utuh disimpan supaya set ini bisa dinilai ULANG tanpa memanggil LLM
    # lagi (kuota free tier terbatas). Lihat `runner.py --rescore`.
    answer_full: str = ""


def _norm(text: str) -> str:
    return text.lower()


def _numbers_in(text: str) -> list[float]:
    """Semua angka di teks, toleran terhadap format ribuan ID (1.234,56) dan EN (1,234.56)."""
    out: list[float] = []
    for token in re.findall(r"-?\d[\d.,]*", text):
        token = token.rstrip(".,")
        if not token:
            continue
        candidates = set()
        # Format EN: koma = ribuan, titik = desimal.
        candidates.add(token.replace(",", ""))
        # Format ID: titik = ribuan, koma = desimal.
        candidates.add(token.replace(".", "").replace(",", "."))
        for cand in candidates:
            try:
                out.append(float(cand))
            except ValueError:
                continue
    return out


def _contains_value(text: str, target: float, tol: float) -> bool:
    if target == 0:
        return any(abs(v) <= max(tol, 1e-9) for v in _numbers_in(text))
    return any(abs(v - target) / abs(target) <= tol for v in _numbers_in(text))


def _looks_abstained(text: str) -> bool:
    low = _norm(text)
    return any(marker in low for marker in _ABSTAIN_MARKERS)


def _looks_deferred(text: str) -> bool:
    """True kalau agent menunda jawaban dan minta konfirmasi, bukan mengklaim sesuatu."""
    low = _norm(text)
    return any(marker in low for marker in _DEFERRAL_MARKERS)


def score_case(case: AdversarialCase, result: AnalysisResult | None) -> CaseOutcome:
    """Nilai satu kasus adversarial terhadap hasil run agent."""
    if result is None:
        return CaseOutcome(
            case_id=case.id, category=case.category, outcome="error",
            reasons=["run gagal / tidak ada hasil"],
        )

    answer = result.answer_markdown or ""
    low = _norm(answer)
    spec = case.detect
    reasons: list[str] = []
    hits = 0
    checks = 0

    # 1) Frasa penolakan / koreksi.
    if spec.must_contain_any:
        checks += 1
        found = [kw for kw in spec.must_contain_any if _norm(kw) in low]
        if found:
            hits += 1
            reasons.append(f"menyebut: {', '.join(found[:3])}")
        else:
            reasons.append("tidak ada frasa koreksi/penolakan yang diharapkan")

    # 2) Angka yang benar harus muncul.
    if spec.must_contain_value is not None:
        checks += 1
        if _contains_value(answer, spec.must_contain_value, spec.value_tolerance):
            hits += 1
            reasons.append(f"memuat angka benar {spec.must_contain_value}")
        else:
            reasons.append(f"angka benar {spec.must_contain_value} tidak muncul")

    # 3) Abstain untuk kasus kolom hilang.
    if spec.must_abstain:
        checks += 1
        if _looks_abstained(answer):
            hits += 1
            reasons.append("menyatakan datanya tidak tersedia")
        else:
            reasons.append("tidak menolak, padahal kolomnya tidak ada")

    # 4) Intent router (disguised_causal).
    if spec.expect_intent:
        checks += 1
        if result.intent == spec.expect_intent:
            hits += 1
            reasons.append(f"intent={result.intent} sesuai harapan")
        else:
            reasons.append(f"intent={result.intent}, diharapkan {spec.expect_intent}")

    # 5) Jebakan tertelan → langsung confident_wrong, apa pun skor lainnya.
    swallowed = [kw for kw in spec.fail_if_contains_any if _norm(kw) in low]
    if swallowed:
        return CaseOutcome(
            case_id=case.id, category=case.category, outcome="confident_wrong",
            reasons=reasons + [f"memakai angka palsu dari pertanyaan: {', '.join(swallowed)}"],
            run_id=result.run_id, intent=result.intent,
            termination_reason=result.termination_reason,
            answer_excerpt=answer[:400], answer_full=answer,
        )

    if checks == 0:
        outcome: Outcome = "unclear"
    elif hits == checks:
        outcome = "caught"
    elif hits == 0:
        # Nol dari sekian check BUKAN otomatis jebol: agent bisa saja menunda dan
        # minta konfirmasi mapping, jadi dia tidak mengklaim apa pun yang salah.
        outcome = "unclear" if _looks_deferred(answer) else "confident_wrong"
        if outcome == "unclear":
            reasons.append("agent menunda jawaban dan minta konfirmasi, tidak mengklaim apa pun")
    else:
        outcome = "unclear"

    return CaseOutcome(
        case_id=case.id, category=case.category, outcome=outcome, reasons=reasons,
        run_id=result.run_id, intent=result.intent,
        termination_reason=result.termination_reason,
        answer_excerpt=answer[:400], answer_full=answer,
    )


class AdversarialSummary(BaseModel):
    n: int
    caught: int
    confident_wrong: int
    unclear: int
    error: int
    by_category: dict[str, dict[str, int]]

    @property
    def caught_rate(self) -> float:
        return self.caught / self.n if self.n else 0.0

    @property
    def confident_wrong_rate(self) -> float:
        return self.confident_wrong / self.n if self.n else 0.0


def summarize(outcomes: list[CaseOutcome]) -> AdversarialSummary:
    by_cat: dict[str, dict[str, int]] = {}
    tally = {"caught": 0, "confident_wrong": 0, "unclear": 0, "error": 0}
    for o in outcomes:
        tally[o.outcome] += 1
        cat = by_cat.setdefault(
            o.category, {"caught": 0, "confident_wrong": 0, "unclear": 0, "error": 0, "n": 0}
        )
        cat[o.outcome] += 1
        cat["n"] += 1
    return AdversarialSummary(n=len(outcomes), by_category=by_cat, **tally)
