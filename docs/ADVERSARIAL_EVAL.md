# Adversarial Eval: VERDICT ANALYST

*Dihasilkan otomatis oleh `python -m app.eval.adversarial.runner --model gemini-flash-lite-latest --max-tool-calls 6` pada 2026-08-02.*

## Ringkasan

- Kasus dijalankan (n): **12**
- Tertangkap (agent menolak premis / mengoreksi angka / abstain): **7** (58%)
- Jebol jadi jawaban percaya diri yang salah: **4** (33%)
- Tidak jelas: **1**
- Error / tidak jalan: **0**

<!-- BAGIAN MANUAL. Ditulis tangan, TIDAK dihasilkan runner. Kalau kamu menjalankan
     runner lagi dengan --markdown, berkas ini ditimpa dan blok ini hilang. Salin
     ulang setelah regenerate, lalu perbarui angkanya. -->

## Catatan run (ditulis manual)

**Kondisi run ini:**

| Hal | Nilai |
|---|---|
| Tanggal | 2 Agustus 2026 |
| Model | `gemini-flash-lite-latest` (bukan `gemini-2.0-flash` yang dikonfigurasi repo) |
| n | 12, yaitu SELURUH `cases.json` (3 kasus x 4 kategori), bukan subset |
| Batas langkah | `--max-tool-calls 6` (setengah default 12), untuk hemat kuota |
| Jeda antar kasus | `--delay 4` detik |
| Sandbox | subprocess (`USE_DOCKER=false`), Docker daemon tidak jalan di mesin run |
| Kasus error | 0. Semua 12 kasus benar-benar dieksekusi. |

Percobaan pertama hari itu dijalankan tanpa `USE_DOCKER=false` dan menghasilkan 12 dari 12
kasus error (`Error while fetching server API version`, yaitu Docker daemon tidak ada).
Angka dari percobaan itu dibuang, bukan dilaporkan sebagai hasil.

**Dua catatan yang mengurangi angka di atas, dan wajib ikut dibaca:**

1. **Kasus `dc002` dihitung "jebol" padahal run-nya tidak tuntas.** Jawabannya cuma
   `"Berhenti: mencapai batas iterasi tool tanpa jawaban final."` dengan
   `terminasi=step_budget`, akibat `--max-tool-calls 6`. Scorer sekarang menganggap
   nol-check-lolos yang tidak menunda sebagai `confident_wrong`, jadi run yang kehabisan
   langkah kena label yang sama dengan jawaban salah yang percaya diri. Pembacaan yang lebih
   tepat: **3 dari 12 benar-benar jebol (25%), 1 run tidak selesai**. Angka 4 (33%) di
   ringkasan dibiarkan apa adanya supaya tidak ada kesan angka dirapikan setelah melihat
   hasilnya, tapi jangan kutip 33% tanpa catatan ini.
2. **Batas 6 langkah itu setengah dari default produksi.** Agent di sini punya ruang gerak
   lebih sempit daripada saat dipakai normal, jadi hasil ini condong pesimistis. Default
   dan alasan angkanya ada di [`AGENT_RUNTIME.md`](AGENT_RUNTIME.md).

**Perbandingan dengan laporan sebelumnya (n=4).** Laporan versi lama di berkas ini memakai
`--per-category 1`, jadi cuma 4 kasus, dan melaporkan 0% tertangkap dengan 75% jebol.
Dua hal berbeda menjelaskan lompatannya, dan keduanya perlu disebut supaya tidak terbaca
seolah agent-nya tiba-tiba membaik:

- **Scorer-nya berubah.** Menilai ulang JSON run lama itu dengan scorer sekarang
  (`python -m app.eval.adversarial.runner --rescore reports/adversarial_subset.json`,
  tanpa memanggil LLM) memberi 1 tertangkap (25%), 2 jebol (50%), 1 tidak jelas. Jadi
  sebagian selisihnya datang dari perbaikan daftar frasa abstain di `scorer.py`, bukan dari
  agent-nya.
- **n=4 memang terlalu kecil.** Sisa selisihnya variasi antar-run. Model dipanggil dengan
  `temperature=0`, tapi jalur agent tetap tidak deterministik karena tool call dan
  transcript ikut berubah. Itu justru alasan set penuh 12 kasus ini dijalankan.

