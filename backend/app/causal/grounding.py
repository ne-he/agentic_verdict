"""Number-grounding check (P1/D4): tiap angka dalam prosa jawaban kausal harus
bisa dilacak ke CausalResult. Mismatch → fallback ke template deterministik.

Heuristik pencocokan (pragmatis, di-test di test_number_grounding.py):
- Angka hasil di-expand ke varian: nilai asli, ×100 (persen), pembulatan 1–4 desimal.
- Angka prosa dinormalisasi (buang pemisah ribuan, %).
- Integer kecil (≤ 12) dianggap struktural (penomoran list, "2 arm", "95%" → ci_level)
  dan tidak menggagalkan grounding.
"""
from __future__ import annotations

import math
import re
from typing import Any

from app.causal.schemas import CausalResult

_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)*")
_STRUCTURAL_MAX = 12          # integer <= ini dianggap struktural
_REL_TOL = 0.005              # toleransi relatif pencocokan (0.5%)
_ABS_TOL = 1e-9


def _collect_numbers(obj: Any, out: set[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        if math.isfinite(float(obj)):
            out.add(float(obj))
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers(v, out)
        return
    if isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_numbers(v, out)


def result_numbers(result: CausalResult) -> set[float]:
    """Semua angka di CausalResult + varian persen & pembulatan."""
    base: set[float] = set()
    _collect_numbers(result.model_dump(), base)

    expanded: set[float] = set()
    for x in base:
        expanded.add(x)
        expanded.add(x * 100)  # 0.0198 sering ditulis "1.98%"
        for nd in (1, 2, 3, 4):
            expanded.add(round(x, nd))
            expanded.add(round(x * 100, nd))
    return expanded


def _parse_prose_number(token: str) -> float | None:
    """'1,234.5' / '1.234,5' / '1,98' → float. Ambigu? pilih interpretasi wajar."""
    t = token.strip()
    if "," in t and "." in t:
        # pemisah terakhir = desimal
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        # koma tunggal dengan <=2 digit setelahnya → desimal gaya ID; selain itu ribuan
        parts = t.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            t = t.replace(",", ".")
        else:
            t = t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def _matches(x: float, candidates: set[float]) -> bool:
    for c in candidates:
        if math.isclose(x, c, rel_tol=_REL_TOL, abs_tol=_ABS_TOL):
            return True
    return False


def check_grounding(prose: str, result: CausalResult) -> tuple[bool, list[str]]:
    """True kalau semua angka non-struktural di prosa ada di result.
    Return (grounded, ungrounded_tokens)."""
    candidates = result_numbers(result)
    ungrounded: list[str] = []
    for token in _NUM_RE.findall(prose):
        x = _parse_prose_number(token)
        if x is None:
            continue
        if float(x).is_integer() and abs(x) <= _STRUCTURAL_MAX:
            continue  # struktural: penomoran, "2 arm", dst.
        if not _matches(x, candidates):
            ungrounded.append(token)
    return (len(ungrounded) == 0, ungrounded)


_DECISION_LABEL = {
    "deploy": "✅ DEPLOY — bukti cukup",
    "deploy_with_caution": "⚠️ DEPLOY WITH CAUTION — signifikan, tapi ada asumsi yang perlu dimitigasi",
    "do_not_ship": "⛔ DO NOT SHIP",
    "inconclusive": "❓ INCONCLUSIVE — belum bisa disimpulkan",
}


def render_template(result: CausalResult) -> str:
    """Jawaban deterministik dari CausalResult — fallback saat narasi LLM gagal
    grounding (P1: lebih baik template jujur daripada prosa halu)."""
    lines: list[str] = []
    rd = result.router_decision
    lines.append(f"**Metode:** {rd.method.value} (router confidence {rd.confidence:.2f})")
    lines.append("**Kenapa metode ini:** " + " ".join(rd.reasons))

    if result.effect is not None:
        e = result.effect
        seg = (
            f"**Efek:** {e.point:+.4g} (CI {int(e.ci_level*100)}%: "
            f"[{e.ci_low:.4g}, {e.ci_high:.4g}])"
        )
        if e.relative_lift is not None:
            seg += f", lift relatif {e.relative_lift*100:.2f}%"
        if e.p_value is not None:
            seg += f", p-value {e.p_value:.3g}"
        seg += " — " + ("**signifikan**" if e.is_significant else "**tidak signifikan**")
        lines.append(seg)

    if result.power is not None:
        p = result.power
        pw = f"**Power:** n/arm = {p.observed_n_per_arm:,}"
        if p.mde_absolute is not None:
            pw += f", MDE ≈ {p.mde_absolute:.4g}"
        if p.required_n_per_arm is not None:
            pw += f", butuh ~{p.required_n_per_arm:,.0f}/arm untuk efek teramati"
        lines.append(pw)

    if result.assumptions:
        lines.append("**Asumsi:**")
        for a in result.assumptions:
            lines.append(f"- [{a.status.value.upper()}] {a.business_explanation}")

    if result.verdict is not None:
        lines.append(
            f"**Keputusan:** {_DECISION_LABEL.get(result.verdict.decision.value, result.verdict.decision.value)}. "
            f"{result.verdict.rationale}"
        )
    return "\n\n".join(lines)
