"""
GP2 Data & Sample Transfer Plan — MVP prototype

Purpose of this prototype: show what conditional scoping buys us over a flat form.
A PI who runs a PD + Control cross-sectional cohort with blood and DNA only should
see roughly a dozen input cells, not the full 17 x 43 grid.

Run:  streamlit run transfer_plan_app.py
"""

import json
from datetime import date

import pandas as pd
import streamlit as st

# --------------------------------------------------------------------------
# Reference lists
# --------------------------------------------------------------------------

PHENOTYPES = [
    "PD", "Control", "PSP", "DLB", "MSA", "CBD/CBS", "FTD", "AD", "Mix",
    "VaD", "VaPD", "Population Control", "Undetermined-MCI",
    "Undetermined-Dementia", "Prodromal", "Other", "LBD",
]

# DNA is handled on its own screen: it sets the denominator for coverage.
OTHER_SAMPLE_TYPES = ["blood", "serum", "plasma", "csf", "brain", "skin", "SAA"]

# Clinical data asked at group level first. Instruments are only named where the
# distinction matters for harmonisation or for a downstream analysis.
MODALITY_GROUPS = {
    "Core clinical minimum": [
        "Demographics / age at onset / diagnosis date / family history",
    ],
    "Medication": ["Medication log / LEDD"],
    "Motor": ["MDS-UPDRS", "UPDRS (original)", "Hoehn & Yahr", "CISI-PD",
              "Schwab & England ADL"],
    "Cognitive": ["MoCA", "MMSE", "Other cognitive battery"],
    "Autonomic": ["SCOPA-AUT", "Orthostatic hypotension", "Vital signs"],
    "Sleep": ["RBD questionnaire", "Epworth Sleepiness Scale"],
    "Mood & behaviour": ["GDS", "QUIP-RS", "QUIP-CS"],
    "Olfaction": ["Olfactory test"],
    "Quality of life & pain": ["PDQ-39", "Pain scale"],
    "Imaging & functional": ["DAT results", "MIBG results"],
    "Neuropathology": ["Pathology report"],
    "Disease-specific scales": [
        "MDS-PSP criteria", "PSP-RS", "PSP-CDS", "MDS-MSA criteria", "UMSARS",
        "CBS-Armstrong criteria", "CBFS", "DLB diagnostic criteria",
    ],
    "Screening & other": ["IDEA screening questionnaire", "PD RFU-Q", "MERQ-PD-8"],
    "Lifestyle & environment": ["Lifestyle", "Environment"],
}

# Instruments only shown when a relevant phenotype is in scope.
PHENOTYPE_GATED = {
    "MDS-PSP criteria": {"PSP"},
    "PSP-RS": {"PSP"},
    "PSP-CDS": {"PSP"},
    "MDS-MSA criteria": {"MSA"},
    "UMSARS": {"MSA"},
    "CBS-Armstrong criteria": {"CBD/CBS"},
    "CBFS": {"CBD/CBS"},
    "DLB diagnostic criteria": {"DLB", "LBD"},
}

NUDGE_THRESHOLD = 50  # percent; below this after a deadline we flag the cohort


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------

DEFAULT_META = {
    "cohort_id": "",
    "pi_name": "",
    "round_label": f"{date.today().year} deposit",
    "as_of": date.today().isoformat(),
    "study_status": "Ongoing",
    "final_collection_year": date.today().year + 3,
    "deadline": (date(date.today().year, 12, 31)).isoformat(),
}


def init_state():
    st.session_state.setdefault("meta", dict(DEFAULT_META))
    st.session_state.setdefault("scope", {
        "phenotypes": [], "sample_types": [], "modality_groups": [],
        "show_all_instruments": False,
    })
    st.session_state.setdefault("dna", None)
    st.session_state.setdefault("samples", None)
    st.session_state.setdefault("clinical", None)
    st.session_state.setdefault("previous_round", {})  # (pheno,item) -> n cumulative
    st.session_state.setdefault("received", {})        # (pheno,item) -> n received


