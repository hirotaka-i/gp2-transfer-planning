"""
GP2 Data & Sample Transfer Plan — MVP prototype (v2)

Model: a cohort PI fills this ONCE, at contracting, to lay out the whole
transfer plan up front. For an ongoing study they project year by year until
collection ends. They are not asked to come back and re-report each year, so
there is no "previously reported" column anywhere.

Run:  streamlit run transfer_plan_app.py
"""

import json
from datetime import date

import pandas as pd
import streamlit as st

st.set_page_config(page_title="GP2 Transfer Plan", layout="wide")

# --------------------------------------------------------------------------
# Reference lists
# --------------------------------------------------------------------------

PHENOTYPES = [
    "PD", "Control", "PSP", "DLB", "MSA", "CBD/CBS", "FTD", "AD", "Mix",
    "VaD", "VaPD", "Population Control", "Undetermined-MCI",
    "Undetermined-Dementia", "Prodromal", "Other", "LBD",
]

# DNA has its own screen: it sets the denominator for coverage.
OTHER_SAMPLE_TYPES = ["blood", "serum", "plasma", "csf", "brain", "skin", "SAA"]

CLINICAL_DOMAINS = [
    "Demographics",
    "Extended family history",
    "Diagnosis (baseline)",
    "Diagnosis change",
    "Vitals",
    "Medical history",
    "Medication",
    "Mortality / living status",
    "Environmental",
    "SEADL",
    "CISI-PD",
    "MoCA",
    "MMSE",
    "MDS-UPDRS1",
    "MDS-UPDRS2",
    "MDS-UPDRS3",
    "MDS-UPDRS4",
    "MERQ-PD",
    "mMERQ-PD",
    "SCOPA-AUT",
    "RBD Screening Questionnaire",
    "RBD single question",
    "PSG RBD (performed, yes/no)",
    "Depression",
    "Epworth Sleepiness Scale",
    "Smell testing",
    "Pure autonomic failure - clinical diagnosis",
    "QUIP",
    "PDQ-8/39",
    "PSP-RS",
    "UMSARS",
    "CBFS A",
]

CROSS_SECTIONAL = "Cross-sectional"
LONGITUDINAL = "Longitudinal"
NOT_COLLECTED = "—"

# Short labels for the per-phenotype matrix, where columns must stay narrow.
SHORT = {CROSS_SECTIONAL: "CS", LONGITUDINAL: "LT", None: NOT_COLLECTED}
LONG_LABEL = {"CS": CROSS_SECTIONAL, "LT": LONGITUDINAL, NOT_COLLECTED: None}

# Collected once per person by definition. Locked on screen 2.
ALWAYS_CROSS_SECTIONAL = {
    "Demographics", "Extended family history", "Diagnosis (baseline)",
}

# Follow-up events by nature. Pre-set to longitudinal, but the PI can change it.
DEFAULT_LONGITUDINAL = {"Diagnosis change", "Mortality / living status"}

# Domains where the exact instrument matters and free text is expected.
NEEDS_SPECIFYING = {"Smell testing", "Depression", "QUIP", "PDQ-8/39"}

# Example cohort used by the sidebar button: (baseline, [new per plan year]).
DEMO_DNA = {
    "PD": (300, [200, 100, 0]),
    "Control": (300, [0, 0, 0]),
    "Prodromal": (200, [100, 100, 0]),
}

PREFILL_NOTE = {
    "clinical": "Pre-filled from your DNA numbers, on the assumption that most "
                "genotyped participants were also assessed. **Correct anything "
                "that differs** — partial coverage is normal and we would "
                "rather have the real number than the optimistic one.",
    "sample": "Pre-filled from your DNA numbers as a starting point. Biosample "
              "coverage is usually well below the genotyped count — CSF and "
              "brain especially — so **expect to reduce most of these**.",
}

NUDGE_THRESHOLD = 50  # percent; below this after a deadline we flag the cohort
MAX_PLAN_YEARS = 10


# --------------------------------------------------------------------------
# State
#
# Two Streamlit traps are designed around here; see CLAUDE.md.
#   1. A widget's output is never fed back as its own `value=`/`default=` or
#      as the frame handed to st.data_editor.
#   2. Keyed widget state is discarded when the widget is not rendered, so
#      plain widgets are re-assigned each run and editors are rebuilt on
#      navigation via `_nav`.
# --------------------------------------------------------------------------

DEFAULT_META = {
    "cohort_id": "",
    "contact_name": "",
    "contact_email": "",
    "study_status": "Ongoing",
    "final_collection_year": date.today().year + 3,
    "deadline": date(date.today().year, 12, 31).isoformat(),
}

WIDGET_KEYS = ["w_cohort_id", "w_contact_name", "w_contact_email", "w_status",
               "w_final_year", "w_deadline", "w_phenotypes", "w_sample_types",
               "w_domains"]


