"""Durable state + crash recovery (brief 04, Skill 2).

Klaim yang diuji: agent ini bisa LANJUT setelah proses mati, bukan cuma jalan
mulus di demo. Test intinya `test_resume_after_hard_process_kill`:

  1. Subprocess menjalankan run agent sampai dua tool call tersimpan.
  2. Subprocess membunuh dirinya dengan os._exit(1), tanpa cleanup, tanpa
     finally, tanpa flush atexit.
  3. Proses induk (proses lain, memori lain) memanggil resume dari checkpoint.
  4. Run selesai dengan jawaban yang benar, dan tool call dari SEBELUM crash
     masih ada di hasil akhir.

Semua pakai LLM scripted, tidak ada panggilan Gemini, jadi aman dari kuota dan
bisa jalan di CI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.agent.checkpoint import SqliteCheckpointer
from app.agent.react_loop import ReactLoop, RunNotResumable
from app.core.schemas import SSEEvent
from app.db import repository
from app.db.session import configure_database, create_tables

BACKEND_DIR = Path(__file__).resolve().parents[1]
CRASH_CHILD = Path(__file__).resolve().parent / "crash_child.py"

EXPECTED_ANSWER = "Total Sales = **$2,297,200.86**"


@pytest.fixture
def temp_db(tmp_path):
    """DB sementara + tabel; dikembalikan sebagai (url, path)."""
    db_file = tmp_path / "durable.db"
    url = f"sqlite:///{db_file.as_posix()}"
    configure_database(url)
    create_tables()
    try:
        yield url, db_file
    finally:
        configure_database(None)


class ScriptedLLM:
    """Balas plan untuk prompt planner, lalu aksi sesuai antrian untuk loop."""

    def __init__(self, actions: list[dict]):
        self._actions = list(actions)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if "perencana" in prompt:
            return json.dumps([{"description": "inspect schema", "tool": "inspect_schema"}])
        if self._actions:
            return json.dumps(self._actions.pop(0))
        return json.dumps({"final": "fallback", "code": ""})


# ── Checkpoint dasar ─────────────────────────────────────────────────────────


def test_every_step_is_persisted(temp_db):
    """Tiap iterasi loop tersimpan, bukan cuma hasil akhir."""
    llm = ScriptedLLM(
        [
            {"action": "inspect_schema", "args": {}},
            {"action": "inspect_schema", "args": {}},
            {"final": EXPECTED_ANSWER, "code": "df['Sales'].sum()"},
        ]
    )
    loop = ReactLoop(generate=llm, checkpointer=SqliteCheckpointer())
    res = loop.run("Berapa total penjualan?", "superstore")

    steps = repository.list_run_steps(res.run_id)
    assert len(steps) == 2
    assert [s["step_index"] for s in steps] == [0, 1]
    assert all(s["kind"] == "tool" and s["tool"] == "inspect_schema" for s in steps)
    # Output tool ikut tersimpan, itu yang dipakai merekonstruksi transcript.
    assert all(s["output_text"] for s in steps)

    state = repository.get_run_state(res.run_id)
    assert state is not None
    assert state["status"] == "completed"
    assert state["termination_reason"] == "completed"
    assert state["question"] == "Berapa total penjualan?"


def test_non_tool_iterations_also_persisted(temp_db):
    """Balasan non-JSON dan tool tak dikenal juga tercatat, supaya resume tidak kehilangan konteks."""
    class Flaky:
        def __init__(self):
            self.n = 0

        def __call__(self, prompt: str) -> str:
            if "perencana" in prompt:
                return json.dumps([{"description": "x", "tool": "inspect_schema"}])
            self.n += 1
            if self.n == 1:
                return "ini bukan json"
            if self.n == 2:
                return json.dumps({"action": "drop_table", "args": {}})
            return json.dumps({"final": "ok", "code": ""})

    loop = ReactLoop(generate=Flaky(), checkpointer=SqliteCheckpointer())
    res = loop.run("q", "superstore")

    kinds = [s["kind"] for s in repository.list_run_steps(res.run_id)]
    assert kinds == ["invalid_response", "unknown_tool"]


# ── Test inti: crash keras lalu resume ────────────────────────────────────────


def test_resume_after_hard_process_kill(temp_db):
    """INTI: proses dimatikan di tengah run, resume menyelesaikannya dengan benar."""
    db_url, db_file = temp_db
    run_id = "run_crashtest01"

    # 1) Jalankan run di proses terpisah yang membunuh dirinya di tengah.
    proc = subprocess.run(
        [sys.executable, str(CRASH_CHILD), db_url, run_id],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 1, (
        f"anak proses harus mati dengan exit 1 (crash), bukan {proc.returncode}.\n"
        f"stdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert "CRASHING_AFTER=2" in proc.stdout
    assert "UNEXPECTED_COMPLETION" not in proc.stdout

    # 2) Proses induk: state pra-crash harus ada di disk.
    state = repository.get_run_state(run_id)
    assert state is not None, "state run hilang setelah crash, checkpoint tidak durable"
    assert state["status"] == "running", "run yang mati harus tetap bertanda 'running'"
    steps_before = repository.list_run_steps(run_id)
    assert len(steps_before) == 2, f"harus ada 2 langkah tersimpan, ada {len(steps_before)}"

    # Run yang mati BELUM masuk run_history (hasil akhir memang tidak pernah ada).
    assert repository.get_run_record(run_id) is None

    # 3) Resume dari proses ini, dengan LLM baru yang langsung memberi jawaban final.
    #    Instance ReactLoop baru, registry baru, tidak ada state di memori yang diwarisi.
    events: list[SSEEvent] = []
    resume_llm = ScriptedLLM(
        [{"final": EXPECTED_ANSWER, "code": "df['Sales'].sum()", "key_value": 2297200.86,
          "verify_sql": 'SELECT SUM("Sales") FROM t'}]
    )
    res = ReactLoop(generate=resume_llm, checkpointer=SqliteCheckpointer()).resume(
        run_id, on_event=events.append
    )

    # 4) Run selesai dengan hasil yang benar.
    assert res.run_id == run_id
    assert "2,297,200.86" in res.answer_markdown
    assert res.termination_reason == "completed"

    # 5) Bukti ini LANJUTAN, bukan run baru: tool call sebelum crash ikut terbawa.
    assert [tc.tool for tc in res.tool_calls] == ["inspect_schema", "inspect_schema"]
    assert all(tc.output for tc in res.tool_calls)

    # 6) Transcript yang dikirim ke model saat resume memuat observasi pra-crash.
    loop_prompt = next(p for p in resume_llm.prompts if "perencana" not in p)
    assert loop_prompt.count("[Aksi] inspect_schema") == 2
    assert "Berapa total penjualan?" in loop_prompt  # pertanyaan asli dipulihkan dari DB

    # 7) Verifikasi silang tetap jalan di jalur resume.
    assert res.verification is not None and res.verification.passed

    # 8) State ditutup rapi + tercatat pernah di-resume.
    after = repository.get_run_state(run_id)
    assert after["status"] == "completed"
    assert after["resume_count"] == 1

    # 9) Planner TIDAK dipanggil ulang saat resume (rencana dipulihkan dari checkpoint).
    assert not any("perencana" in p for p in resume_llm.prompts)


def test_resume_rejects_unknown_run(temp_db):
    loop = ReactLoop(generate=ScriptedLLM([]), checkpointer=SqliteCheckpointer())
    with pytest.raises(RunNotResumable):
        loop.resume("run_tidak_ada")


def test_resume_rejects_completed_run(temp_db):
    llm = ScriptedLLM([{"final": "sudah selesai", "code": ""}])
    loop = ReactLoop(generate=llm, checkpointer=SqliteCheckpointer())
    res = loop.run("q", "superstore")

    with pytest.raises(RunNotResumable):
        ReactLoop(generate=ScriptedLLM([]), checkpointer=SqliteCheckpointer()).resume(res.run_id)


def test_resumable_runs_listed_after_crash(temp_db):
    """Run yang mati muncul di daftar kandidat resume."""
    db_url, _ = temp_db
    run_id = "run_crashtest02"
    subprocess.run(
        [sys.executable, str(CRASH_CHILD), db_url, run_id],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        timeout=180,
    )
    pending = repository.list_resumable_runs()
    assert any(r["run_id"] == run_id for r in pending)