def is_ongoing() -> bool:
    return st.session_state["meta"]["study_status"] == "Ongoing"


def prev_value(pheno: str, item: str) -> int:
    return int(st.session_state["previous_round"].get(f"{pheno}||{item}", 0))


def build_grid(pairs, ongoing: bool) -> pd.DataFrame:
    """pairs: list of (phenotype, item). Returns an editable long-format grid."""
    rows = []
    for pheno, item in pairs:
        row = {
            "Phenotype": pheno,
            "Item": item,
            "Previously reported": prev_value(pheno, item),
            "New participants": 0,
        }
        if ongoing:
            row["Repeat participants"] = 0
        row["Note (optional)"] = ""
        rows.append(row)
    return pd.DataFrame(rows)


def merge_grid(old: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    """Keep values the PI already typed when the scope changes."""
    if old is None or old.empty:
        return new
    keys = ["Phenotype", "Item"]
    keep = [c for c in new.columns if c not in keys]
    merged = new.merge(old, on=keys, how="left", suffixes=("", "_old"))
    for c in keep:
        oldc = f"{c}_old"
        if oldc in merged.columns:
            merged[c] = merged[oldc].where(merged[oldc].notna(), merged[c])
            merged = merged.drop(columns=[oldc])
    return merged[new.columns]


def numeric_config(ongoing: bool) -> dict:
    cfg = {
        "Phenotype": st.column_config.TextColumn(disabled=True),
        "Item": st.column_config.TextColumn(disabled=True),
        "Previously reported": st.column_config.NumberColumn(
            disabled=True, help="Cumulative total you reported in the last round."),
        "New participants": st.column_config.NumberColumn(
            min_value=0, step=1, format="%d",
            help="Participants contributing this for the first time."),
        "Note (optional)": st.column_config.TextColumn(
            help="Anything blocking this item, if relevant."),
    }
    if ongoing:
        cfg["Repeat participants"] = st.column_config.NumberColumn(
            min_value=0, step=1, format="%d",
            help="Already-transferred participants contributing a further visit.")
    return cfg


def dna_denominator() -> dict:
    """Cumulative DNA participants per phenotype — the coverage denominator."""
    dna = st.session_state["dna"]
    if dna is None or dna.empty:
        return {}
    out = {}
    for _, r in dna.iterrows():
        out[r["Phenotype"]] = int(r["Previously reported"]) + int(r["New participants"])
    return out


# --------------------------------------------------------------------------
# Long-format export — this is what we store
# --------------------------------------------------------------------------

def to_long() -> pd.DataFrame:
    meta = st.session_state["meta"]
    ongoing = is_ongoing()
    frames = []
    for item_class, group_lookup, df in [
        ("sample", None, st.session_state["dna"]),
        ("sample", None, st.session_state["samples"]),
        ("clinical", "group", st.session_state["clinical"]),
    ]:
        if df is None or df.empty:
            continue
        d = df.copy()
        d["item_class"] = item_class
        frames.append(d)
    if not frames:
        return pd.DataFrame()

    long = pd.concat(frames, ignore_index=True)
    long = long.rename(columns={
        "Phenotype": "phenotype",
        "Item": "item",
        "Previously reported": "n_previous_cumulative",
        "New participants": "n_new",
        "Repeat participants": "n_repeat",
        "Note (optional)": "note",
        "Group": "item_group",
    })
    if "n_repeat" not in long.columns:
        long["n_repeat"] = 0
    if "item_group" not in long.columns:
        long["item_group"] = ""
    long["item_group"] = long["item_group"].fillna("")

    long["n_cumulative_participants"] = long["n_previous_cumulative"] + long["n_new"]
    long["cohort_id"] = meta["cohort_id"]
    long["round_label"] = meta["round_label"]
    long["as_of"] = meta["as_of"]
    long["deadline"] = meta["deadline"]
    long["study_status"] = meta["study_status"]
    long["n_received"] = [
        int(st.session_state["received"].get(f'{r.phenotype}||{r.item}', 0))
        for r in long.itertuples()
    ]
    long["pct_complete"] = (
        100 * long["n_received"] / long["n_cumulative_participants"].replace(0, float("nan")).astype(float)
    ).round(1)

    cols = ["cohort_id", "round_label", "as_of", "study_status", "deadline",
            "phenotype", "item_class", "item_group", "item",
            "n_previous_cumulative", "n_new", "n_repeat",
            "n_cumulative_participants", "n_received", "pct_complete", "note"]
    return long[[c for c in cols if c in long.columns]]


def validate(long: pd.DataFrame) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    meta = st.session_state["meta"]
    if not meta["cohort_id"].strip():
        errors.append("Cohort ID is missing.")
    if long.empty or long["n_cumulative_participants"].sum() == 0:
        errors.append("No numbers entered yet.")
        return errors, warnings

    denom = dna_denominator()
    if not denom or sum(denom.values()) == 0:
        errors.append("DNA numbers set the denominator for every coverage figure. "
                      "Enter them before submitting.")

    for pheno, n_dna in denom.items():
        if n_dna == 0:
            continue
        over = long[(long["phenotype"] == pheno)
                    & (long["item"] != "DNA")
                    & (long["n_cumulative_participants"] > n_dna)]
        for _, r in over.iterrows():
            warnings.append(
                f"{pheno} / {r['item']}: {int(r['n_cumulative_participants'])} "
                f"participants exceeds the {n_dna} with DNA. Check whether these "
                f"people are genuinely outside the genotyped set.")

    if is_ongoing() and long["n_repeat"].sum() == 0:
        warnings.append("Study is marked ongoing but no repeat participants are "
                        "planned. If every deposit is a new person, that is fine — "
                        "otherwise the follow-up numbers are missing.")

    try:
        if date.fromisoformat(meta["deadline"]) < date.today():
            warnings.append("The deadline is in the past.")
    except ValueError:
        errors.append("Deadline is not a valid date.")

    return errors, warnings


# --------------------------------------------------------------------------
# Screens
# --------------------------------------------------------------------------

def screen_cohort():
    st.header("1. Your cohort")
    st.caption("Everything after this screen is filtered by what you tell us here.")
    meta = st.session_state["meta"]
    c1, c2 = st.columns(2)
    meta["cohort_id"] = c1.text_input("GP2 cohort ID", meta["cohort_id"],
                                      placeholder="e.g. PPMI")
    meta["pi_name"] = c2.text_input("Principal investigator", meta["pi_name"])

    meta["study_status"] = st.radio(
        "Is recruitment or follow-up still running?",
        ["Ongoing", "Completed"],
        index=0 if meta["study_status"] == "Ongoing" else 1,
        horizontal=True,
        help="Completed studies transfer everything once. Ongoing studies deposit "
             "once a year until collection ends.")

    if is_ongoing():
        c1, c2 = st.columns(2)
        meta["final_collection_year"] = c1.number_input(
            "Last year you expect to collect data",
            min_value=date.today().year, max_value=date.today().year + 20,
            value=int(meta["final_collection_year"]))
        meta["deadline"] = c2.date_input(
            "Deadline for this year's deposit",
            value=date.fromisoformat(meta["deadline"])).isoformat()
        years = list(range(date.today().year, int(meta["final_collection_year"]) + 1))
        st.info(f"That schedules {len(years)} annual deposits: "
                f"{', '.join(str(y) for y in years)}. Each one asks for your "
                f"**cumulative total to date**, pre-filled with what you last "
                f"reported, so you only revise numbers upward.")
    else:
        meta["deadline"] = st.date_input(
            "Transfer deadline",
            value=date.fromisoformat(meta["deadline"])).isoformat()
        st.info("Single deposit. We will ask for the full dataset once.")


def screen_scope():
    st.header("2. What exists in this cohort")
    st.caption("Tick only what you have. You will not be asked about anything else.")
    scope = st.session_state["scope"]

    scope["phenotypes"] = st.multiselect(
        "Phenotypes in this cohort", PHENOTYPES, default=scope["phenotypes"])
    scope["sample_types"] = st.multiselect(
        "Biosamples available for transfer, besides DNA",
        OTHER_SAMPLE_TYPES, default=scope["sample_types"])
    scope["modality_groups"] = st.multiselect(
        "Clinical data domains collected", list(MODALITY_GROUPS),
        default=scope["modality_groups"])
    scope["show_all_instruments"] = st.checkbox(
        "Show disease-specific scales for phenotypes I did not select",
        value=scope["show_all_instruments"])

    n_pheno = max(len(scope["phenotypes"]), 1)
    full = len(PHENOTYPES) * (1 + len(OTHER_SAMPLE_TYPES) +
                              sum(len(v) for v in MODALITY_GROUPS.values()))
    shown = n_pheno * (1 + len(scope["sample_types"]) +
                       len(visible_instruments(scope)))
    if scope["phenotypes"]:
        st.success(f"You will be asked to fill **{shown}** cells. "
                   f"A flat form covering everything would ask for {full}.")


def visible_instruments(scope) -> list[tuple[str, str]]:
    out = []
    selected = set(scope["phenotypes"])
    for group in scope["modality_groups"]:
        for inst in MODALITY_GROUPS[group]:
            gate = PHENOTYPE_GATED.get(inst)
            if gate and not scope["show_all_instruments"] and not (gate & selected):
                continue
            out.append((group, inst))
    return out


def screen_dna():
    st.header("3. DNA transfer plan")
    st.caption("Ask this first: the DNA numbers define the cohort size we compare "
               "everything else against.")
    scope = st.session_state["scope"]
    if not scope["phenotypes"]:
        st.warning("Select phenotypes on screen 2 first.")
        return

    pairs = [(p, "DNA") for p in scope["phenotypes"]]
    grid = merge_grid(st.session_state["dna"], build_grid(pairs, ongoing=False))
    edited = st.data_editor(
        grid, hide_index=True, width="stretch",
        column_config=numeric_config(ongoing=False), key="dna_editor")
    if is_ongoing():
        edited["Repeat participants"] = 0
    st.session_state["dna"] = edited

    total = int(edited["Previously reported"].sum() + edited["New participants"].sum())
    st.metric("Participants with DNA, cumulative", total)
    st.caption("One row per participant per material. A person giving blood, plasma "
               "and DNA counts once in each of those three rows.")


def screen_samples():
    st.header("4. Other biosamples")
    scope = st.session_state["scope"]
    if not scope["sample_types"]:
        st.info("No other biosamples selected. Skip to clinical data.")
        st.session_state["samples"] = None
        return
    if not scope["phenotypes"]:
        st.warning("Select phenotypes on screen 2 first.")
        return

    ongoing = is_ongoing()
    if ongoing:
        st.caption("Split new participants from repeat draws on people already "
                   "transferred — otherwise we cannot tell growth from follow-up.")
    pairs = [(p, s) for p in scope["phenotypes"] for s in scope["sample_types"]]
    grid = merge_grid(st.session_state["samples"], build_grid(pairs, ongoing))
    st.session_state["samples"] = st.data_editor(
        grid, hide_index=True, width="stretch",
        column_config=numeric_config(ongoing), key="sample_editor")


def screen_clinical():
    st.header("5. Clinical data")
    scope = st.session_state["scope"]
    instruments = visible_instruments(scope)
    if not instruments or not scope["phenotypes"]:
        st.info("Select phenotypes and clinical domains on screen 2 first.")
        st.session_state["clinical"] = None
        return

    ongoing = is_ongoing()
    st.caption("Counts are participants, not visits. For ongoing studies, repeat "
               "means an existing participant with a further assessment.")

    frames = []
    for group in scope["modality_groups"]:
        items = [(g, i) for g, i in instruments if g == group]
        if not items:
            continue
        with st.expander(group, expanded=(group == scope["modality_groups"][0])):
            pairs = [(p, i) for p in scope["phenotypes"] for _, i in items]
            sub = build_grid(pairs, ongoing)
            sub.insert(2, "Group", group)
            prev = st.session_state["clinical"]
            if prev is not None and not prev.empty:
                sub = merge_grid(prev[prev["Group"] == group].drop(columns=["Group"])
                                 if "Group" in prev.columns else prev,
                                 sub.drop(columns=["Group"]))
                sub.insert(2, "Group", group)
            cfg = numeric_config(ongoing)
            cfg["Group"] = st.column_config.TextColumn(disabled=True)
            frames.append(st.data_editor(
                sub, hide_index=True, width="stretch",
                column_config=cfg, key=f"clin_{group}"))

    st.session_state["clinical"] = (pd.concat(frames, ignore_index=True)
                                    if frames else None)


def screen_review():
    st.header("6. Review and submit")
    long = to_long()
    errors, warnings = validate(long)
    for e in errors:
        st.error(e)
    for w in warnings:
        st.warning(w)
    if long.empty:
        return

    denom = dna_denominator()
    st.subheader("Coverage against DNA")
    cov = long[long["item"] != "DNA"].copy()
    if not cov.empty and denom:
        cov["DNA participants"] = cov["phenotype"].map(denom)
        cov["Coverage %"] = (100 * cov["n_cumulative_participants"]
                             / cov["DNA participants"].replace(0, float("nan")).astype(float)).round(0)
        wide = cov.pivot_table(index="item", columns="phenotype",
                               values="Coverage %", aggfunc="first")
        st.dataframe(wide.style.format("{:.0f}%", na_rep="—"),
                     width="stretch")
        st.caption("Coverage is derived, not asked. It falls out of the DNA "
                   "denominator and the per-item counts.")

    st.subheader("What gets stored")
    st.dataframe(long, hide_index=True, width="stretch")
    st.caption("Long format: one row per cohort x round x phenotype x item. "
               "Adding a modality or a deadline never changes the schema.")

    c1, c2 = st.columns(2)
    c1.download_button("Download plan (CSV)", long.to_csv(index=False),
                       file_name=f"transfer_plan_{st.session_state['meta']['cohort_id'] or 'draft'}.csv",
                       mime="text/csv")
    snapshot = {
        "meta": st.session_state["meta"],
        "scope": st.session_state["scope"],
        "cumulative": {f"{r.phenotype}||{r.item}": int(r.n_cumulative_participants)
                       for r in long.itertuples()},
    }
    c2.download_button("Save draft (JSON)", json.dumps(snapshot, indent=2),
                       file_name="transfer_plan_draft.json",
                       mime="application/json")


def screen_gp2_view():
    st.header("GP2 tracking view")
    st.caption("Not shown to PIs. This is the side that answers 'who is lagging'.")
    long = to_long()
    if long.empty:
        st.info("Fill in a plan first.")
        return

    st.write("Enter what has actually arrived. PIs never see or edit this.")
    rec = long[["phenotype", "item", "n_cumulative_participants"]].copy()
    rec["Received"] = [st.session_state["received"].get(f"{r.phenotype}||{r.item}", 0)
                       for r in rec.itertuples()]
    rec = rec.rename(columns={"phenotype": "Phenotype", "item": "Item",
                              "n_cumulative_participants": "Promised"})
    edited = st.data_editor(
        rec, hide_index=True, width="stretch",
        column_config={
            "Phenotype": st.column_config.TextColumn(disabled=True),
            "Item": st.column_config.TextColumn(disabled=True),
            "Promised": st.column_config.NumberColumn(disabled=True),
            "Received": st.column_config.NumberColumn(min_value=0, step=1, format="%d"),
        }, key="received_editor")
    st.session_state["received"] = {
        f"{r.Phenotype}||{r.Item}": int(r.Received) for r in edited.itertuples()}

    edited["% complete"] = (100 * edited["Received"]
                            / edited["Promised"].replace(0, float("nan")).astype(float)).round(0)
    overdue = date.fromisoformat(st.session_state["meta"]["deadline"]) < date.today()
    lagging = edited[edited["% complete"].fillna(0) < NUDGE_THRESHOLD]

    c1, c2, c3 = st.columns(3)
    c1.metric("Promised", int(edited["Promised"].sum()))
    c2.metric("Received", int(edited["Received"].sum()))
    overall = (100 * edited["Received"].sum() / max(edited["Promised"].sum(), 1))
    c3.metric("Overall complete", f"{overall:.0f}%")

    if overdue and not lagging.empty:
        st.error(f"Past deadline and {len(lagging)} items are below "
                 f"{NUDGE_THRESHOLD}%. These are the nudge candidates.")
        st.dataframe(lagging, hide_index=True, width="stretch")
    elif not lagging.empty:
        st.info(f"{len(lagging)} items below {NUDGE_THRESHOLD}%, but the deadline "
                f"has not passed. No nudge yet.")
    else:
        st.success("Nothing below the nudge threshold.")
    st.caption(f"Only completed, released material is visible to us, so partial "
               f"percentages are expected before a deadline. The nudge fires on "
               f"overdue items below {NUDGE_THRESHOLD}% rather than on anything "
               f"short of 100%.")


# --------------------------------------------------------------------------
# Shell
# --------------------------------------------------------------------------

STEPS = {
    "1. Your cohort": screen_cohort,
    "2. What you have": screen_scope,
    "3. DNA": screen_dna,
    "4. Other biosamples": screen_samples,
    "5. Clinical data": screen_clinical,
    "6. Review & submit": screen_review,
    "— GP2 tracking view": screen_gp2_view,
}


def sidebar():
    st.sidebar.title("GP2 transfer plan")
    st.sidebar.caption("Prototype for discussion — not a live collection.")
    step = st.sidebar.radio("Step", list(STEPS), label_visibility="collapsed")

    st.sidebar.divider()
    up = st.sidebar.file_uploader("Resume a saved draft", type="json")
    if up is not None and not st.session_state.get("_loaded"):
        data = json.load(up)
        st.session_state["meta"].update(data.get("meta", {}))
        st.session_state["scope"].update(data.get("scope", {}))
        st.session_state["previous_round"] = data.get("cumulative", {})
        st.session_state["_loaded"] = True
        st.sidebar.success("Draft loaded. Previous totals are pre-filled.")

    if st.sidebar.button("Load an example cohort"):
        load_demo()
        st.rerun()

    st.sidebar.divider()
    st.sidebar.caption(
        "Real deployment needs a per-cohort tokenised link instead of a login, "
        "and a database behind it. Neither is in this prototype.")
    return step


def load_demo():
    st.session_state["meta"].update({
        "cohort_id": "DEMO-COHORT", "pi_name": "A. Example",
        "study_status": "Ongoing", "final_collection_year": date.today().year + 2,
    })
    st.session_state["scope"].update({
        "phenotypes": ["PD", "Control", "Prodromal"],
        "sample_types": ["blood", "plasma", "csf"],
        "modality_groups": ["Core clinical minimum", "Motor", "Cognitive", "Sleep"],
    })
    st.session_state["previous_round"] = {
        "PD||DNA": 420, "Control||DNA": 180, "Prodromal||DNA": 55,
        "PD||MDS-UPDRS": 400, "PD||MoCA": 380, "Control||MoCA": 175,
        "PD||blood": 410, "PD||plasma": 300, "PD||csf": 90,
    }
    st.session_state["dna"] = None
    st.session_state["samples"] = None
    st.session_state["clinical"] = None


def main():
    init_state()
    step = sidebar()
    STEPS[step]()


if __name__ == "__main__":
    main()