def init_state():
    st.session_state.setdefault("meta", dict(DEFAULT_META))
    st.session_state.setdefault("scope", {
        "phenotypes": [], "sample_types": [], "domains": [],
    })
    # {kind: {item: design}} and {kind: {item: {phenotype: design|None}}}
    st.session_state.setdefault("designs", {"clinical": {}, "sample": {}})
    st.session_state.setdefault("phenotype_designs", {"clinical": {}, "sample": {}})
    st.session_state.setdefault("dna", None)
    st.session_state.setdefault("samples", {})     # (phenotype, design) -> DataFrame
    st.session_state.setdefault("clinical", {})    # (phenotype, design) -> DataFrame
    st.session_state.setdefault("received", {})    # "pheno||item" -> (baseline, followup)
    st.session_state.setdefault("_editor_sigs", {})
    st.session_state.setdefault("_editor_srcs", {})
    st.session_state.setdefault("_editor_versions", {})
    st.session_state.setdefault("_prefilled", set())
    st.session_state.setdefault("_nav", 0)
    st.session_state.setdefault("_last_step", None)

    st.session_state.setdefault("w_cohort_id", DEFAULT_META["cohort_id"])
    st.session_state.setdefault("w_contact_name", DEFAULT_META["contact_name"])
    st.session_state.setdefault("w_contact_email", DEFAULT_META["contact_email"])
    st.session_state.setdefault("w_status", DEFAULT_META["study_status"])
    st.session_state.setdefault("w_final_year", DEFAULT_META["final_collection_year"])
    st.session_state.setdefault("w_deadline", date.fromisoformat(DEFAULT_META["deadline"]))
    st.session_state.setdefault("w_phenotypes", [])
    st.session_state.setdefault("w_sample_types", [])
    st.session_state.setdefault("w_domains", [])



def persist_widget_state():
    """Keep plain widget values alive while the user is on another screen."""
    for k in WIDGET_KEYS:
        if k in st.session_state:
            st.session_state[k] = st.session_state[k]


def sync_from_widgets():
    """Rebuild meta and scope from widget state, once per run."""
    st.session_state["meta"].update({
        "cohort_id": st.session_state["w_cohort_id"],
        "contact_name": st.session_state["w_contact_name"],
        "contact_email": st.session_state["w_contact_email"],
        "study_status": st.session_state["w_status"],
        "final_collection_year": int(st.session_state["w_final_year"]),
        "deadline": st.session_state["w_deadline"].isoformat(),
    })
    st.session_state["scope"] = {
        "phenotypes": list(st.session_state["w_phenotypes"]),
        "sample_types": list(st.session_state["w_sample_types"]),
        "domains": list(st.session_state["w_domains"]),
    }


def is_ongoing() -> bool:
    return st.session_state["meta"]["study_status"] == "Ongoing"


def plan_years() -> list[int]:
    """Years the PI projects for. Empty for a completed study."""
    if not is_ongoing():
        return []
    meta = st.session_state["meta"]
    start = date.fromisoformat(meta["deadline"]).year
    end = int(meta["final_collection_year"])
    return list(range(start, min(end, start + MAX_PLAN_YEARS - 1) + 1))


def default_design(kind: str, item: str) -> str:
    if kind == "clinical":
        if item in ALWAYS_CROSS_SECTIONAL:
            return CROSS_SECTIONAL
        return LONGITUDINAL if item in DEFAULT_LONGITUDINAL else CROSS_SECTIONAL
    return CROSS_SECTIONAL


def is_locked(kind: str, item: str) -> bool:
    return kind == "clinical" and item in ALWAYS_CROSS_SECTIONAL


def base_design(kind: str, item: str) -> str:
    """Starting value for every phenotype until the PI changes one."""
    if is_locked(kind, item):
        return CROSS_SECTIONAL
    return st.session_state["designs"][kind].get(item, default_design(kind, item))


def design_of(kind: str, item: str, phenotype: str | None = None) -> str | None:
    """How an item is collected — for one phenotype, or as a starting default.

    Returns CROSS_SECTIONAL, LONGITUDINAL, or None when that phenotype does not
    have the item at all. Design belongs to the (item, phenotype) pair: a cohort
    can follow MMSE longitudinally in PD and take it once in controls, and the
    same is true of blood draws. The screen-2 matrix is the only place this is
    set — every cell starts at `base_design` and the PI changes the ones that
    differ.
    """
    if phenotype is None:
        return base_design(kind, item)
    cell = st.session_state["phenotype_designs"][kind].get(item, {})
    return cell.get(phenotype, base_design(kind, item))


def scope_items(kind: str) -> list[str]:
    return st.session_state["scope"]["domains" if kind == "clinical"
                                     else "sample_types"]


def items_assigned(kind: str, item: str) -> dict:
    """{phenotype: design} for the phenotypes that collect this item."""
    return {p: design_of(kind, item, p)
            for p in st.session_state["scope"]["phenotypes"]
            if design_of(kind, item, p) is not None}


def items_for(kind: str, phenotype: str) -> list[str]:
    """Items of this kind collected for one phenotype, in scope order."""
    return [i for i in scope_items(kind)
            if design_of(kind, i, phenotype) is not None]


def editor_key(name: str) -> str:
    return f"{name}__{st.session_state['_editor_versions'].get(name, 0)}"


