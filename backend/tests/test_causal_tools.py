"""Kontrak tools kausal: gate konfirmasi mapping (D3), routing, analisis end-to-end.

Memakai dataset demo datasets/ab_marketing.csv (ground-truth di meta.json) —
kalau file belum ada, di-generate on the fly dari DGP (deterministik, seed sama).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.intent import classify_intent
from app.agent.tools import build_default_registry
from app.core.datasets import resolve_path

ROLES = {"treatment": "variant", "outcome": "converted", "covariates": ["pre_engagement"]}


@pytest.fixture(scope="module", autouse=True)
def ensure_dataset():
    try:
        resolve_path("ab_marketing")
    except FileNotFoundError:
        import subprocess
        import sys

        script = Path(__file__).resolve().parents[1] / "scripts" / "generate_demo_dataset.py"
        subprocess.run([sys.executable, str(script)], check=True)


@pytest.fixture()
def registry():
    return build_default_registry()


class TestRegistry:
    def test_causal_tools_registered(self, registry):
        names = registry.names()
        for tool in ("causal_route", "causal_analyze", "causal_refute"):
            assert tool in names

    def test_function_declarations_valid(self, registry):
        for decl in registry.function_declarations():
            assert decl["name"] and decl["description"]
            assert decl["parameters"]["type"] == "object"


class TestCausalRoute:
    def test_proposes_mapping_and_needs_confirmation(self, registry):
        res = registry.get("causal_route").run(dataset_id="ab_marketing")
        assert res.ok, res.error
        payload = json.loads(res.output)
        assert payload["needs_confirmation"] is True
        assert payload["roles"]["treatment"] == "variant"
        assert payload["roles"]["outcome"] == "converted"
        assert payload["router_decision"]["reasons"]  # P3

    def test_confirmed_roles_skip_confirmation(self, registry):
        res = registry.get("causal_route").run(
            dataset_id="ab_marketing", _confirmed_roles=ROLES
        )
        payload = json.loads(res.output)
        assert payload["needs_confirmation"] is False
        assert payload["router_decision"]["method"] == "ab_test"

    def test_llm_args_override_heuristic(self, registry):
        res = registry.get("causal_route").run(
            dataset_id="ab_marketing", outcome="pre_engagement"
        )
        payload = json.loads(res.output)
        assert payload["roles"]["outcome"] == "pre_engagement"


class TestCausalAnalyze:
    def test_refuses_without_confirmation(self, registry):
        """GATE D3: tanpa konfirmasi user, analisis TIDAK BOLEH jalan."""
        res = registry.get("causal_analyze").run(dataset_id="ab_marketing")
        assert not res.ok
        assert "KONFIRMASI" in res.error

    def test_full_pipeline_recovers_truth(self, registry):
        res = registry.get("causal_analyze").run(
            dataset_id="ab_marketing", _confirmed_roles=ROLES
        )
        assert res.ok, res.error
        payload = json.loads(res.output)

        meta_path = resolve_path("ab_marketing").with_suffix(".meta.json")
        true_lift = json.loads(meta_path.read_text(encoding="utf-8"))["ground_truth"][
            "true_lift_absolute"
        ]
        effect = payload["effect"]
        assert effect["ci_low"] <= true_lift <= effect["ci_high"]
        assert payload["router_decision"]["method"] == "ab_test"
        assert payload["assumptions"], "assumption checks wajib ada"
        assert payload["verdict"]["decision"] in ("deploy", "deploy_with_caution")

    def test_unimplemented_method_is_honest(self, registry):
        res = registry.get("causal_analyze").run(
            dataset_id="ab_marketing", _confirmed_roles=ROLES, method="observational"
        )
        assert not res.ok
        assert "M3" in res.error  # jujur soal roadmap, bukan mengarang hasil


class TestCausalRefute:
    def test_contract_is_honest_stub(self, registry):
        res = registry.get("causal_refute").run(dataset_id="ab_marketing")
        assert not res.ok
        assert "M3" in res.error


class TestIntentClassification:
    @pytest.mark.parametrize(
        "q",
        [
            "Apakah kampanye ini menaikkan konversi?",
            "Berapa dampak diskon terhadap profit?",
            "Does the new onboarding increase retention?",
            "Analisa hasil A/B test variant baru dong",
            "Apa efek perlakuan X ke outcome Y?",
        ],
    )
    def test_causal_questions(self, q):
        assert classify_intent(q).intent == "causal"

    @pytest.mark.parametrize(
        "q",
        [
            "Berapa total sales per region?",
            "Tampilkan tren revenue bulanan",
            "Top 5 produk paling laku apa aja?",
        ],
    )
    def test_descriptive_questions(self, q):
        d = classify_intent(q)
        assert d.intent == "descriptive"
        assert d.note  # saran eksplisit utk user (D2)

    def test_signals_surfaced_for_transparency(self):
        d = classify_intent("apakah fitur baru menyebabkan churn naik?")
        assert d.intent == "causal" and d.signals