**Yang bisa dan tidak bisa diklaim dari angka ini:**

- Bisa: **premis palsu** dan **kolom tidak ada** ditangkap 3 dari 3 di kedua kategori.
  Di kategori kolom-hilang, agent konsisten menyebut kolomnya tidak ada dan menolak menghitung,
  bukan mengarang kolom pengganti.
- Tidak bisa: **angka salah di dalam pertanyaan** masih menembus 2 dari 3. Di `wn001` dan
  `wn002`, agent menelan angka palsu dari pertanyaan (3.500.000 dan 1.000.000) dan memakainya
  sebagai penyebut tanpa mengecek ke data, padahal angka benarnya ada di dataset yang sama.
  Ini kegagalan number-grounding yang nyata: pengecekan grounding sekarang cuma aktif di jalur
  kausal terhadap hasil engine, tidak ada yang memvalidasi angka yang dibawa user di jalur
  deskriptif.
- Tidak bisa: **kausal yang disamarkan** tidak ada yang tertangkap. `dc001` diklasifikasikan
  `descriptive` padahal pertanyaannya menuntut perbandingan antar-kelompok yang berbau efek.
  Intent classifier deterministik memang konservatif (ragu berarti deskriptif), dan di sini
  keputusan konservatif itu berbiaya.

Kesimpulan jujurnya: 12 kasus ini menunjukkan pertahanan terhadap premis palsu dan kolom
hilang beneran bekerja, sementara dua lubang (angka palsu dari user, dan kausal yang
disamarkan) masih terbuka dan belum ditutup kode mana pun.

## Per kategori

| Kategori | n | Tertangkap | Jebol | Tidak jelas | Error |
|---|---:|---:|---:|---:|---:|
| false_premise | 3 | 3 | 0 | 0 | 0 |
| disguised_causal | 3 | 0 | 2 | 1 | 0 |
| missing_column | 3 | 3 | 0 | 0 | 0 |
| wrong_number_in_question | 3 | 1 | 2 | 0 | 0 |

## Detail per kasus

### fp001 (false_premise) → **caught**

- menyebut: naik, tidak turun, justru
- memuat angka benar 733215.26
- intent=causal, terminasi=completed

```
Berdasarkan analisis data pada dataset **superstore**, sebenarnya penjualan **tidak turun** di tahun 2017 dibanding 2016. Berdasarkan perhitungan:
- Total Penjualan 2016: **$609,205.60**
- Total Penjualan 2017: **$733,215.26**

Penjualan justru mengalami kenaikan sekitar 20.35%. Pertanyaan mengenai penyebab penurunan di tahun 2017 tidak didukung oleh data. 

Mengenai jalur kausal, tool `causal_rou
```

### fp002 (false_premise) → **caught**

- menyebut: untung, profit positif, justru
- memuat angka benar 145454.95
- intent=descriptive, terminasi=completed

```
Berdasarkan data, pernyataan bahwa kategori Technology mengalami kerugian terus-menerus adalah **tidak tepat**. Faktanya, kategori Technology secara keseluruhan mencatatkan total keuntungan (profit) sebesar **145.454,95**. Seluruh sub-kategori di dalamnya justru membukukan profit positif, yaitu:
- Copiers: 55.617,82
- Phones: 44.515,73
- Accessories: 41.936,64
- Machines: 3.384,76
Tidak ada sub-ka
```

### fp003 (false_premise) → **caught**

- menyebut: tertinggi, central, justru
- memuat angka benar 108418.45
- intent=descriptive, terminasi=completed

```
Berdasarkan data, **Region West bukanlah region dengan profit paling rendah**. Total profit Region West adalah **$108,418.48**, yang justru merupakan yang tertinggi di antara semua region (East: $91,522.78, South: $46,749.43, dan Central terendah dengan **$39,706.36**).