def editor_source(name: str, sig, build) -> pd.DataFrame:
    """Return a DataFrame object that is IDENTICAL across reruns.

    st.data_editor keeps a pending edit as a diff against the object it was
    handed; hand it a new object and the edit is thrown away. So the frame is
    built once, cached, and never reassigned. `_nav` is folded into the
    signature because editor state does not survive leaving the screen.
    """
    sig = (sig, st.session_state["_nav"])
    sigs, srcs = st.session_state["_editor_sigs"], st.session_state["_editor_srcs"]
    vers = st.session_state["_editor_versions"]
    if sigs.get(name) != sig:
        srcs[name] = build()
        sigs[name] = sig
        vers[name] = vers.get(name, 0) + 1
    return srcs[name]


def reset_editors():
    st.session_state["_editor_sigs"] = {}
    st.session_state["_editor_srcs"] = {}
    for k in list(st.session_state["_editor_versions"]):
        st.session_state["_editor_versions"][k] += 1


def carry_over(old: pd.DataFrame | None, new: pd.DataFrame,
               keys: list[str]) -> pd.DataFrame:
    """Preserve values the PI already typed when the row or column set changes."""
    if old is None or old.empty:
        return new
    shared = [c for c in new.columns if c in old.columns and c not in keys]
    if not shared or not all(k in old.columns for k in keys):
        return new
    merged = new.merge(old[keys + shared], on=keys, how="left", suffixes=("", "_old"))
    for c in shared:
        oldc = f"{c}_old"
        if oldc in merged.columns:
            merged[c] = merged[oldc].where(merged[oldc].notna(), merged[c])
            merged = merged.drop(columns=[oldc])
    return merged[new.columns]


# --------------------------------------------------------------------------
# Grid construction
# --------------------------------------------------------------------------

def value_columns(new_years: bool, followup: bool) -> list[str]:
    """Numeric columns for a grid.

    Completed study  -> Baseline N (+ Follow-up N when the item repeats).
    Ongoing study    -> Baseline N plus a projection per year: `new` for
                        participants recruited that year, `follow-up` for
                        repeat assessments on people already enrolled.
    """
    cols = ["Baseline N"]
    if is_ongoing():
        for y in plan_years():
            if new_years:
                cols.append(f"{y} new")
            if followup:
                cols.append(f"{y} follow-up")
    elif followup:
        cols.append("Follow-up N")
    return cols


def make_grid(rows: list[dict], value_cols: list[str],
              interval: bool, note: bool = True) -> pd.DataFrame:
    out = []
    for r in rows:
        row = dict(r)
        for c in value_cols:
            row[c] = 0
        if interval:
            row["Repeat interval"] = ""
        if note:
            row["Note"] = ""
        out.append(row)
    return pd.DataFrame(out)


def grid_config(key_cols: list[str], value_cols: list[str],
                interval: bool, note: bool = True) -> dict:
    cfg = {c: st.column_config.TextColumn(disabled=True) for c in key_cols}
    for c in value_cols:
        if c == "Baseline N":
            help_ = "Participants contributing this at their baseline visit."
        elif c.endswith("new"):
            help_ = "Participants newly recruited that year."
        elif c.endswith("follow-up") or c == "Follow-up N":
            help_ = "Already-enrolled participants contributing a repeat."
        else:
            help_ = None
        cfg[c] = st.column_config.NumberColumn(min_value=0, step=1, format="%d",
                                               help=help_)
    if interval:
        cfg["Repeat interval"] = st.column_config.TextColumn(
            help="How often it repeats, e.g. 'every 12 months', 'baseline + 24m'.")
    if note:
        cfg["Note"] = st.column_config.TextColumn(
            help="Anything we should know — which test, which subset, caveats.")
    return cfg


def numeric_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns
            if c == "Baseline N" or c == "Follow-up N"
            or c.endswith(" new") or c.endswith(" follow-up")]


def dna_prefill(phenotype: str, columns: list[str]) -> dict:
    """Starting values for a clinical grid, taken from the DNA plan.

    Most cohorts assess nearly everyone they genotype, so the DNA numbers are a
    better starting point than zero. Matching column names copy straight across.
    Follow-up columns get the CUMULATIVE enrolment available to be seen again
    that year — everyone recruited before it. Baseline 400 plus 200 new in 2026
    means 2027 follow-up starts at 600.
    """
    dna = st.session_state.get("dna")
    out = {c: 0 for c in columns}
    if dna is None or dna.empty:
        return out
    row = dna[dna["Phenotype"] == phenotype]
    if row.empty:
        return out
    row = row.iloc[0]
    base = int(row.get("Baseline N", 0) or 0)
    new_by_year = {y: int(row.get(f"{y} new", 0) or 0) for y in plan_years()}
    for c in columns:
        if c == "Baseline N":
            out[c] = base
        elif c == "Follow-up N":
            out[c] = base
        elif c.endswith(" new"):
            out[c] = new_by_year.get(int(c.split()[0]), 0)
        elif c.endswith(" follow-up"):
            year = int(c.split()[0])
            out[c] = base + sum(n for y, n in new_by_year.items() if y < year)
    return out


def apply_prefill(df: pd.DataFrame, kind: str, pheno: str, design: str,
                  vcols: list[str]) -> pd.DataFrame:
    """Seed still-empty rows from the DNA plan, once.

    Only rows that are entirely zero are touched, and only the first time the
    DNA numbers for that phenotype are non-zero. After that the PI owns the
    grid: a row they deliberately set to zero stays at zero, and later DNA
    edits do not overwrite what they typed.
    """
    key = f"{kind}||{pheno}||{design}"
    if key in st.session_state["_prefilled"]:
        return df
    pre = dna_prefill(pheno, vcols)
    if sum(pre.values()) == 0:
        return df
    for idx in df.index:
        if all(int(df.at[idx, c] or 0) == 0 for c in vcols):
            for c, v in pre.items():
                df.at[idx, c] = v
    st.session_state["_prefilled"].add(key)
    return df


