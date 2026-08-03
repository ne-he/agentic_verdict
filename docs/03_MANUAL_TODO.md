# Kerjaan manual: dataset yang harus diunduh sendiri

Berkas ini dirujuk oleh `backend/app/core/datasets.py` (baris 6 dan 77). Sebelumnya
rujukan itu menggantung, jadi orang yang kena `FileNotFoundError` diarahkan ke dokumen
yang tidak ada.

## Kenapa ada dataset yang tidak ikut di repo

Katalog di `app/core/datasets.py` mendaftarkan 4 dataset. Dua di antaranya ikut repo,
dua lagi tidak karena lisensinya milik penyedia asli dan ukurannya tidak pantas masuk git.

Yang menentukan aktif atau tidak bukan katalog, tapi keberadaan berkas CSV-nya:

```python
def list_datasets() -> list[str]:
    """dataset_id yang AKTIF = terdaftar di katalog DAN file CSV-nya ada."""
    return [ds_id for ds_id, meta in DATASET_CATALOG.items() if _file_exists(meta)]
```

Jadi cukup taruh CSV-nya di `backend/datasets/` dengan nama yang benar, dan dataset itu
langsung muncul di playground. Tidak ada kode yang perlu diubah, tidak ada restart
konfigurasi, tidak ada migrasi.

## Status per dataset

| `dataset_id` | Nama berkas yang dicari | Ikut repo? |
|---|---|---|
| `superstore` | `superstore.csv` | Ya |
| `ab_marketing` | `ab_marketing.csv` plus `ab_marketing.meta.json` | Ya, sintetik, ground truth-nya ada di berkas `.meta.json` |
| `olist` | `ecommerce_olist.csv` | **Tidak. Unduh sendiri.** |
| `hr_attrition` | `hr_attrition.csv` | **Tidak. Unduh sendiri.** |

## Cara menambahkannya

1. Unduh dataset dari Kaggle:
   - Olist: cari "Brazilian E-Commerce Public Dataset by Olist". Sumbernya terpecah jadi
     beberapa tabel, jadi gabungkan dulu jadi satu CSV datar sebelum disimpan.
   - IBM HR Attrition: cari "IBM HR Analytics Employee Attrition & Performance". Sumbernya
     sudah satu berkas datar, tinggal ganti nama.
2. Simpan ke `backend/datasets/` dengan nama persis seperti kolom kedua tabel di atas.
   Nama yang meleset satu huruf berarti dataset tetap dianggap tidak ada.
3. Encoding yang diharapkan katalog: `utf-8` untuk keduanya. `superstore.csv` memakai
   `latin-1`, itu pengecualian dan sudah tercatat di katalog.
4. Jalankan backend, lalu cek `GET /datasets`. Dataset yang berhasil terpasang akan
   muncul di daftar.

## Kalau tidak diunduh

Tidak ada yang rusak. Playground jalan dengan `superstore` dan `ab_marketing` saja, dan
seluruh test suite lulus tanpa dua berkas ini. Gold set eval pun cuma memakai
`superstore`. Jadi ini pelebaran cakupan, bukan prasyarat.
