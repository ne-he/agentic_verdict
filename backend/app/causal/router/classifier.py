"""
★ ROUTER — otak pemilih metode. (Port dari VERDICT; spec: VERDICT_BLUEPRINT.md §2.)

Mengikuti P3: SELALU mengembalikan reasons[] + assumptions_required[], dan
allow_override=True. Default ke metode lebih konservatif kalau ragu.
Router MENGUSULKAN; user boleh override.
"""
from __future__ import annotations

import pandas as pd

from app.causal.router.diagnostics import (
    max_abs_smd,
    sample_ratio_mismatch,
    standardized_mean_diff,
)
from app.causal.schemas import (
    ColumnRoles,
    DeclaredType,
    Method,
    RouterDecision,
)

SMD_BALANCE_THRESHOLD = 0.10   # |SMD| < 0.1 = seimbang
CATE_MIN_N_PER_ARM = 1000      # ambang tawarkan CATE


def route(
    df: pd.DataFrame,
    roles: ColumnRoles,
    declared_type: DeclaredType = DeclaredType.AUTO,
    expected_ratio: float | None = None,
) -> RouterDecision:
    # STEP 0 — outcome wajib
    if roles.outcome not in df.columns:
        raise ValueError("kolom outcome tidak ada — minta mapping ulang")

    # STEP 1 — tidak ada treatment → time-series atau deskriptif
    if not roles.treatment:
        if roles.timestamp and roles.intervention_date:
            return RouterDecision(
                method=Method.TIMESERIES,
                confidence=0.7,
                reasons=[
                    "Tidak ada grup kontrol, tapi ada deret waktu + tanggal intervensi.",
                    "Efek diestimasi via synthetic control (CausalImpact).",
                ],
                assumptions_required=[
                    "Pola pra-intervensi stabil & bisa diekstrapolasi.",
                    "Tidak ada intervensi lain bersamaan di tanggal yang sama.",
                    "Prediktor/kovariat tidak ikut terpengaruh treatment.",
                ],
            )
        return RouterDecision(
            method=Method.DESCRIPTIVE,
            confidence=0.3,
            reasons=["Tidak ada treatment maupun tanggal intervensi — klaim kausal tidak bisa ditegakkan."],
            assumptions_required=["Hanya analisis deskriptif; jangan tafsirkan sebagai kausal."],
        )

    # STEP 1.5 — jumlah arm harus tepat 2 (multi-arm belum didukung)
    n_arms = int(df[roles.treatment].dropna().nunique())
    if n_arms < 2:
        raise ValueError("kolom treatment hanya punya 1 nilai — tidak ada pembanding")
    if n_arms > 2:
        raise ValueError(
            f"terdeteksi {n_arms} arm — versi ini baru mendukung 2 arm "
            "(kontrol vs treatment); filter data ke 2 arm dulu"
        )

    # STEP 2 — diagnostik
    smd = standardized_mean_diff(df, roles.treatment, roles.covariates)
    srm = sample_ratio_mismatch(df, roles.treatment, expected_ratio)
    worst_smd = max_abs_smd(smd)
    diagnostics = {"smd": smd, "max_abs_smd": worst_smd, "srm": srm}

    # balance hanya boleh diklaim kalau ADA kovariat yang dicek (smd tidak kosong)
    balanced = bool(smd) and worst_smd < SMD_BALANCE_THRESHOLD
    n_per_arm = int(df[roles.treatment].value_counts().min())
    cate_addon = (len(roles.covariates) > 0 and n_per_arm >= CATE_MIN_N_PER_ARM)

    # STEP 3 — putuskan kebersihan
    if declared_type == DeclaredType.OBSERVATIONAL:
        return _observational(diagnostics, cate_addon, reason="User mendeklarasikan data observasional.")

    if declared_type == DeclaredType.RANDOMIZED or balanced or not smd:
        reasons = []
        confidence = 0.9
        if declared_type == DeclaredType.RANDOMIZED:
            reasons.append("User mendeklarasikan eksperimen acak (A/B).")
        if balanced:
            reasons.append(f"Kovariat seimbang antar arm (max |SMD| = {worst_smd:.3f} < {SMD_BALANCE_THRESHOLD}).")
        assumptions = [
            "Penugasan benar-benar acak (tidak ada self-selection).",
            "SUTVA: tidak ada interferensi antar unit.",
        ]
        if not smd and declared_type != DeclaredType.RANDOMIZED:
            # tidak ada kovariat → keacakan TIDAK terverifikasi dari data
            confidence = 0.5
            reasons.append(
                "Tidak ada kovariat untuk uji balance — keacakan assignment tidak bisa "
                "diverifikasi dari data; A/B dipilih karena tanpa kovariat metode "
                "adjustment (observasional) tidak mungkin."
            )
            assumptions.append(
                "Sertakan kovariat pra-eksperimen agar balance bisa diverifikasi."
            )
        if srm["srm_detected"]:
            reasons.append("⚠️ SRM TERDETEKSI — rasio sampel meleset dari desain; hasil harus ditandai berisiko.")
            assumptions.append("PERIKSA pipeline assignment: SRM = bias mekanis, bukan efek nyata.")
            confidence = min(confidence, 0.5)
        return RouterDecision(
            method=Method.AB_TEST,
            confidence=confidence,
            reasons=reasons,
            assumptions_required=assumptions,
            diagnostics=diagnostics,
        )

    # imbalance → observasional (konservatif, P3)
    return _observational(
        diagnostics,
        cate_addon,
        reason=f"Kovariat tidak seimbang (max |SMD| = {worst_smd:.3f} ≥ {SMD_BALANCE_THRESHOLD}) — indikasi confounding.",
    )


def _observational(diagnostics: dict, cate_addon: bool, reason: str) -> RouterDecision:
    reasons = [reason, "Pakai DoWhy (graph + identifikasi) + propensity matching + refutation."]
    if cate_addon:
        reasons.append("N cukup besar → CATE (efek heterogen) ditawarkan sebagai add-on.")
    return RouterDecision(
        method=Method.OBSERVATIONAL,
        confidence=0.6,
        reasons=reasons,
        assumptions_required=[
            "Unconfoundedness: semua confounder kunci terobservasi & dimasukkan.",
            "Overlap/positivity: tiap unit punya peluang masuk kedua kondisi.",
            "SUTVA: tidak ada interferensi antar unit.",
        ],
        diagnostics=diagnostics,
    )