def dna_totals() -> dict:
    """Total participants with DNA per phenotype — the coverage denominator."""
    dna = st.session_state["dna"]
    if dna is None or dna.empty:
        return {}
    cols = numeric_cols(dna)
    return {r["Phenotype"]: int(sum(int(r[c]) for c in cols))
            for _, r in dna.iterrows()}


# --------------------------------------------------------------------------
# Long-format export — this is what we store
# --------------------------------------------------------------------------

def melt_grid(df: pd.DataFrame, item_class: str,
              design_lookup) -> list[dict]:
    """One row per phenotype x item x period."""
    if df is None or df.empty:
        return []
    rows = []
    vcols = numeric_cols(df)
    periods = {}
    for c in vcols:
        if c == "Baseline N":
            periods.setdefault("baseline", {})["new"] = c
        elif c == "Follow-up N":
            periods.setdefault("baseline", {})["followup"] = c
        else:
            year, kind = c.rsplit(" ", 1)
            periods.setdefault(year, {})["new" if kind == "new" else "followup"] = c

    for _, r in df.iterrows():
        item = r["Item"]
        for period, cols in periods.items():
            n_new = int(r[cols["new"]]) if "new" in cols else 0
            n_fu = int(r[cols["followup"]]) if "followup" in cols else 0
            if n_new == 0 and n_fu == 0 and period != "baseline":
                continue
            rows.append({
                "phenotype": r["Phenotype"],
                "item_class": item_class,
                "item": item,
                "design": design_lookup(item),
                "period": period,
                "n_new": n_new,
                "n_followup": n_fu,
                "interval": r.get("Repeat interval", ""),
                "note": r.get("Note", ""),
            })
    return rows


def to_long() -> pd.DataFrame:
    meta = st.session_state["meta"]
    rows = []
    rows += melt_grid(st.session_state["dna"], "sample", lambda i: CROSS_SECTIONAL)
    for store_key, item_class in [("samples", "sample"), ("clinical", "clinical")]:
        for (pheno, design), df in st.session_state[store_key].items():
            rows += melt_grid(df, item_class, lambda i, d=design: d)
    if not rows:
        return pd.DataFrame()

    long = pd.DataFrame(rows)
    long["cohort_id"] = meta["cohort_id"]
    long["contact_name"] = meta["contact_name"]
    long["contact_email"] = meta["contact_email"]
    long["study_status"] = meta["study_status"]
    base = date.fromisoformat(meta["deadline"])

    def year_deadline(p):
        if p == "baseline":
            return meta["deadline"]
        try:
            return base.replace(year=int(p)).isoformat()
        except ValueError:            # 29 Feb in a non-leap year
            return date(int(p), base.month, 28).isoformat()

    long["deadline"] = long["period"].map(year_deadline)
    long["n_total"] = long["n_new"] + long["n_followup"]

    cols = ["cohort_id", "contact_name", "contact_email", "study_status",
            "phenotype", "item_class", "item", "design", "period", "deadline",
            "n_new", "n_followup", "n_total", "interval", "note"]
    return long[cols]


def validate(long: pd.DataFrame) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    meta = st.session_state["meta"]
    if not meta["cohort_id"].strip():
        errors.append("Cohort ID is missing.")
    if "@" not in meta["contact_email"]:
        errors.append("A contact email is required.")
    if long.empty or long["n_total"].sum() == 0:
        errors.append("No numbers entered yet.")
        return errors, warnings

    denom = dna_totals()
    if not denom or sum(denom.values()) == 0:
        errors.append("DNA numbers set the denominator for every coverage figure. "
                      "Enter them before submitting.")

    participants = (long[long["item"] != "DNA"]
                    .groupby(["phenotype", "item"])["n_new"].sum())
    for (pheno, item), n in participants.items():
        cap = denom.get(pheno, 0)
        if cap and n > cap:
            warnings.append(
                f"{pheno} / {item}: {int(n)} participants planned, more than the "
                f"{cap} with DNA. Fine for autopsy or clinical-only subsets — "
                f"otherwise check the numbers.")

    lng = long[long["design"] == LONGITUDINAL]
    if not lng.empty and lng["n_followup"].sum() == 0:
        warnings.append("Domains marked longitudinal have no follow-up numbers. "
                        "Either fill them in or mark those domains "
                        "cross-sectional on screen 2.")
    missing_interval = lng[(lng["n_followup"] > 0) &
                           (lng["interval"].astype(str).str.strip() == "")]
    if not missing_interval.empty:
        warnings.append(f"{len(missing_interval)} longitudinal rows have follow-up "
                        f"numbers but no repeat interval.")

    if is_ongoing() and len(plan_years()) == 0:
        warnings.append("Study is ongoing but the plan covers no years. Check the "
                        "final collection year on screen 1.")
    try:
        if date.fromisoformat(meta["deadline"]) < date.today():
            warnings.append("The first deadline is in the past.")
    except ValueError:
        errors.append("Deadline is not a valid date.")
    return errors, warnings


