# Agent Runtime: batas, alasan berhenti, dan durable state

Dokumen ini dirujuk langsung dari `backend/app/agent/react_loop.py` (baris 11 dan 49).
Isinya menjelaskan tiga hal yang menentukan perilaku runtime agent: **berapa jauh dia
boleh jalan**, **kenapa dia berhenti**, dan **apa yang tersimpan kalau prosesnya mati**.

Semua angka dan nama kolom di sini dibaca dari kode, bukan dikarang. Kalau kamu mengubah
nilainya di kode, ubah juga di sini. `tests/test_agent_rules.py::test_defaults_are_documented_values`
mengunci ketiga default supaya tidak berubah diam-diam.

Berkas yang relevan:

| Berkas | Isi |
|---|---|
| `backend/app/agent/react_loop.py` | loop ReAct, konstanta budget, penentuan alasan terminasi |
| `backend/app/agent/termination.py` | kosakata alasan terminasi + label bahasa manusia |
| `backend/app/agent/tools/__init__.py` | subset tool per intent (aturan produksi #1) |
| `backend/app/agent/checkpoint.py` | kontrak checkpointer + implementasi SQLite |
| `backend/app/db/models.py` | tabel `run_states` dan `run_steps` |
| `backend/app/api/routes.py` | endpoint resume dan daftar run yang bisa di-resume |

---

## 1. Budget per run (aturan produksi #2)

Tiga batas berjalan bersamaan di `_execute()`. Yang tersentuh duluan, itu yang menghentikan run.

| Konstanta | Nilai | Dicek di mana |
|---|---|---|
| `DEFAULT_MAX_TOOL_CALLS` | `12` | kondisi `while` loop utama |
| `DEFAULT_MAX_TOKENS` | `200_000` | awal tiap iterasi, sebelum panggil model |
| `DEFAULT_TIMEOUT_S` | `300.0` detik | awal tiap iterasi, wall-clock sejak `_execute` mulai |

### Kenapa 12 langkah

Dari [`EVAL_SCORECARD.md`](EVAL_SCORECARD.md), run gold set 20 pertanyaan pada 1 Agustus 2026:
rata-rata tool call per pertanyaan **2,55**, dan yang paling boros (q016, kategori statistical)
memakai **6** tool call. Run kedua di gold set yang sama pada 2 Agustus 2026 memberi rata-rata
**2,3**. Jadi 12 kira-kira dua kali lipat kasus terburuk yang pernah benar-benar tercatat. Efeknya: pertanyaan normal tidak pernah menyentuh batas ini, sementara loop yang
ngelantur (model minta tool yang sama berulang-ulang) berhenti sebelum membakar kuota LLM.

Angka ini bukan hasil tuning teoretis. Kalau nanti gold set diperluas dan ada pertanyaan sah
yang butuh lebih dari 12 langkah, naikkan konstantanya dan perbarui alasannya di sini.
Adversarial eval sengaja dijalankan dengan `--max-tool-calls 6` untuk menghemat kuota, dan itu
memang menurunkan ruang gerak agent. Catatan itu ikut tercantum di
[`ADVERSARIAL_EVAL.md`](ADVERSARIAL_EVAL.md).

### Kenapa 200.000 token

Ini pagar kasar, bukan akuntansi biaya. Penghitungnya `_approx_tokens()` cuma membagi panjang
karakter dengan 4, dan dipanggil terhadap **seluruh transcript tiap iterasi**, jadi angka
`tokens` tumbuh lebih cepat daripada konsumsi token asli. Konsekuensinya batas ini konservatif:
dia menyala lebih awal daripada tagihan sebenarnya, yang untuk sebuah pagar justru arah error
yang benar.

Yang perlu jujur diakui: karena penghitungnya perkiraan, `tokens` di scorecard tidak boleh
dipakai untuk menghitung biaya. Akuntansi token presisi (dari `usage_metadata` response Gemini)
belum ada, dan itu tercatat sebagai item terbuka di brief 04 (HIJAU 7) serta di bagian
"Yang tidak terukur" pada [`EVAL_SCORECARD.md`](EVAL_SCORECARD.md).

### Kenapa 300 detik

Batas ini melindungi request SSE yang menggantung, bukan mengejar performa. Sandbox punya
batasnya sendiri (`SANDBOX_TIMEOUT_SEC`, default 30 detik per eksekusi kode), jadi satu run
12 langkah yang semuanya eksekusi kode pun masih di bawah 300 detik selama modelnya tidak
kena backoff berat. Di free tier Gemini, batch 20 pertanyaan tercatat memakan sekitar 45 menit
(sekitar 2,2 menit per pertanyaan) justru karena rate limit, jadi 5 menit per run memberi
kelonggaran sekitar dua kali lipat sebelum run dinyatakan mati.

### Cara mengubah tanpa menyentuh default

Ketiganya adalah argumen konstruktor `ReactLoop`, jadi tidak perlu mengedit konstanta:

```python
ReactLoop(max_tool_calls=6, max_tokens=50_000, timeout_s=120.0)
```

Runner adversarial memakai jalur ini lewat flag `--max-tool-calls`.

---

## 2. Alasan terminasi (aturan produksi #3)

Tiap run mencatat **kenapa** dia berhenti. Tanpa ini, run yang kehabisan langkah kelihatan
persis sama dengan run yang beneran selesai, padahal kualitas jawabannya beda jauh.

Kosakatanya tunggal, didefinisikan di `app/agent/termination.py`, dan dipakai di tiga lapisan:
loop (menentukan), DB (`run_history.termination_reason` dan `run_states.termination_reason`),
serta UI (`analyze-view.tsx` dan `history-view.tsx` memanggil `terminationLabel()`).

| Kode | Label UI | Artinya | Yang harus kamu lakukan saat melihatnya |
|---|---|---|---|
| `completed` | Selesai normal | Model mengembalikan `{"final": ...}` | Tidak ada. Ini satu-satunya alasan yang tidak masuk `INCOMPLETE_REASONS`. |
| `step_budget` | Berhenti: batas langkah tercapai | Iterasi mentok `max_tool_calls` tanpa jawaban final | Baca `run_steps`: kalau tool yang sama diulang-ulang, masalahnya prompt atau output tool yang tidak informatif, bukan batasnya kekecilan. Naikkan batas hanya kalau langkah-langkahnya memang maju. |
| `token_budget` | Berhenti: budget token habis | Perkiraan token melewati `max_tokens` | Biasanya tanda output tool kepanjangan (dump tabel besar) yang menumpuk di transcript. Pangkas output tool dulu sebelum menaikkan batas. |
| `timeout` | Berhenti: melewati batas waktu | Wall-clock melewati `timeout_s` | Cek apakah lambatnya di sandbox atau di backoff rate limit LLM. Dua penyebab itu obatnya beda. |
| `tool_error` | Berhenti: tool gagal beruntun | Run dihentikan karena kegagalan tool | Dipakai `run_batch.py` saat `run_fn` melempar exception. Lihat `answer_markdown` yang diawali `[ERROR]` untuk pesan aslinya. |
| `cancelled` | Dibatalkan | User atau client memutus koneksi | Bukan bug. Jangan hitung run ini di metrik kualitas. |
| `crashed` | Proses mati di tengah run | Prosesnya hilang; ketahuan dari `run_states.status` yang masih `running` | Kandidat resume. Lihat bagian 4 di bawah. |

Dua helper yang dipakai lintas lapisan:

- `label(reason)` mengubah kode jadi kalimat pendek. Kode asing dikembalikan apa adanya, jadi
  tidak pernah melempar exception.
- `is_incomplete(reason)` menjawab "apakah jawaban ini patut dicurigai belum lengkap".
  Semua kode kecuali `completed` masuk kategori itu.

Catatan penting saat membaca hasil eval: `step_budget`, `timeout`, dan `token_budget` tetap
menghasilkan `answer_markdown` berisi hasil parsial. Jawabannya ada, tapi itu bukan jawaban
final model. Jangan perlakukan sama dengan run `completed`.

---

## 3. Tool minimum (aturan produksi #1)

Deskripsi tiap tool ikut dikirim ke model di **setiap** request. Tool yang menganggur itu rugi
dua kali: bayar token tiap request, dan menambah peluang model salah pilih. Karena itu registry
dipangkas per intent, bukan dikirim semua sekaligus.

Intent ditentukan `app/agent/intent.py` secara deterministik (regex kata kunci ID dan EN), bukan
oleh LLM, dan defaultnya konservatif: ragu berarti `descriptive`.

| Intent | Tool yang dikirim | Yang sengaja tidak dikirim |
|---|---|---|
| `descriptive` | `inspect_schema`, `write_and_execute`, `make_chart` | seluruh tool kausal |
| `causal` | `inspect_schema`, `write_and_execute`, `causal_route`, `causal_analyze`, `causal_refute` | `make_chart` |
| intent asing | jatuh ke set `descriptive` | seluruh tool kausal |

Sumbernya `TOOLSETS` di `app/agent/tools/__init__.py`. Dua test menjaga pemangkasan ini benar-benar
sampai ke prompt, bukan cuma ke registry: `test_prompt_for_descriptive_question_omits_causal_tool_docs`
dan `test_prompt_for_causal_question_omits_chart_tool`.

### Kenapa `write_and_execute` tetap ada di jalur kausal

Ini pertanyaan yang wajar, karena aturan non-negotiable #1 repo ini bilang LLM tidak pernah
menghitung angka kausal. Jawabannya: yang dilarang bukan tool-nya, melainkan memakainya untuk
menghitung efek kausal.

Analisis kausal tetap butuh eksplorasi pendukung yang sah, misalnya mengecek jumlah baris per
arm, melihat distribusi outcome, atau memastikan kolom treatment memang biner. Tanpa
`write_and_execute`, agent kehilangan kemampuan itu dan malah lebih sering menebak.

Yang menjaga batasnya ada tiga lapis, bukan penghapusan tool:

1. **Prompt.** Blok `_CAUSAL_UNCONFIRMED` dan `_CAUSAL_CONFIRMED` di `react_loop.py` melarang
   eksplisit: semua angka efek harus dikutip dari output `causal_analyze`.
2. **Number-grounding check.** Setelah jawaban final, `check_grounding()` mencocokkan tiap angka
   di narasi dengan hasil engine. Ada angka yang tidak ada di hasil engine, narasi diganti
   template deterministik dan `answer_grounded` jadi `False`.
3. **Human gate.** `causal_analyze` tidak jalan sebelum mapping kolom dikonfirmasi user, dan
   `_confirmed_roles` di-inject oleh loop, bukan diambil dari argumen LLM (`args.pop` di
   `react_loop.py` membuang klaim konfirmasi yang dipalsukan model).

Jadi menghapus `write_and_execute` dari jalur kausal akan melumpuhkan eksplorasi tanpa menambah
jaminan apa pun yang belum dipegang tiga lapis di atas.

---

## 4. Durable state dan resume

Masalah yang dipecahkan: `run_history` cuma menyimpan **hasil**. Kalau proses mati di tengah run,
hasil itu tidak pernah ditulis dan seluruh pekerjaan hilang, termasuk tool call yang sudah
terlanjur jalan.

Solusinya: state loop ditulis ke SQLite **tiap langkah**, bukan cuma di akhir.

### Tabel

`run_states` (satu baris per run, header yang cukup untuk melanjutkan):

| Kolom | Isi |
|---|---|
| `run_id` | kunci unik, ter-index |
| `question`, `dataset_id` | input asli, dipulihkan saat resume |
| `causal_roles_json` | mapping kolom terkonfirmasi, kosong kalau belum ada |
| `intent`, `intent_json` | keputusan intent classifier beserta sinyalnya |
| `plan_json` | rencana dari planner, supaya resume tidak memanggil planner lagi |
| `transcript_head` | bagian transcript yang tidak berubah (system prompt, catatan kausal, pertanyaan, rencana) |
| `tokens`, `elapsed_ms` | akumulasi sebelum crash, dilanjutkan bukan direset |
| `status` | `running` / `completed` / `failed`. `running` yang tertinggal = kandidat resume |
| `termination_reason` | diisi saat `finish()` |
| `resume_count` | berapa kali run ini pernah dilanjutkan |
| `created_at`, `updated_at` | jejak waktu |

`run_steps` (satu baris per iterasi loop):

| Kolom | Isi |
|---|---|
| `run_id`, `step_index` | urutan langkah dalam run |
| `kind` | `tool`, `invalid_response`, atau `unknown_tool` |
| `tool`, `input_json` | nama tool dan argumennya |
| `output_text`, `error` | observasi hasil tool |
| `chart_paths_json` | artifact chart yang dihasilkan langkah itu |
| `tokens_after` | akumulasi token setelah langkah itu |
| `created_at` | jejak waktu |

Bagian dinamis transcript (aksi dan observasi) **tidak** disimpan di `run_states`. Dia
direkonstruksi dari `run_steps` saat resume, supaya step record benar-benar jadi sumber
kebenaran dan tidak ada dua versi transcript yang bisa berbeda.

Urutan penulisan penting: checkpoint langkah ditulis **setelah** tool jalan dan observasinya
masuk transcript. Dengan begitu yang tersimpan persis sama dengan state yang dipakai iterasi
berikutnya, jadi resume tidak mengulang efek samping tool yang sudah terjadi.

`SqliteCheckpointer.record_step()` membuka session sendiri dan commit tiap langkah. Itu lebih
mahal daripada satu transaksi besar, dan memang itu maksudnya: kalau proses dibunuh setelah
langkah kedua, langkah pertama dan kedua harus sudah ada di disk.

Default `ReactLoop` adalah `NullCheckpointer` (tidak menulis apa-apa). Durable state aktif kalau
checkpointer diberikan eksplisit, dan itu yang dilakukan `app/api/deps.py`, `run_batch.py`, serta
runner adversarial.

### Endpoint

**`POST /runs/{run_id}/resume`**

- `404` kalau `run_id` tidak ada di checkpoint.
- `409` kalau statusnya bukan `running` (tidak ada yang perlu dilanjutkan).
- Sukses: stream SSE persis seperti `/analyze`, diawali event `step` bertanda `resume` berisi
  `steps_replayed`, supaya UI tahu ini lanjutan dan bukan run baru.

Yang terjadi di balik layar (`ReactLoop.resume()`): checkpoint dimuat, transcript direkonstruksi
dari `run_steps`, `resume_count` dinaikkan, lalu loop yang sama dijalankan dengan `steps_done`
sebagai titik mulai. Planner **tidak** dipanggil ulang.

**`GET /runs/resumable?limit=50`**

Daftar run yang statusnya masih `running`, yaitu sisa proses yang mati di tengah. Ini pintu
masuk debugging setelah backend crash atau restart: cek daftar ini dulu sebelum menjalankan
ulang pertanyaan dari nol.

### Cara test crash recovery bekerja

Test intinya `backend/tests/test_durable_state.py::test_resume_after_hard_process_kill`.
Alurnya empat langkah:

1. Test menjalankan `backend/tests/crash_child.py` sebagai **subprocess terpisah** dengan
   argumen `<db_url> <run_id>`. Anak proses ini memakai LLM scripted, bukan Gemini, jadi test
   bebas kuota dan bisa jalan di CI.
2. Setelah dua tool call tersimpan, anak proses membunuh dirinya dengan **`os._exit(1)`**.
   Ini pilihan yang disengaja, bukan `sys.exit`: `os._exit` tidak melakukan unwind stack, tidak
   menjalankan blok `finally`, dan tidak memanggil handler `atexit`. Artinya tidak ada satu pun
   jalur cleanup yang bisa menyelamatkan state. Kalau state tetap ada di DB, satu-satunya
   penjelasan adalah checkpointer memang commit tiap langkah.
3. Proses induk (memori berbeda, instance `ReactLoop` baru, registry baru) memverifikasi
   `run_states.status` masih `running`, ada 2 baris di `run_steps`, dan `run_history` masih
   kosong untuk run itu. Lalu memanggil `resume(run_id)`.
4. Assert bahwa run selesai dengan jawaban benar, `termination_reason == "completed"`, dua tool
   call pra-crash ikut terbawa ke hasil akhir, transcript yang dikirim ke model memuat dua blok
   `[Aksi] inspect_schema`, `resume_count == 1`, dan planner tidak dipanggil ulang.

Poin 3 dan 4 itu yang membuat test ini bukan sekadar test unit checkpointer: buktinya harus
menyeberangi batas proses. Kalau kamu mengganti mekanisme penyimpanan, test ini yang harus
tetap hijau.

Menjalankan hanya test ini:

```bash
cd backend
python -m pytest tests/test_durable_state.py -q -p no:warnings
```

### Batas yang jujur

- Resume melanjutkan dari **langkah** terakhir yang tersimpan, bukan dari tengah sebuah tool
  call. Kalau proses mati saat sandbox sedang mengeksekusi kode, langkah itu tidak tercatat dan
  akan diulang.
- Status `failed` didefinisikan di skema tapi belum ada jalur kode yang menulisnya. Run yang
  gagal keras akan tertinggal sebagai `running`, dan memang itu yang bikin dia muncul di
  `GET /runs/resumable`.
- Tidak ada mekanisme kedaluwarsa. Run `running` yang sudah basi akan terus muncul di daftar
  kandidat resume sampai dihapus manual.
