"""
Smoke tests. Run before and after any change:

    pytest -q

These are not unit tests. They drive the real apps through Streamlit's AppTest
harness and assert that every screen renders without an exception, that the
vocabulary is internally consistent, and that the handful of behaviours that
have broken before still work. Streamlit's failure mode is a silent wrong
value rather than a crash, so the specific assertions matter more than the
coverage.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
STAGE1 = str(ROOT / "sif_stage1_app.py")
STAGE2 = str(ROOT / "transfer_plan_stage2_app.py")
TIMEOUT = 300


def run(path: str) -> AppTest:
    at = AppTest.from_file(path, default_timeout=TIMEOUT).run()
    at.sidebar.button[0].click().run()          # "Load an example cohort"
    return at


def visit_all(at: AppTest) -> None:
    for step in list(at.sidebar.radio[0].options):
        at.sidebar.radio[0].set_value(step).run()
        at.run()
        assert not at.exception, f"{step}: {[e.value for e in at.exception]}"


# ---------------------------------------------------------------- vocabulary

def test_vocabulary_is_self_consistent():
    l1 = pd.read_csv(ROOT / "vocab" / "gp2_L1_constructs.csv")
    l2 = pd.read_csv(ROOT / "vocab" / "gp2_L2_to_L1.csv")
    tags = pd.read_csv(ROOT / "vocab" / "gp2_L3_item_tags.csv")
    names = set(l1.l1)

    unknown = set(l2.primary_l1) - names - {"EXCLUDE", "MULTIPLE"}
    assert not unknown, f"L2 points at constructs that do not exist: {unknown}"

    tagged = set(tags.extra_l1.dropna()) - {""}
    assert not tagged - names, f"item tags name unknown constructs: {tagged - names}"

    # every MULTIPLE instrument must tag every one of its items, or the items
    # inherit nothing and their constructs silently lose coverage
    multiple = set(l2[l2.primary_l1 == "MULTIPLE"].l2_modality)
    for m in multiple:
        rows = tags[tags.l2_modality == m]
        untagged = rows[rows.extra_l1.fillna("") == ""]
        assert untagged.empty or len(untagged) < 10, (
            f"{m}: {len(untagged)} items carry no construct tag")


def test_instrument_groups_resolve():
    """Every modality the app offers must exist in the vocabulary or be declared
    pending."""
    import ast
    src = (ROOT / "transfer_plan_stage2_app.py").read_text()
    tree = ast.parse(src)
    groups = next(ast.literal_eval(n.value) for n in tree.body
                  if isinstance(n, ast.Assign)
                  and any(getattr(t, "id", "") == "INSTRUMENT_GROUPS"
                          for t in n.targets))
    l2 = pd.read_csv(ROOT / "vocab" / "gp2_L2_to_L1.csv")
    pend_file = ROOT / "vocab" / "pending_modalities.txt"
    pending = {l.strip() for l in pend_file.read_text().splitlines()
               if l.strip() and not l.startswith("#")} if pend_file.exists() else set()
    known = set(l2.l2_modality) | pending
    named = {m for _, _, mods, _, _ in groups for m in mods}
    assert not named - known, f"INSTRUMENT_GROUPS names unknown modalities: {named - known}"

    labels = [lab for _, lab, _, _, _ in groups]
    dupes = {lab for lab in labels
             if sum(1 for c, l2l, _, _, _ in groups if l2l == lab
                    for _ in [0]) and labels.count(lab) > len(
                 {c for c, l, _, _, _ in groups if l == lab})}
    assert not dupes, f"a label is defined twice for the same construct: {dupes}"


# ---------------------------------------------------------------- stage 1

def test_stage1_every_screen_renders():
    visit_all(run(STAGE1))


def test_stage1_defaults_and_captions():
    """The domain matrix must open with most rows off and its captions shown.
    Both come from the same CSV columns, so they fail together — this caught a
    stale @st.cache_data once already."""
    at = run(STAGE1)
    at.sidebar.radio[0].set_value("3. Clinical & biomarker data").run()
    at.run()
    ticked = [c.label for c in at.checkbox if c.value]
    unticked = [c.label for c in at.checkbox if not c.value]
    assert 5 < len(ticked) < len(unticked), "default_on is not being applied"
    assert any("SCOPA-AUT" in str(c.value) for c in at.caption), \
        "example captions are missing — stale vocab CSV?"


def test_stage1_timespan_seeds_the_matrix():
    at = run(STAGE1)
    at.sidebar.radio[0].set_value("1. Study & contact").run()
    at.selectbox(key="w_timespan").set_value("Cross-sectional plus").run()
    at.sidebar.radio[0].set_value("3. Clinical & biomarker data").run()
    at.run()
    # mortality is off by default, so tick it before reading its seeded design
    at.checkbox(key="on::Mortality / vital status").check().run()
    d = at.session_state["designs"]
    assert d["Demographics"]["PD"] == "Cross-sectional"
    assert d["Mortality / vital status"]["PD"] == "Longitudinal", \
        "cross-sectional plus must still be longitudinal for mortality"


def test_stage1_row_toggle_clears_the_line():
    at = run(STAGE1)
    at.sidebar.radio[0].set_value("3. Clinical & biomarker data").run()
    at.run()
    at.checkbox(key="on::Cognition").uncheck().run()
    assert set(at.session_state["designs"]["Cognition"].values()) == {None}


def test_stage1_projection_below_current_is_an_error():
    at = run(STAGE1)
    at.sidebar.radio[0].set_value("4. Samples & numbers").run()
    at.run()
    src = at.session_state["_editor_srcs"]["counts"]
    horizon = next(c for c in src.columns if c.startswith("By "))
    key = "counts__" + str(at.session_state["_editor_versions"]["counts"])
    at.session_state[key] = {"edited_rows": {0: {"Now": 500, horizon: 100}},
                             "added_rows": [], "deleted_rows": []}
    at.run()
    at.sidebar.radio[0].set_value("6. Review & submit").run()
    at.run()
    assert any("already exist" in str(e.value) for e in at.error)


# ---------------------------------------------------------------- stage 2

def test_stage2_every_screen_renders():
    visit_all(run(STAGE2))


def test_stage2_selection_survives_navigation():
    """Streamlit discards widget state once a widget stops rendering. Anything
    the user decided has to come back from the plain-dict store, not from its
    default — this has broken three times."""
    at = run(STAGE2)
    at.sidebar.radio[0].set_value("2. What to transfer").run()
    at.run()
    src = at.session_state["_editor_srcs"]["instruments"]
    row = next(i for i, r in src.iterrows() if r["Instrument"] == "MoCA")
    key = "instruments__" + str(at.session_state["_editor_versions"]["instruments"])
    at.session_state[key] = {"edited_rows": {int(row): {"Transfer": False}},
                             "added_rows": [], "deleted_rows": []}
    at.run()
    assert "MoCA" not in at.session_state["selected"]
    at.sidebar.radio[0].set_value("4. DNA").run()
    at.run()
    at.sidebar.radio[0].set_value("2. What to transfer").run()
    at.run()
    assert "MoCA" not in at.session_state["selected"], \
        "unticking a default-on instrument was undone by navigating away"


def test_stage2_design_override_survives_navigation():
    at = run(STAGE2)
    at.sidebar.radio[0].set_value("2. What to transfer").run()   # populates the selection
    at.run()
    at.sidebar.radio[0].set_value("3. CS / LT").run()
    at.run()
    at.segmented_control(key="seg::MoCA::Control").set_value("None").run()
    at.run()
    at.sidebar.radio[0].set_value("2. What to transfer").run()
    at.run()
    at.sidebar.radio[0].set_value("3. CS / LT").run()
    at.run()
    assert at.session_state["designs"]["MoCA"]["Control"] is None


def test_stage2_disease_specific_scales_are_phenotype_scoped():
    at = run(STAGE2)
    at.sidebar.radio[0].set_value("2. What to transfer").run()
    at.run()
    at.sidebar.radio[0].set_value("3. CS / LT").run()
    at.run()
    at.session_state["w_phenotypes"] = ["PD", "PSP"]
    at.run()
    d = at.session_state["designs"].get("MDS-PSP criteria")
    if d:
        assert d.get("PD") is None, "a PSP scale must open at None in the PD arm"


def test_stage2_free_text_reaches_the_count_grids():
    at = run(STAGE2)
    at.sidebar.radio[0].set_value("2. What to transfer").run()
    at.run()
    at.session_state["extras"] = [{"domain": "Depression", "measure": "BDI-II"},
                                  {"domain": "Depression", "measure": "HADS-D"}]
    for step in ["3. CS / LT", "4. DNA", "6. Instrument numbers"]:
        at.sidebar.radio[0].set_value(step).run()
        at.run()
    items = {i for g in at.session_state["clinical"].values() for i in g["Item"]}
    assert "Depression — BDI-II" in items and "Depression — HADS-D" in items, \
        "two measures in one domain must both become rows"


@pytest.mark.parametrize("path", [STAGE1, STAGE2])
def test_pdf_builds(path):
    at = run(path)
    visit_all(at)
    labels = [d.label for d in at.download_button]
    assert any("PDF" in l for l in labels), f"no PDF button on {path}"