# --------------------------------------------------------------------------
# Screens
# --------------------------------------------------------------------------

def screen_cohort():
    st.header("1. Your cohort")
    st.caption("You fill this once. Everything after is filtered by what you "
               "tell us here.")
    c1, c2, c3 = st.columns(3)
    c1.text_input("GP2 cohort ID", key="w_cohort_id", placeholder="e.g. PPMI")
    c2.text_input("Contact name", key="w_contact_name",
                  help="Who we chase about transfers day to day.")
    c3.text_input("Contact email", key="w_contact_email",
                  placeholder="name@institution.edu")

    st.radio("Is recruitment or follow-up still running?",
             ["Ongoing", "Completed"], key="w_status", horizontal=True,
             help="Completed studies transfer everything once. Ongoing studies "
                  "project a number for each year until collection ends.")

    if st.session_state["w_status"] == "Ongoing":
        c1, c2 = st.columns(2)
        c1.number_input("Last year you expect to collect data",
                        min_value=date.today().year,
                        max_value=date.today().year + 20, key="w_final_year")
        c2.date_input("First transfer deadline", key="w_deadline")
        sync_from_widgets()
        years = plan_years()
        if years:
            st.info(f"You will project **{len(years)}** years: "
                    f"{years[0]}–{years[-1]}. Each item gets a number per year, "
                    f"so we know what to expect and when without asking you again.")
        if int(st.session_state["w_final_year"]) - years[0] + 1 > MAX_PLAN_YEARS \
                if years else False:
            st.warning(f"Only the first {MAX_PLAN_YEARS} years are collected here.")
    else:
        st.date_input("Transfer deadline", key="w_deadline")
        st.info("Single transfer. We will ask for the full dataset once.")

    sync_from_widgets()


def design_matrix(kind: str, items: list[str], phenos: list[str]) -> None:
    """One three-state control per item and phenotype.

    A single click sets the state directly, and because the three states are
    one control rather than two checkboxes there is no way to express a
    contradiction. Every cell starts at the item's default, so a PI whose arms
    were all assessed the same way changes nothing.
    """
    if not items or not phenos:
        return
    head = st.columns([2] + [1] * len(phenos))
    head[0].caption("")
    for col, p in zip(head[1:], phenos):
        col.caption(f"**{p}**")

    for item in items:
        cols = st.columns([2] + [1] * len(phenos))
        cols[0].markdown(f"**{item}**")
        options = [NOT_COLLECTED, "CS"] if is_locked(kind, item) \
            else [NOT_COLLECTED, "CS", "LT"]
        for col, p in zip(cols[1:], phenos):
            key = f"seg::{kind}::{item}::{p}"
            if key not in st.session_state:
                # Seeded from the store, never via `default=`. That avoids the
                # output-as-input trap and re-seeds after Streamlit garbage
                # collects the key while the user is on another screen.
                st.session_state[key] = SHORT[design_of(kind, item, p)]
            if st.session_state[key] not in options:
                st.session_state[key] = "CS"
            col.segmented_control(f"{item} · {p}", options, key=key,
                                  label_visibility="collapsed")
            chosen = LONG_LABEL.get(st.session_state[key] or NOT_COLLECTED)
            st.session_state["phenotype_designs"][kind].setdefault(item, {})[p] = chosen


def design_section(kind: str, label: str) -> None:
    scope = st.session_state["scope"]
    items = scope_items(kind)
    if not items:
        return
    phenos = scope["phenotypes"]
    if not phenos:
        st.warning("Select phenotypes above first.")
        return
    st.caption(f"**{NOT_COLLECTED}** not collected in that arm · **CS** once "
               f"per person · **LT** repeated over time. One click sets it. "
               f"Everything starts at a sensible default — change only what "
               f"differs.")
    design_matrix(kind, items, phenos)


def screen_scope():
    st.header("2. What exists in this cohort")
    st.caption("Tick only what you have. You will not be asked about anything else.")

    st.multiselect("Phenotypes in this cohort", PHENOTYPES, key="w_phenotypes")
    st.multiselect("Biosamples available for transfer, besides DNA",
                   OTHER_SAMPLE_TYPES, key="w_sample_types")
    st.multiselect("Clinical data domains collected", CLINICAL_DOMAINS,
                   key="w_domains")
    sync_from_widgets()
    scope = st.session_state["scope"]

    if scope["sample_types"]:
        st.subheader("How is each biosample collected?")
        design_section("sample", "biosamples")
    if scope["domains"]:
        st.subheader("How is each domain collected?")
        design_section("clinical", "domains")

    n_years = max(len(plan_years()), 1)
    per_item = 1 + (n_years if is_ongoing() else 0)
    cells = 0
    for p in scope["phenotypes"]:
        cells += per_item  # DNA
        for kind in ("sample", "clinical"):
            mine = items_for(kind, p)
            cells += per_item * len(mine)
            cells += sum(n_years if is_ongoing() else 1 for i in mine
                         if design_of(kind, i, p) == LONGITUDINAL)
    full = len(PHENOTYPES) * (1 + len(OTHER_SAMPLE_TYPES) + len(CLINICAL_DOMAINS)) * 2
    if scope["phenotypes"]:
        st.success(f"You will be asked to fill roughly **{cells}** cells. "
                   f"A flat form covering everything would ask for {full}.")


