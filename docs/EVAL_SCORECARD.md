# EVAL SCORECARD

Hasil menjalankan `app/eval/run_batch.py` di gold set `superstore` (20 pertanyaan).
Angka di dokumen ini dibaca langsung dari tabel `scorecards` di `backend/analyst.db`,
bukan diketik ulang dari layar.

**Tanggal run:** 1 Agustus 2026
**Gold set:** [`backend/app/eval/gold_set/superstore.json`](../backend/app/eval/gold_set/superstore.json) (20 pertanyaan, 5 kategori)
**Dataset:** `datasets/superstore.csv` (9.994 baris, 2014-2017)
**Sandbox:** subprocess (`USE_DOCKER=false`). Docker tidak tersedia di mesin run.

> ### Baca ini dulu sebelum percaya angkanya
>
> Run ini **TIDAK memakai model yang dikonfigurasi di repo** (`gemini-2.0-flash`).
> Kuota harian free tier untuk model itu sudah habis waktu eval dijalankan, begitu juga
> `gemini-2.0-flash-lite`, `gemini-2.5-flash`, dan `gemini-2.5-pro`. Satu-satunya model yang
> masih punya kuota untuk menyelesaikan 20 pertanyaan adalah **`gemini-flash-lite-latest`**,
> yaitu tier paling ringan.
>
> Artinya: **angka di bawah adalah batas bawah, bukan performa sistem yang sebenarnya.**
> Bukti pendukungnya ada di bagian [Perbandingan antar model](#perbandingan-antar-model):
> di pertanyaan yang sempat kesentuh, model yang lebih kuat menjawab benar 9 dari 9,
> sementara model lite ini cuma 2 dari 5 di pertanyaan yang sama.
>
> Rerun dengan `gemini-2.0-flash` masih **BELUM DIJALANKAN**. Perintahnya ada di
> [Cara menjalankan ulang](#cara-menjalankan-ulang).

---

## Ringkasan

Model yang dipakai: `gemini-flash-lite-latest` (fallback, lihat catatan di atas).

| Metrik | Nilai |
|---|---|
| Akurasi vs gold | **0,350** (7 dari 20 tepat, 0 separuh, 13 salah) |
| Rata-rata tool call per pertanyaan (tool-efficiency) | **2,55** |
| Hallucination flag rate | **65,0%** (13 dari 20) |
| Biaya per query | **tidak terinstrumentasi** (lihat [Yang tidak terukur](#yang-tidak-terukur)) |

Metrik tambahan yang ikut kehitung: verification accuracy rata-rata **0,600**.

**Cara baca hallucination flag.** Grader menandai satu pertanyaan sebagai halusinasi kalau
correctness di bawah 0,5 **dan** confidence label agent masih HIGH atau MEDIUM. Jadi ini bukan
sekadar "jawabannya salah", tapi "salah sambil pede". Angka 65% berarti gerbang confidence gagal
menangkap mayoritas kesalahan model lite ini. Ini temuan yang tidak enak tapi nyata, dan justru
sejalan dengan premis di README: verifikasi yang memakai penalaran yang sama tidak menangkap
error yang dilahirkan penalaran itu.

## Per kategori

| Kategori | n | Akurasi | Hallucination flag |
|---|---|---|---|
| descriptive | 4 | 0,50 | 2/4 |
| diagnostic | 6 | 0,50 | 3/6 |
| predictive | 4 | 0,00 | 4/4 |
| statistical | 4 | 0,50 | 2/4 |
| edge_case | 2 | 0,00 | 2/2 |

Dua kategori jatuh total. **predictive** (0,00) semuanya soal agregasi per tahun, tren YoY, dan
CAGR, yang butuh parsing tanggal dengan format eksplisit. **edge_case** (0,00) termasuk q019, si
pertanyaan jebakan soal data 2013 yang memang tidak ada di dataset. Agent tetap menjawab dengan
percaya diri alih-alih mengaku datanya di luar rentang, persis kegagalan yang mau diuji soal itu.

## Per pertanyaan

| ID | Kategori | Correctness | Tool calls | Halluc flag |
|---|---|---|---|---|
| q001 | descriptive | 0,0 | 2 | YA |
| q002 | descriptive | 0,0 | 2 | YA |
| q003 | descriptive | 1,0 | 2 | - |
| q004 | descriptive | 1,0 | 2 | - |
| q005 | diagnostic | 0,0 | 2 | YA |
| q006 | diagnostic | 0,0 | 2 | YA |
| q007 | diagnostic | 1,0 | 3 | - |
| q008 | diagnostic | 0,0 | 2 | YA |
| q009 | diagnostic | 1,0 | 2 | - |
| q010 | diagnostic | 1,0 | 2 | - |
| q011 | predictive | 0,0 | 3 | YA |
| q012 | predictive | 0,0 | 2 | YA |
| q013 | predictive | 0,0 | 2 | YA |
| q014 | predictive | 0,0 | 2 | YA |
| q015 | statistical | 1,0 | 5 | - |
| q016 | statistical | 0,0 | 6 | YA |
| q017 | statistical | 1,0 | 3 | - |
| q018 | statistical | 0,0 | 2 | YA |
| q019 | edge_case | 0,0 | 3 | YA |
| q020 | edge_case | 0,0 | 2 | YA |

## Perbandingan antar model

Tiga run dicoba di hari yang sama. Dua run pertama mati di tengah jalan karena kuota harian habis,
jadi cuma pertanyaan awal yang sempat benar-benar dieksekusi. Baris "dieksekusi" di bawah hanya
menghitung pertanyaan dengan `tool_calls > 0`, yaitu yang agent-nya beneran jalan, bukan yang
langsung gagal karena kuota.

| Model | Pertanyaan dieksekusi | Akurasi di yang dieksekusi | Catatan |
|---|---|---|---|
| `gemini-2.0-flash` (konfigurasi repo) | 0 dari 20 | tidak ada | Kuota harian habis sebelum eval dimulai |
| `gemini-2.5-flash-lite` | 4 dari 20 | 1,00 (4/4) | Kuota habis di q005 |
| `gemini-2.5-flash` | 5 dari 20 | 1,00 (5/5) | Kuota habis di q006 |
| `gemini-flash-lite-latest` | **20 dari 20** | **0,35 (7/20)** | Run lengkap, jadi sumber tabel utama |

Di lima pertanyaan yang sama (q001 sampai q005), `gemini-2.5-flash` benar 5 dari 5 sementara
`gemini-flash-lite-latest` cuma benar 2 dari 5. Pertanyaan q001 dan q002 adalah penjumlahan kolom
paling sederhana di seluruh gold set, dan model lite tetap salah di keduanya. Ini memperkuat
kesimpulan bahwa angka 0,350 di atas lebih banyak bercerita tentang model fallback-nya
daripada tentang arsitektur agent-nya.

Jangan kutip 0,350 sebagai "akurasi VERDICT ANALYST" sebelum ada run dengan model produksi.

## Run kedua, 2 Agustus 2026

Batch yang sama dijalankan ulang sehari kemudian. Alasannya bukan mengejar angka yang lebih
bagus, melainkan mengisi tabel `run_history`: `python -m app.eval.export_calibration` gagal
dengan "run_history KOSONG" karena `save_run()` baru ikut dipanggil `run_batch.py` setelah
perubahan durable-state. Scorecard menyimpan skor, bukan teks jawaban, dan kalibrasi grader
butuh teksnya.

Perintah persis:

```powershell
cd backend
$env:USE_DOCKER='false'; $env:GEMINI_MODEL='gemini-flash-lite-latest'
.\.venv\Scripts\python.exe -m app.eval.run_batch
```

`gemini-2.0-flash` dicoba lebih dulu dan tetap kena 429 sampai lima kali retry habis, jadi run
ini memakai model lite yang sama dengan run pertama.

| Metrik | Run 1 Agu | Run 2 Agu |
|---|---|---|
| Avg correctness | 0,350 | **0,300** (6 dari 20) |
| Hallucination rate | 65,0% | **70,0%** |
| Avg tool calls | 2,55 | **2,3** |
| Avg time-to-insight | tidak terukur (selalu 0) | **27,8 detik** (durasi kini beneran diukur) |
| Total cost | $0,0000 (tidak terinstrumentasi) | $0,0000 (tidak terinstrumentasi) |

Selisih 0,350 versus 0,300 datang dari variasi antar-run pada model yang sama, bukan dari
perubahan kode agent. Itu sekaligus pengingat bahwa n=20 terlalu kecil untuk membedakan
selisih sekecil itu.

Yang berubah beneran: `avg_time_to_insight` sekarang terisi 27,8 detik, sebelumnya selalu nol.
Itu efek perbaikan `duration_ms` di `react_loop.py` yang dijaga
`tests/test_agent_rules.py::test_duration_ms_is_measured_on_success_path`.

**Tabel per pertanyaan dan per kategori di atas masih menggambarkan run 1 Agustus,** tidak
ditimpa. Hasil run kedua tersimpan di `reports/calibration_sample.csv` (20 baris, satu baris per
pertanyaan, lengkap dengan teks jawaban agent) dan dipakai sebagai bahan kalibrasi grader di
[`EVAL_CALIBRATION.md`](EVAL_CALIBRATION.md).

## Yang tidak terukur

Tiga hal di harness ini belum terinstrumentasi, jadi kolomnya tidak diisi angka:

1. **Biaya per query.** Field `cost_usd` ada di skema `Scorecard`, `AnalysisResult`, dan tabel DB,
   tapi tidak pernah ada satu baris kode pun yang mengisinya. Nilainya selalu default `0.0`,
   dan agregat `total_cost_usd` otomatis ikut `$0.0000`. Angka nol itu artinya "tidak diukur",
   bukan "gratis". Mengisi kolom ini butuh akuntansi token dari response Gemini
   (`usage_metadata`) dikali harga per token, dan itu belum ada.
2. **Time-to-insight.** `build_analysis_bundle()` dipanggil di `react_loop.py` tanpa argumen
   `duration_ms`, jadi durasi selalu 0 di jalur sukses. Angka `time_to_insight` yang bukan nol
   di run ini justru hanya muncul di jalur ERROR, karena di situ durasinya dihitung oleh
   `run_batch.py` sendiri. Jadi metrik ini terbalik dan belum bisa dipakai.
3. **Jalur kausal.** Gold set `superstore` isinya deskriptif sampai statistical. Belum ada gold
   set kausal, jadi eval ini sama sekali tidak menyentuh `app/causal`. Jaminan untuk jalur kausal
   masih bertumpu pada test recover ground-truth di `backend/tests/test_causal_engines.py`
   dan `test_causal_router.py`, bukan pada scorecard ini.

## Cara menjalankan ulang

Prasyarat: `GEMINI_API_KEY` terisi di `.env` di root repo, dan model di `GEMINI_MODEL` masih
punya kuota harian.

Tabel `scorecards` harus ada dulu. Kalau `analyst.db` masih baru, `run_batch` akan ramai
melempar `no such table: scorecards` sebelum menyimpan hasil:

```bash
cd backend
python -c "from app.db.repository import init_db; init_db()"
```

Lalu jalankan batch penuh:

```bash
cd backend
USE_DOCKER=false python -m app.eval.run_batch
```

PowerShell:

```powershell
cd backend
.\.venv\Scripts\python.exe -c "from app.db.repository import init_db; init_db()"
$env:USE_DOCKER='false'; .\.venv\Scripts\python.exe -m app.eval.run_batch
```

Opsi yang berguna:

| Perintah | Gunanya |
|---|---|
| `python -m app.eval.run_batch --max-questions 3` | Smoke test cepat, hemat kuota |
| `python -m app.eval.run_batch --gold-dir path/ke/gold` | Pakai gold set lain |

Kalau Docker tersedia dan image `analyst-sandbox:latest` sudah ter-build, buang
`USE_DOCKER=false` supaya sandbox terisolasi penuh yang dipakai.

**Catatan kuota.** Free tier Gemini punya batas per menit dan per hari, dan batasnya terpisah
per model. Kalau muncul pesan "daily quota habis", ganti `GEMINI_MODEL` ke model lain atau tunggu
reset. Run 20 pertanyaan makan waktu sekitar 45 menit di free tier karena kena backoff rate limit.
