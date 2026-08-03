# Kalibrasi Grader: VERDICT ANALYST

*Dihasilkan `python -m app.eval.calibration_report --csv calibration_sample.csv` pada 2026-08-02.*

Yang diukur: seberapa sejalan grader otomatis (`app/eval/grader.py`) dengan penilaian manusia atas jawaban agent yang sama. Tanpa angka ini, eval harness cuma opini mesin.

## Status: MENUNGGU LABEL MANUSIA

CSV punya 20 baris, tapi belum ada satu pun kolom `human_label` yang terisi. Tidak ada angka agreement maupun kappa yang bisa dilaporkan.

<!-- BAGIAN MANUAL. Ditulis tangan, TIDAK dihasilkan calibration_report.py. Kalau kamu
     menjalankan script itu lagi dengan --out ke berkas ini, blok di bawah ikut ketimpa.
     Salin ulang setelah regenerate. -->

## Cara menyelesaikan kalibrasi ini

Langkah 1 dan 2 (ekspor jawaban dan bikin kerangka laporan) sudah dijalankan pada 2 Agustus 2026.
Yang tersisa cuma satu langkah, dan langkah itu memang harus dikerjakan manusia. Agent tidak boleh
mengisinya: label yang dikarang membuat seluruh angka agreement jadi teater.

### 1. Buka berkasnya

```
reports/calibration_sample.csv
```

Relatif terhadap root repo, bukan terhadap `backend/`. Isinya **20 baris**, satu baris per
pertanyaan gold set, hasil `python -m app.eval.run_batch` pada 2 Agustus 2026 memakai model
`gemini-flash-lite-latest`. Encoding `utf-8-sig`, jadi Excel membukanya tanpa teks berantakan.

### 2. Isi kolom `human_label`

Cuma kolom **`human_label`** yang wajib. Isi salah satu dari tiga nilai:

| Nilai | Artinya |
|---|---|
| `benar` | Jawaban agent menjawab pertanyaannya dan angkanya cocok dengan `gold_answer` |
| `partial` | Pendekatannya benar tapi angkanya meleset, atau menjawab sebagian saja |
| `salah` | Jawabannya keliru, atau menjawab pertanyaan yang berbeda |

Kolom `human_note` opsional. Isi kalau kamu tidak setuju dengan grader dan mau alasannya
tercatat, misalnya "grader baca angka pertama di kalimat, padahal angka jawabannya yang kedua".

Variasi ketikan yang tetap dikenali `normalize_label()`: `correct`, `true`, `b`, `1` untuk benar;
`wrong`, `false`, `s`, `0` untuk salah; `sebagian`, `benar sebagian`, `p`, `0.5` untuk partial.
Huruf besar-kecil bebas. Nilai di luar itu akan dilewati dan dilaporkan sebagai peringatan.

**Jangan isi kolom lain.** `auto_correctness` dan `auto_label` adalah penilaian grader yang
sedang diuji. Mengeditnya berarti mengubah pihak yang lagi dinilai.

### 3. Aturan yang bikin angkanya berarti

1. **Jangan urutkan atau filter berdasarkan skor grader dulu.** Labeli baris sesuai urutan
   aslinya di CSV. Kalau kamu cuma melabeli baris yang grader-nya sudah bilang benar, agreement
   yang keluar akan tinggi dan tidak mengukur apa pun.
2. **Kalau bisa, tutup dulu kolom `auto_correctness`, `auto_label`, dan `hallucination_flag`**
   sebelum menilai. Di Excel: sembunyikan kolom H, I, J, labeli sampai habis, baru tampilkan lagi.
   Melihat jawaban grader sebelum memutuskan itu jalan pintas ke agreement palsu.
3. **Labeli semua 20 baris, bukan sebagian.** Melewati baris yang membingungkan justru membuang
   kasus yang paling informatif.
4. **Bandingkan ke `gold_answer`, bukan ke perasaan.** Kolom `question` dan `gold_answer` ada di
   CSV persis untuk itu.

### 4. Regenerate laporannya

Dari dalam `backend/`:

```bash
cd backend
python -m app.eval.calibration_report --csv ../reports/calibration_sample.csv --out ../docs/EVAL_CALIBRATION.md
```

PowerShell:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.eval.calibration_report --csv ..\reports\calibration_sample.csv --out ..\docs\EVAL_CALIBRATION.md
```

Perhatikan: **tanpa** `--allow-empty`. Flag itu cuma dipakai untuk membuat berkas berstatus
menunggu seperti sekarang. Begitu ada label, jangan pakai lagi, biar script tetap galak kalau
CSV-nya ternyata masih kosong.

Setelah itu berkas ini akan berisi agreement rate, Cohen's kappa, breakdown per kategori,
matriks bingung, dan daftar run yang grader dan manusianya beda pendapat. Salin ulang bagian
manual ini ke bawahnya.

### 5. Kalau agreement-nya rendah, jangan diam-diam menyetel grader

Ini aturan keras dari brief. Tulis angka aslinya, lalu tulis di mana grader dan manusia paling
sering berbeda. Analisis ketidaksepakatan jauh lebih bernilai daripada angka agreement tinggi
yang didapat dengan cara mencurigakan.

## Berapa n yang tersedia, apa adanya

Brief aslinya menyebut 150 sampel. Angka itu tidak bisa dicapai dengan kondisi repo sekarang,
dan alasannya bukan malas:

- Gold set yang ada cuma satu, `superstore`, isinya **20 pertanyaan**
  (`backend/app/eval/gold_set/superstore.json`). Satu batch eval penuh menghasilkan tepat 20 baris.
- Menambah baris berarti menjalankan batch berkali-kali dengan pertanyaan yang sama persis, dan
  itu tidak menambah keragaman kasus, cuma menambah pengulangan. Kappa dari data seperti itu
  menyesatkan.
- Jalan yang benar menuju n lebih besar adalah memperluas gold set ke 2 sampai 3 dataset, yang
  memang sudah terdaftar sebagai item terpisah (brief 04, HIJAU 6).

Jadi **n maksimum yang realistis hari ini adalah 20**, dan laporan ini akan menyebut n=20, bukan
150. Dengan n=20, `calibration_report.py` otomatis menambahkan catatan bahwa sampelnya kecil dan
hasilnya harus dibaca sebagai arah, bukan kesimpulan. Itu memang harus tetap ada.

## Dugaan awal soal di mana grader akan meleset

Ini **dugaan, bukan hasil pengukuran**, dan sengaja ditulis sebelum ada label supaya tidak
terlihat seperti kesimpulan yang dicocokkan belakangan.

`_extract_first_number()` di `app/eval/grader.py` mengambil **angka pertama** yang muncul di
jawaban. Kalau agent menulis kalimat pembuka seperti "Dari total 9.994 baris transaksi, terdapat
1.871 yang merugi", yang dibandingkan ke gold adalah 9.994, bukan 1.871, sehingga jawaban yang
sebenarnya benar bisa dinilai salah. Baris q020 di CSV ini persis berbentuk begitu dan diberi
`auto_label=salah`.

Kalau setelah dilabeli ternyata pola ketidaksepakatannya memang menumpuk di "grader bilang salah,
manusia bilang benar", maka yang perlu diperbaiki adalah cara ekstraksi angkanya, bukan ambang
nilainya. Tapi itu baru boleh disimpulkan setelah ada labelnya.