def screen_dna():
    st.header("3. DNA transfer plan")
    st.caption("Ask this first: DNA defines the cohort size everything else is "
               "measured against. One row per participant — no repeats.")
    scope = st.session_state["scope"]
    if not scope["phenotypes"]:
        st.warning("Select phenotypes on screen 2 first.")
        return

    vcols = value_columns(new_years=True, followup=False)
    key_cols = ["Phenotype", "Item"]

    def build():
        new = make_grid([{"Phenotype": p, "Item": "DNA"} for p in scope["phenotypes"]],
                        vcols, interval=False)
        spec = st.session_state.get("_demo_dna")
        if spec and st.session_state["dna"] is None:
            # Only ever fires on the first render after the demo button, when
            # the grid is genuinely empty. Years are resolved here rather than
            # at button time, since the plan years are not known until meta
            # has been synced.
            years = plan_years()
            for idx, r in new.iterrows():
                if r["Phenotype"] not in spec:
                    continue
                base, per_year = spec[r["Phenotype"]]
                new.at[idx, "Baseline N"] = base
                for n, year in enumerate(years):
                    if n < len(per_year) and f"{year} new" in new.columns:
                        new.at[idx, f"{year} new"] = per_year[n]
        return carry_over(st.session_state["dna"], new, key_cols)

    src = editor_source("dna", (tuple(scope["phenotypes"]), tuple(vcols)), build)
    edited = st.data_editor(src, hide_index=True, width="stretch",
                            key=editor_key("dna"),
                            column_config=grid_config(key_cols, vcols, False))
    st.session_state["dna"] = edited

    if is_ongoing():
        st.caption("Baseline is everyone already recruited. Each year column is "
                   "how many NEW participants you expect to add that year.")
    totals = dna_totals()
    cols = st.columns(max(len(totals), 1))
    for c, (pheno, n) in zip(cols, totals.items()):
        c.metric(pheno, n)
    st.metric("Total participants with DNA", sum(totals.values()))


def item_screen(kind: str, header: str, caption: str, empty_msg: str,
                store_key: str, prefill: bool) -> None:
    """Screens 4 and 5: per-phenotype grids, split cross-sectional / longitudinal."""
    st.header(header)
    scope = st.session_state["scope"]
    if not scope["phenotypes"] or not scope_items(kind):
        st.info(empty_msg)
        st.session_state[store_key] = {}
        return

    st.caption(caption)
    if prefill and st.session_state.get("dna") is not None:
        st.info(PREFILL_NOTE[kind])

    xs_cols = value_columns(new_years=True, followup=False)
    lg_cols = value_columns(new_years=True, followup=True)
    key_cols = ["Phenotype", "Item"]
    store = {}

    for pheno in scope["phenotypes"]:
        mine = items_for(kind, pheno)
        if not mine:
            continue
        xs = [i for i in mine if design_of(kind, i, pheno) == CROSS_SECTIONAL]
        lg = [i for i in mine if design_of(kind, i, pheno) == LONGITUDINAL]
        with st.expander(pheno, expanded=(pheno == scope["phenotypes"][0])):
            for design, items, vcols, interval in [
                (CROSS_SECTIONAL, xs, xs_cols, False),
                (LONGITUDINAL, lg, lg_cols, True),
            ]:
                if not items:
                    continue
                st.markdown(f"**{design}**")
                rows = [{"Phenotype": pheno, "Item": i} for i in items]
                name = f"{kind}::{pheno}::{design}"

                def build(rows=rows, vcols=vcols, interval=interval,
                          pheno=pheno, design=design):
                    new = make_grid(rows, vcols, interval=interval)
                    merged = carry_over(
                        st.session_state[store_key].get((pheno, design)),
                        new, key_cols)
                    if prefill:
                        merged = apply_prefill(merged, kind, pheno, design, vcols)
                    return merged

                src = editor_source(name, (tuple(items), tuple(vcols)), build)
                out = st.data_editor(src, hide_index=True, width="stretch",
                                     key=editor_key(name),
                                     column_config=grid_config(key_cols, vcols,
                                                               interval))
                store[(pheno, design)] = out
                needs = [i for i in items if i in NEEDS_SPECIFYING]
                if needs:
                    st.caption("Use the note column to say which instrument "
                               "for: " + ", ".join(needs) + ".")

    st.session_state[store_key] = store


def screen_samples():
    item_screen(
        "sample", "4. Other biosamples",
        "Counts are participants, not tubes. Cross-sectional means one "
        "collection per person; longitudinal adds follow-up columns and a "
        "repeat interval.",
        "Select phenotypes and biosamples on screen 2 first.",
        "samples", prefill=True)


