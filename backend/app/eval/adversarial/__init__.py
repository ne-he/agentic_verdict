"""Adversarial eval set: pilar P7.

Number-grounding check adalah klaim terkuat projek ini. Klaim itu cuma terbukti
kalau diuji dengan kasus yang sengaja dirancang menjebolnya. Gold set biasa hanya
berisi pertanyaan yang BISA dijawab, jadi cuma mengukur separuh sistem
(lihat brief/EVAL_DESIGN.md bagian 7).

Empat kategori:
  false_premise:            premis pertanyaannya salah menurut data
  disguised_causal:         pertanyaan kausal yang dikemas seperti deskriptif
  missing_column:           jawabannya butuh kolom yang tidak ada di dataset
  wrong_number_in_question: pertanyaannya sendiri sudah menyebut angka yang salah

Kriteria lulus untuk sebagian besar kasus BUKAN "jawabannya benar", melainkan
"agent menolak premisnya / mengoreksi angkanya / bilang datanya tidak ada".
"""

from app.eval.adversarial.loader import (
    AdversarialCase,
    AdversarialSet,
    load_cases,
    CATEGORIES,
)

__all__ = ["AdversarialCase", "AdversarialSet", "load_cases", "CATEGORIES"]
