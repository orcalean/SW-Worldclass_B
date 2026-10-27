from pathlib import Path

from app.rubric.importer import import_core
from app.rubric.registry import load_catalogue

XLSX = Path(__file__).resolve().parents[2] / "rubrics/source/OracLean_Quality_Core1_Requirement_Known_Full_v1.xlsx"
DECLARED = {"1.1": 4, "1.2": 5, "1.3": 5, "1.4": 5, "1.5": 5, "1.6": 5,
            "1.7": 4, "1.8": 5, "1.9": 5, "1.10": 5, "1.11": 4, "1.12": 4}


def test_importer_matches_declared_counts():
    core = import_core(XLSX, "Q", 1, "1.0")
    assert {s.id: len(s.checks) for s in core.subcategories} == DECLARED
    assert len(core.checks()) == 56
    assert all(set(c.criteria) == {"L1", "L2", "L3"} and all(c.criteria.values()) for c in core.checks())


def test_committed_rubric_is_in_sync_with_workbook():
    core = import_core(XLSX, "Q", 1, "1.0")
    cat = load_catalogue()
    committed = next(c for c in cat.assessed_cores() if c.id == "Q.core1")
    assert committed.model_dump() == core.model_dump()


def test_catalogue_has_all_sqdcme_and_policy_ids_exist():
    cat = load_catalogue()
    assert [d.key for d in cat.dimensions] == list("SQDCME")
    for bid in cat.policy.blocking_checks:
        assert cat.check(bid) is not None, bid