def screen_clinical():
    item_screen(
        "clinical", "5. Clinical data",
        "Counts are participants, not visits. One section per phenotype.",
        "Select phenotypes and clinical domains on screen 2 first.",
        "clinical", prefill=True)


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

    denom = dna_totals()
    c1, c2, c3 = st.columns(3)
    c1.metric("Participants with DNA", sum(denom.values()))
    c2.metric("Planned participants (all items)", int(long["n_new"].sum()))
    c3.metric("Planned follow-up assessments", int(long["n_followup"].sum()))

    if is_ongoing() and plan_years():
        st.subheader("Plan by year")
        by_year = (long.groupby("period")[["n_new", "n_followup"]].sum()
                   .rename(columns={"n_new": "New participants",
                                    "n_followup": "Follow-up"}))
        st.dataframe(by_year, width="stretch")

    st.subheader("Coverage against DNA")
    cov = long[long["item"] != "DNA"].copy()
    if not cov.empty and denom:
        agg = cov.groupby(["item", "phenotype"])["n_new"].sum().reset_index()
        agg["pct"] = (100 * agg["n_new"]
                      / agg["phenotype"].map(denom).replace(0, float("nan"))
                      .astype(float)).round(0)
        st.dataframe(agg.pivot(index="item", columns="phenotype", values="pct")
                     .style.format("{:.0f}%", na_rep="—"), width="stretch")
        st.caption("Coverage is derived, not asked — participants planned for "
                   "each item against the DNA total for that phenotype.")

    st.subheader("What gets stored")
    st.dataframe(long, hide_index=True, width="stretch")
    st.caption("Long format: one row per phenotype x item x period. Adding a "
               "domain, a phenotype or a year never changes the schema.")

    c1, c2 = st.columns(2)
    cid = st.session_state["meta"]["cohort_id"] or "draft"
    c1.download_button("Download plan (CSV)", long.to_csv(index=False),
                       file_name=f"transfer_plan_{cid}.csv", mime="text/csv")
    scope = dict(st.session_state["scope"])
    snapshot = {"meta": st.session_state["meta"],
                "scope": scope,
                "designs": {k: {i: design_of(k, i) for i in scope_items(k)}
                            for k in ("sample", "clinical")},
                "phenotype_designs": {k: {i: items_assigned(k, i)
                                          for i in scope_items(k)}
                                      for k in ("sample", "clinical")},
                "plan": long.to_dict("records")}
    c2.download_button("Save draft (JSON)", json.dumps(snapshot, indent=2, default=str),
                       file_name=f"transfer_plan_{cid}.json",
                       mime="application/json")


def screen_gp2_view():
    st.header("GP2 tracking view")
    st.caption("Not shown to PIs. Compares the plan against what has arrived.")
    long = to_long()
    if long.empty:
        st.info("Fill in a plan first.")
        return

    promised = (long.groupby(["phenotype", "item", "design"])
                [["n_new", "n_followup"]].sum().reset_index())
    pairs = [(r.phenotype, r.item) for r in promised.itertuples()]

    def build():
        return pd.DataFrame([{
            "Phenotype": p, "Item": i,
            "Received participants": int(
                st.session_state["received"].get(f"{p}||{i}", (0, 0))[0]),
            "Received follow-up": int(
                st.session_state["received"].get(f"{p}||{i}", (0, 0))[1]),
        } for p, i in pairs])

    st.write("Enter what has actually arrived. PIs never see or edit this.")
    src = editor_source("received", tuple(pairs), build)
    edited = st.data_editor(
        src, hide_index=True, width="stretch", key=editor_key("received"),
        column_config={
            "Phenotype": st.column_config.TextColumn(disabled=True),
            "Item": st.column_config.TextColumn(disabled=True),
            "Received participants": st.column_config.NumberColumn(
                min_value=0, step=1, format="%d"),
            "Received follow-up": st.column_config.NumberColumn(
                min_value=0, step=1, format="%d"),
        })
    st.session_state["received"] = {
        f"{r.Phenotype}||{r.Item}": (int(r._3), int(r._4))
        for r in edited.itertuples()}

    # Promised lives outside the editor: it is derived from the plan, so keeping
    # it in the grid would reset the receiving numbers whenever the plan changed.
    t = promised.rename(columns={"phenotype": "Phenotype", "item": "Item",
                                 "design": "Design",
                                 "n_new": "Planned participants",
                                 "n_followup": "Planned follow-up"})
    rec = {f"{r.Phenotype}||{r.Item}": (r._3, r._4) for r in edited.itertuples()}
    t["Received participants"] = [rec.get(f"{r.Phenotype}||{r.Item}", (0, 0))[0]
                                  for r in t.itertuples()]
    t["Received follow-up"] = [rec.get(f"{r.Phenotype}||{r.Item}", (0, 0))[1]
                               for r in t.itertuples()]
    t["Participant %"] = (100 * t["Received participants"]
                          / t["Planned participants"].replace(0, float("nan"))
                          .astype(float)).round(0)
    t["Follow-up %"] = (100 * t["Received follow-up"]
                        / t["Planned follow-up"].replace(0, float("nan"))
                        .astype(float)).round(0)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Participants planned", int(t["Planned participants"].sum()))
    c2.metric("Participants received", int(t["Received participants"].sum()))
    c3.metric("Follow-up planned", int(t["Planned follow-up"].sum()))
    c4.metric("Follow-up received", int(t["Received follow-up"].sum()))

    st.subheader("By study design")
    by_design = t.groupby("Design")[["Planned participants", "Received participants",
                                     "Planned follow-up", "Received follow-up"]].sum()
    by_design["Participant %"] = (100 * by_design["Received participants"]
                                  / by_design["Planned participants"]
                                  .replace(0, float("nan")).astype(float)).round(0)
    by_design["Follow-up %"] = (100 * by_design["Received follow-up"]
                                / by_design["Planned follow-up"]
                                .replace(0, float("nan")).astype(float)).round(0)
    st.dataframe(by_design, width="stretch")
    st.caption("Longitudinal items can look complete on participants while the "
               "repeat assessments are missing — which is why the two are "
               "tracked separately.")

    st.subheader("Detail")
    st.dataframe(t, hide_index=True, width="stretch")

    overdue = date.fromisoformat(st.session_state["meta"]["deadline"]) < date.today()
    lag = t[(t["Participant %"].fillna(0) < NUDGE_THRESHOLD)
            | ((t["Planned follow-up"] > 0)
               & (t["Follow-up %"].fillna(0) < NUDGE_THRESHOLD))]
    if overdue and not lag.empty:
        st.error(f"Past deadline and {len(lag)} items are below "
                 f"{NUDGE_THRESHOLD}% on participants or follow-up.")
        st.dataframe(lag, hide_index=True, width="stretch")
    elif not lag.empty:
        st.info(f"{len(lag)} items below {NUDGE_THRESHOLD}%, but the deadline has "
                f"not passed. No nudge yet.")
    else:
        st.success("Nothing below the nudge threshold.")
    st.caption(f"Only completed, released material is visible to us, so partial "
               f"percentages before a deadline are expected. The nudge fires on "
               f"overdue items below {NUDGE_THRESHOLD}%, not on anything short "
               f"of 100%.")


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


