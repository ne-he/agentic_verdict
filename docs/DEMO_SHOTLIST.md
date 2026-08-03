# DEMO SHOTLIST: GIF 20 detik

Skenario rekaman untuk GIF yang dipasang di atas lipatan README. Tujuannya satu:
dalam 20 detik penonton harus paham bahwa sistem ini **tidak percaya jawaban LLM begitu saja**.

Yang dijual bukan "agent bisa jawab", tapi "agent dicek dari luar".

---

## Sebelum merekam

| Hal | Nilai |
|---|---|
| Ukuran window | 1280 x 800, browser fullscreen tanpa bookmark bar |
| Zoom browser | 100% (biar teks tetap kebaca setelah dikompres jadi GIF) |
| Dataset | `ab_marketing` (ground-truth ada di `datasets/ab_marketing.meta.json`) |
| Backend | sudah warm. Kirim 1 pertanyaan dummy dulu supaya cold start tidak ikut kerekam |
| Tab awal | Executive Summary |
| Bersihkan | tab lain, notifikasi OS, dan history panel |

Pertanyaan yang diketik: **"Apakah kampanye ini menaikkan konversi?"**

Alasan pakai pertanyaan ini: dia memicu jalur kausal, jadi satu rekaman bisa menampilkan
intent detection, role mapping gate, dan angka dari engine deterministik sekaligus.

Target durasi total: **20 detik**. Kalau meleset, potong di bagian mengetik (bisa dipercepat 2x),
jangan potong bagian hasil.

---

## Adegan per detik

| Detik | Yang terjadi di layar | Kenapa penting |
|---|---|---|
| 0.0 - 2.0 | Halaman utama, dataset `ab_marketing` sudah terpilih. Kursor klik input pertanyaan. | Set konteks. Jangan lama-lama. |
| 2.0 - 5.0 | Ketik "Apakah kampanye ini menaikkan konversi?" lalu Enter. Percepat 2x kalau perlu. | Menunjukkan input bahasa manusia biasa. |
| 5.0 - 7.5 | Execution trace jalan: badge intent berubah jadi **CAUSAL**. | Ini momen "agent tahu sendiri ini pertanyaan sebab-akibat". |
| 7.5 - 11.0 | **RoleMappingModal** muncul. Treatment=`variant`, Outcome=`converted`, Covariates=`pre_engagement`. Kursor klik konfirmasi. | Human gate. Analisis kausal tidak jalan diam-diam. |
| 11.0 - 13.5 | Tab **Causal** terbuka. Method router tampil dengan `reasons[]` dan "Asumsi yang ditanggung". | Router transparan, bukan kotak hitam. |
| 13.5 - 16.5 | Scroll pelan ke hasil: efek sekitar **+0.02 absolut** dengan CI, assumption badges hijau, SRM lolos. | Angka ini cocok dengan ground truth di file meta. Inilah bukti recover. |
| 16.5 - 18.5 | Keputusan **DEPLOY** muncul, plus breakdown confidence kausal (router, assumption health, verification agreement, tool success). | Confidence dihitung, bukan ditebak. |
| 18.5 - 20.0 | Klik tab **Verification** sebentar, tahan frame di situ. Frame terakhir harus tab Verification. | Frame terakhir yang membekas = verifikasi, sesuai sudut README. |

---

## Take alternatif (kalau mau versi deskriptif)

Kalau ingin menonjolkan cross-check dua metode alih-alih jalur kausal, pakai dataset
`superstore` dan pertanyaan **"Berapa total penjualan keseluruhan?"**, lalu:

| Detik | Yang terjadi |
|---|---|
| 0 - 4 | Ketik pertanyaan, Enter. |
| 4 - 9 | Execution trace: `inspect_schema` lalu `write_and_execute`. |
| 9 - 13 | Tab **Code**: kode pandas yang ditulis agent sendiri kelihatan. |
| 13 - 18 | Tab **Verification**: pandas vs DuckDB SQL, dua angka, status cocok. |
| 18 - 20 | Tahan di badge confidence. |

Angka gold untuk pertanyaan ini ada di `backend/app/eval/gold_set/superstore.json` (q001),
jadi penonton yang iseng bisa memverifikasi sendiri.

---

## Teknis ekspor

- Rekam pakai ScreenToGif, LICEcap, atau Kap. Rekam sebagai video dulu, konversi belakangan.
- Frame rate 12-15 fps sudah cukup. GIF di atas 20 fps ukurannya meledak tanpa terasa lebih mulus.
- Target ukuran akhir **di bawah 8 MB**. GitHub masih mau render, dan README tidak berat dibuka.
- Lebar output 960 px. Turunkan ke 800 px kalau masih kegedean.
- Simpan ke `docs/demo.gif`, lalu ganti slot placeholder di README.
- Jangan pasang caption teks di dalam GIF. Konteksnya sudah ada di paragraf README di atasnya.

## Setelah GIF jadi

1. Taruh file di `docs/demo.gif`.
2. Di README, ganti blok `<!-- DEMO GIF: ... -->` dengan `![Demo VERDICT ANALYST](docs/demo.gif)`.
3. Cek tampilan render di GitHub, bukan cuma di preview editor lokal.
