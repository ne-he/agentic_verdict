"""
Translator: diagnostik teknis → kalimat bahasa bisnis. (Port dari VERDICT.)

Ini deterministik (bukan LLM) — template per asumsi. LLM hanya menarasikan
laporan akhir, bukan menjelaskan asumsi (jaga konsistensi & auditability).
"""
from __future__ import annotations


def explain(name: str, problem: bool, ctx: dict) -> str:
    if name == "sample_ratio":
        counts = ctx.get("counts", {})
        if problem:
            return (
                f"⚠️ Alokasi sampel meleset dari desain ({counts}). Ini biasanya bug "
                "pipeline assignment, bukan efek nyata — hasil tidak bisa dipercaya sampai diperbaiki."
            )
        return f"Alokasi sampel sehat ({counts}); tidak ada tanda bias mekanis."

    if name == "statistical_power":
        mde = ctx.get("mde_absolute")
        if mde is None:
            return "Daya uji tidak bisa dihitung — periksa ukuran sampel & varians."
        if problem:
            return (
                f"⚠️ Sampel belum cukup: uji ini baru bisa mendeteksi efek ≥ ~{mde:.3g} "
                "(absolut), lebih besar dari efek yang teramati. 'Tidak signifikan' di "
                "sini BUKAN berarti 'tidak ada efek' — tambah sampel dulu."
            )
        return (
            f"Dengan jumlah sampel sekarang, uji ini mampu mendeteksi efek sekecil "
            f"~{mde:.3g} (absolut). Efek di bawah itu mungkin terlewat."
        )

    # TODO(M3): overlap, positivity, e_value, balance, sutva, pre_period_fit
    return name