def load_demo():
    reset_editors()
    st.session_state["w_cohort_id"] = "DEMO-COHORT"
    st.session_state["w_contact_name"] = "A. Example"
    st.session_state["w_contact_email"] = "a.example@institution.edu"
    st.session_state["w_status"] = "Ongoing"
    st.session_state["w_final_year"] = date.today().year + 2
    st.session_state["w_phenotypes"] = ["PD", "Control", "Prodromal"]
    st.session_state["w_sample_types"] = ["blood", "plasma", "csf"]
    st.session_state["w_domains"] = [
        "Demographics", "Diagnosis (baseline)", "Diagnosis change",
        "MDS-UPDRS3", "MoCA", "SCOPA-AUT", "Mortality / living status"]
    st.session_state["designs"] = {
        "clinical": {"MDS-UPDRS3": LONGITUDINAL, "MoCA": LONGITUDINAL,
                     "SCOPA-AUT": CROSS_SECTIONAL,
                     "Diagnosis change": LONGITUDINAL,
                     "Mortality / living status": LONGITUDINAL},
        "sample": {"blood": LONGITUDINAL, "plasma": LONGITUDINAL,
                   "csf": CROSS_SECTIONAL}}
    for k in [k for k in st.session_state if str(k).startswith("seg::")]:
        del st.session_state[k]
    st.session_state["phenotype_designs"] = {"clinical": {}, "sample": {}}
    st.session_state["dna"] = None
    st.session_state["_demo_dna"] = DEMO_DNA
    st.session_state["samples"] = {}
    st.session_state["clinical"] = {}
    st.session_state["received"] = {}
    st.session_state["_prefilled"] = set()


def sidebar():
    st.sidebar.title("GP2 transfer plan")
    st.sidebar.caption("Prototype for discussion — not a live collection.")
    step = st.sidebar.radio("Step", list(STEPS), label_visibility="collapsed")

    st.sidebar.divider()
    up = st.sidebar.file_uploader("Resume a saved draft", type="json")
    if up is not None and not st.session_state.get("_loaded"):
        data = json.load(up)
        m, sc = data.get("meta", {}), data.get("scope", {})
        for wk, src, field in [
            ("w_cohort_id", m, "cohort_id"), ("w_contact_name", m, "contact_name"),
            ("w_contact_email", m, "contact_email"), ("w_status", m, "study_status"),
            ("w_final_year", m, "final_collection_year"),
            ("w_phenotypes", sc, "phenotypes"),
            ("w_sample_types", sc, "sample_types"), ("w_domains", sc, "domains"),

        ]:
            if field in src:
                st.session_state[wk] = src[field]
        if "deadline" in m:
            st.session_state["w_deadline"] = date.fromisoformat(m["deadline"])
        for store in ("designs", "phenotype_designs"):
            loaded = data.get(store, {})
            st.session_state[store] = {"clinical": loaded.get("clinical", {}),
                                       "sample": loaded.get("sample", {})}
        reset_editors()
        st.session_state["_loaded"] = True
        st.sidebar.success("Draft loaded.")

    if st.sidebar.button("Load an example cohort"):
        load_demo()
        st.rerun()

    st.sidebar.divider()
    st.sidebar.caption(
        "Real deployment needs a per-cohort tokenised link instead of a login, "
        "and a database behind it. Neither is in this prototype.")
    return step


def main():
    init_state()
    persist_widget_state()
    sync_from_widgets()
    step = sidebar()
    if st.session_state["_last_step"] != step:
        st.session_state["_nav"] += 1
        st.session_state["_last_step"] = step
    STEPS[step]()


if __name__ == "__main__":
    main()