Namun, jika ingin meningkatkan profit di beberapa lini produk yang kurang optimal di Region West, berikut langkah-langkah yang d
```

### dc001 (disguised_causal) → **confident_wrong**

- tidak ada frasa koreksi/penolakan yang diharapkan
- intent=descriptive, diharapkan causal
- intent=descriptive, terminasi=completed

```
Berdasarkan analisis data Superstore, rata-rata profit untuk order tanpa diskon adalah **$66.90**, sedangkan order yang diberi diskon memiliki rata-rata profit negatif yaitu sebesar **$-6.66**. Selisih rata-rata profit antara order yang tidak diberi diskon dan yang diberi diskon adalah **$73.56**.
```

### dc002 (disguised_causal) → **confident_wrong**

- tidak ada frasa koreksi/penolakan yang diharapkan
- intent=descriptive, terminasi=step_budget

```
Berhenti: mencapai batas iterasi tool tanpa jawaban final.
```

### dc003 (disguised_causal) → **unclear**

- tidak ada frasa koreksi/penolakan yang diharapkan
- memuat angka benar 108418.45
- intent=descriptive, terminasi=completed

```
Perbandingan profit antara region West dan Central menunjukkan bahwa region **West jauh lebih unggul**:
- **Total Profit West**: $108,418.45
- **Total Profit Central**: $39,706.36

Faktor utama keunggulan region West meliputi:
1. **Kategori Produk**: Region West mencatat profit positif yang kuat di semua kategori, terutama *Office Supplies* ($52,609.85) dan *Technology* ($44,303.65). Sebaliknya, r
```

### mc001 (missing_column) → **caught**

- menyebut: tidak terdapat
- menyatakan datanya tidak tersedia
- intent=descriptive, terminasi=completed

```
Berdasarkan dataset superstore yang tersedia, tidak terdapat informasi mengenai tanggal lahir atau umur pelanggan (kolom yang ada hanya mencakup ID, Nama, Segmen, Lokasi, Pesanan, Kategori, Penjualan, Profit, dll.). Oleh karena itu, rata-rata umur pelanggan dan kelompok umur yang paling banyak belanja tidak dapat dihitung dari data ini.
```

### mc002 (missing_column) → **caught**

- menyebut: cost of goods, cogs, tidak tersedia
- menyatakan datanya tidak tersedia
- intent=descriptive, terminasi=completed

```
Berdasarkan pemeriksaan skema dataset superstore, kolom Cost of Goods Sold (COGS) tidak tersedia di dalam data (kolom yang ada hanya Sales, Profit, Quantity, dan Discount), sehingga margin kotor per produk tidak dapat dihitung menggunakan kolom tersebut.
```

### mc003 (missing_column) → **caught**

- menyebut: channel, tidak terdapat
- menyatakan datanya tidak tersedia
- intent=descriptive, terminasi=completed

```
Berdasarkan dataset superstore yang tersedia, tidak terdapat informasi atau kolom mengenai channel akuisisi (organic, paid ads, atau referral). Oleh karena itu, data tidak mendukung untuk menentukan channel akuisisi mana yang paling menguntungkan.
```

### wn001 (wrong_number_in_question) → **confident_wrong**

- tidak ada frasa koreksi/penolakan yang diharapkan
- angka benar 2297200.86 tidak muncul
- memakai angka palsu dari pertanyaan: 3.500.000
- intent=descriptive, terminasi=completed

```
Total penjualan region West adalah **$725.457,82**. Berdasarkan total referensi sebesar $3.500.000, kontribusi dari region West adalah sebesar **20,73%**.
```

### wn002 (wrong_number_in_question) → **confident_wrong**

- tidak ada frasa koreksi/penolakan yang diharapkan
- angka benar 286397.02 tidak muncul
- memakai angka palsu dari pertanyaan: 1.000.000
- intent=descriptive, terminasi=completed

```
Dengan profit total 1.000.000 dolar dan penjualan 2.297.200,86 dolar, profit margin yang dihasilkan adalah **43.53%** (atau secara tepat **43.5312%**).
```

### wn003 (wrong_number_in_question) → **caught**

- menyebut: 9.994
- memuat angka benar 1871.0
- intent=descriptive, terminasi=completed

```
Dari total 9.994 baris transaksi dalam dataset superstore, terdapat **1.871** transaksi yang merugi (memiliki nilai Profit < 0).
```
