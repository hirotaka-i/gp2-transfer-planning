"""
GP2 Transfer Plan — Stage 2 prototype

Run after the DTA/MTA is being drawn up. Turns the Stage 1 Site Interest answers
into a firm schedule: which GP2 data dictionary instruments will be transferred,
for which phenotypes, how many participants, and by when.

Stage 1 answered at construct level ("we collect depression data, longitudinally").
Stage 2 answers at instrument level ("GDS-15, PD and Prodromal, 400 at baseline").
The link between the two is many-to-many, so Stage 1 SUGGESTS instruments — it
never decides them.

Run:  streamlit run transfer_plan_stage2_app.py
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import report

st.set_page_config(page_title="GP2 Transfer Plan", layout="wide")

VOCAB = Path(__file__).parent / "vocab"

CROSS_SECTIONAL, LONGITUDINAL, NOT_COLLECTED = "Cross-sectional", "Longitudinal", "None"
SHORT = {CROSS_SECTIONAL: "CS", LONGITUDINAL: "LT", None: NOT_COLLECTED}
LONG_LABEL = {"CS": CROSS_SECTIONAL, "LT": LONGITUDINAL, NOT_COLLECTED: None}

PHENOTYPES = [
    "PD", "Control", "PSP", "DLB", "MSA", "CBD/CBS", "FTD", "AD", "Mix",
    "VaD", "VaPD", "Population Control", "Undetermined-MCI",
    "Undetermined-Dementia", "Prodromal", "LBD", "Other",
]

# Which biosample the DNA count comes from when the cohort has no extracted DNA.
DNA_SOURCE_SAMPLE = {"Blood": "blood", "Saliva": "saliva",
                     "Brain": "brain (post-mortem)"}

NUDGE_THRESHOLD = 50
MAX_PLAN_YEARS = 10

def load_vocab():
    """Read the vocabulary every run — see the Stage 1 app for why it is not cached."""
    l1 = pd.read_csv(VOCAB / "gp2_L1_constructs.csv")
    l2 = pd.read_csv(VOCAB / "gp2_L2_to_L1.csv")
    tags = pd.read_csv(VOCAB / "gp2_L3_item_tags.csv")
    tags = tags[tags.extra_l1.notna() & (tags.extra_l1 != "")]
    bios = pd.read_csv(VOCAB / "gp2_biosamples.csv")
    l2 = l2[~l2.primary_l1.isin(["EXCLUDE"])]
    return l1, l2, tags, bios


# ==========================================================================
# THE ONE PLACE TO EDIT
#
# What Stage 2 offers, per construct. Everything else is derived from the
# vocabulary CSVs, so this table is the only hand-maintained mapping.
#
#   (construct, label, [data dictionary modalities], default_on, note)
#
# `label` is what the cohort sees and what ends up in the plan. Several
# dictionary modalities can collapse into one label — nobody plans a transfer
# of "MDS-UPDRS Part III" separately from Part II. If the dictionary renames or
# splits a modality, only the middle column changes, and `vocab_check()` below
# reports the mismatch on screen rather than failing silently.
# ==========================================================================

INSTRUMENT_GROUPS = [
    # -- History
    ("Demographics", "Demographics", ["Demographics"], True, ""),
    ("Family history", "Family history",
     ["Family history", "Known_relatedness"], True, ""),
    ("Medical history", "Medical history", ["Medical History"], True, ""),
    ("Medication", "Current medication status", ["Current Medication Status"],
     True, "current drugs and LEDD"),
    ("Lifestyle", "Lifestyle questions", ["Lifestyle"], False, ""),
    ("Lifestyle", "MERQ-PD-B", ["MERQ-PD-B"], False,
     "exposure questionnaire — also covers environment and head injury"),
    ("Lifestyle", "Modified MERQ-PD", ["Modified MERQ-PD"], False,
     "exposure questionnaire — also covers occupation and head injury"),
    ("Lifestyle", "PD RFQ-U", ["PD RFQ-U"], False,
     "risk factor questionnaire — smoking, caffeine, alcohol, NSAIDs"),
    ("Environment", "MERQ-PD-B", ["MERQ-PD-B"], False,
     "pesticides, solvents, welding, heavy metals"),
    ("Environment", "Modified MERQ-PD", ["Modified MERQ-PD"], False,
     "occupation history and exposures"),
    ("Environment", "PD RFQ-U", ["PD RFQ-U"], False, ""),
    ("Head trauma", "MERQ-PD-B", ["MERQ-PD-B"], False, "head injury section"),
    ("Head trauma", "Modified MERQ-PD", ["Modified MERQ-PD"], False,
     "head injury section, with age and count"),
    ("Head trauma", "PD RFQ-U", ["PD RFQ-U"], False, "concussion questions"),

    # -- Diagnosis and course
    ("Diagnosis", "Diagnosis", ["Diagnosis"], True,
     "primary diagnosis, certainty, diagnosis change, prodromal markers"),
    ("Diagnosis", "MDS diagnostic criteria checklist", ["MDS_Diagnostic_criteria"],
     False, "the full item-by-item checklist — few cohorts record this"),
    ("Disease course / complications", "PD history", ["PD History"], True,
     "age at first motor symptom, and age at reaching H&Y 3, dyskinesia, "
     "motor fluctuation, levodopa and agonist start"),
    ("Mortality / vital status", "Mortality / vital status", ["Mortality"], True,
     "alive/dead with date and age at censoring"),

    # -- Clinical assessment
    ("UPDRS (MDS / original)", "MDS-UPDRS",
     ["MDS-UPDRS Part I", "MDS-UPDRS Part II", "MDS-UPDRS Part III",
      "MDS-UPDRS Part IV"], True, "all four parts"),
    ("UPDRS (MDS / original)", "UPDRS (original)",
     ["UPDRS Part I", "UPDRS Part II", "UPDRS Part III", "UPDRS Part IV"], False,
     "the pre-MDS version, all four parts"),
    ("Motor staging (H&Y)", "Hoehn & Yahr", ["Hoehn and Yahr"], True, ""),
    ("Global severity (CISI-PD)", "CISI-PD", ["CISI-PD"], True, ""),
    ("Cognition", "MoCA", ["MoCA"], True, ""),
    ("Cognition", "MMSE", ["MMSE"], False, ""),
    ("Cognition", "SCOPA-COG", ["SCOPA-COG"], False, ""),
    ("Cognition", "Symbol Digit Modalities", ["SDM"], False, ""),
    ("Cognition", "IDEA screening questionnaire", ["IDEA Screening Questionnaire"],
     False, "dementia screening designed for low-literacy settings"),
    ("ADL", "Schwab & England", ["Schwab England ADL"], True, ""),
    ("ADL", "Modified Rankin Scale", ["Rankin Scale"], False, ""),
    ("QOL", "PDQ-39", ["PDQ-39"], True, ""),
    ("QOL", "PDQ-8", ["PDQ-8"], False, "the short form"),
    ("Autonomic", "SCOPA-AUT", ["SCOPA-AUT"], True, ""),
    ("Autonomic", "Orthostatic hypotension", ["Orthostatic hypotension"], False,
     "supine / sitting / standing blood pressure and heart rate"),
    ("Daytime sleepiness", "Epworth Sleepiness Scale", ["Epworth Sleepiness Scale"],
     True, ""),
    ("RBD", "RBD diagnosis (polysomnography)", ["RBD Diagnosis"], True,
     "PSG-confirmed, not questionnaire-based"),
    ("RBD", "RBD Screening Questionnaire", ["RBD Screening Questionnaire"], False,
     "RBDSQ"),
    ("RBD", "RBD single-question screen", ["RBD Single-Question Screen"], False, ""),
    ("Depression", "GDS-15", ["Geriatric Depression Scale: Short Form"], True, ""),
    ("Impulse control disorder", "QUIP-RS", ["QUIP-RS"], True, ""),
    ("Impulse control disorder", "QUIP-CS", ["QUIP-CS"], False, "the short form"),
    ("Pain", "King's PD pain scale", ["King's PD pain scale"], True, ""),
    ("Olfaction", "Smell test", ["Olfactory test"], True,
     "the test name and version are fields inside it, so any test fits"),
    ("Vital signs", "Vitals", ["Vitals"], True,
     "height, weight, BMI, heart rate, blood pressure"),

    # -- Disease-specific. Defaults follow the phenotypes under agreement.
    ("Disease-specific scales", "MDS-PSP criteria", ["MDS-PSP"], False, "PSP"),
    ("Disease-specific scales", "PSP-RS",
     ["PSP-RS", "PSP-RS part I", "PSP-RS part II", "PSP-RS part III",
      "PSP-RS part IV", "PSP-RS part V", "PSP-RS part VI"], False, "PSP"),
    ("Disease-specific scales", "PSP-CDS", ["PSP-CDS"], False, "PSP"),
    ("Disease-specific scales", "MDS-MSA criteria", ["MDS-MSA"], False, "MSA"),
    ("Disease-specific scales", "UMSARS",
     ["UMSARS part I", "UMSARS part II", "UMSARS part III", "UMSARS part IV"],
     False, "MSA"),
    ("Disease-specific scales", "CBD/CBS-Armstrong criteria",
     ["CBD-Armstrong", "CBS-Armstrong"], False, "CBD/CBS"),
    ("Disease-specific scales", "CBFS", ["CBFS A", "CBFS B"], False, "CBD/CBS"),
    ("Disease-specific scales", "DLB criteria", ["DLB"], False, "DLB / LBD"),

    # -- Biomarker, imaging, neuropathology
    ("SAA", "Alpha-synuclein SAA", ["SAA Positivity"], True, ""),
    ("DAT-SPECT", "DAT scan", ["DAT_imaging"], True, ""),
    ("MIBG", "Cardiac MIBG", ["MIBG_imaging"], True, ""),
    ("Pathology", "Neuropathology", ["Pathology"], True,
     "autopsy diagnosis, Braak staging, brain weight"),
]

# Which disease-specific options are ticked for which phenotype under agreement.
DISEASE_SPECIFIC_BY_PHENOTYPE = {
    "PSP": ["MDS-PSP criteria", "PSP-RS"],
    "MSA": ["MDS-MSA criteria", "UMSARS"],
    "CBD/CBS": ["CBD/CBS-Armstrong criteria"],
    "DLB": ["DLB criteria"], "LBD": ["DLB criteria"],
}

# A PSP rating scale is not "cross-sectional in the PD arm", it is not collected
# there at all — so these open at None outside their own phenotype.
SCALE_PHENOTYPES = {
    "MDS-PSP criteria": {"PSP"}, "PSP-RS": {"PSP"}, "PSP-CDS": {"PSP"},
    "MDS-MSA criteria": {"MSA"}, "UMSARS": {"MSA"},
    "CBD/CBS-Armstrong criteria": {"CBD/CBS"}, "CBFS": {"CBD/CBS"},
    "DLB criteria": {"DLB", "LBD"},
}

# Free text belongs everywhere except where the construct IS the instrument.
NO_OTHER = {"Diagnosis", "Family history"}

# For measures that belong to no GP2 domain at all.
OTHER_DOMAIN = "Other"

# Reported in Stage 1 but never planned here: dropped on purpose.
NOT_OFFERED_IN_STAGE2 = {"Blood tests", "CT", "MRI", "PET"}


def groups_for(construct: str) -> list[dict]:
    return [{"construct": c, "label": lab, "modalities": mods,
             "default": dflt, "note": note}
            for c, lab, mods, dflt, note in INSTRUMENT_GROUPS if c == construct]


def unit_modalities(label: str) -> list[str]:
    for _, lab, mods, _, _ in INSTRUMENT_GROUPS:
        if lab == label:
            return mods
    return []


def unit_constructs(label: str) -> list[str]:
    return sorted({c for c, lab, _, _, _ in INSTRUMENT_GROUPS if lab == label})


def default_on(g: dict, phenotypes: list[str]) -> bool:
    if g["construct"] == "Disease-specific scales":
        wanted = {lab for p in phenotypes
                  for lab in DISEASE_SPECIFIC_BY_PHENOTYPE.get(p, [])}
        return g["label"] in wanted
    return g["default"]


def vocab_check(l2) -> tuple[list[str], list[str]]:
    """Keep this table and the data dictionary honest about each other.

    Returns (modalities this table names that the dictionary does not have,
             dictionary modalities no Stage 2 option would ever transfer).
    """
    known = set(l2.l2_modality)
    named = {m for _, _, mods, _, _ in INSTRUMENT_GROUPS for m in mods}
    offered_constructs = {c for c, _, _, _, _ in INSTRUMENT_GROUPS}
    unreachable = sorted(
        m for m in known - named
        if l2[l2.l2_modality == m].primary_l1.iloc[0] in offered_constructs)
    return sorted(named - known), unreachable


# --------------------------------------------------------------------------
# State. Same two Streamlit traps as the other apps.
#   1. A widget's output is never fed back as its own value=/default=.
#   2. Keyed widget state is discarded when not rendered, so plain widgets are
#      re-assigned each run and editors rebuild on navigation via _nav.
# --------------------------------------------------------------------------

DEFAULT_META = {
    "cohort_id": "", "contact_name": "", "contact_email": "",
    "study_status": "Ongoing", "final_collection_year": date.today().year + 3,
    "deadline": date(date.today().year, 12, 31).isoformat(),
}
WIDGET_KEYS = ["w_cohort_id", "w_contact_name", "w_contact_email", "w_status",
               "w_final_year", "w_deadline", "w_phenotypes", "w_samples",
               "w_extra_domains"]


def init_state():
    st.session_state.setdefault("meta", dict(DEFAULT_META))
    st.session_state.setdefault("stage1", None)
    st.session_state.setdefault("designs", {})      # modality -> {phenotype: design|None}
    st.session_state.setdefault("selected", [])     # option labels, survives navigation
    st.session_state.setdefault("extras", [])       # [{domain, measure}]
    st.session_state.setdefault("_inst_init", False)
    st.session_state.setdefault("dna", None)
    st.session_state.setdefault("samples", {})      # (phenotype, design) -> DataFrame
    st.session_state.setdefault("clinical", {})
    st.session_state.setdefault("_prefilled", set())
    st.session_state.setdefault("_editor_sigs", {})
    st.session_state.setdefault("_editor_srcs", {})
    st.session_state.setdefault("_editor_versions", {})
    st.session_state.setdefault("_nav", 0)
    st.session_state.setdefault("_last_step", None)

    st.session_state.setdefault("w_cohort_id", "")
    st.session_state.setdefault("w_contact_name", "")
    st.session_state.setdefault("w_contact_email", "")
    st.session_state.setdefault("w_status", "Ongoing")
    st.session_state.setdefault("w_final_year", DEFAULT_META["final_collection_year"])
    st.session_state.setdefault("w_deadline", date.fromisoformat(DEFAULT_META["deadline"]))
    st.session_state.setdefault("w_phenotypes", [])
    st.session_state.setdefault("w_samples", [])
    st.session_state.setdefault("w_extra_domains", [])


def persist_widget_state():
    for k in WIDGET_KEYS:
        if k in st.session_state:
            st.session_state[k] = st.session_state[k]


def sync_from_widgets():
    st.session_state["meta"].update({
        "cohort_id": st.session_state["w_cohort_id"],
        "contact_name": st.session_state["w_contact_name"],
        "contact_email": st.session_state["w_contact_email"],
        "study_status": st.session_state["w_status"],
        "final_collection_year": int(st.session_state["w_final_year"]),
        "deadline": st.session_state["w_deadline"].isoformat(),
    })


def is_ongoing() -> bool:
    return st.session_state["meta"]["study_status"] == "Ongoing"


def plan_years() -> list[int]:
    if not is_ongoing():
        return []
    m = st.session_state["meta"]
    start = date.fromisoformat(m["deadline"]).year
    end = int(m["final_collection_year"])
    return list(range(start, min(end, start + MAX_PLAN_YEARS - 1) + 1))


def phenos() -> list[str]:
    return list(st.session_state["w_phenotypes"])


def extra_units() -> list[dict]:
    """Free-text measures, as {label, domain}.

    Named "<Domain> — <measure>" rather than "Other — <Domain>": by the time
    these reach the count grids and the PDF, what matters is which questionnaire
    it is, not that it came from a free-text box. A domain can carry several.
    """
    out, seen = [], set()
    for e in st.session_state["extras"]:
        d = str(e.get("domain", "") or "").strip()
        m = str(e.get("measure", "") or "").strip()
        if not d or not m:
            continue
        label = f"{d} — {m}"
        if label in seen:
            continue
        seen.add(label)
        out.append({"label": label, "domain": d})
    return out


def selected_instruments() -> list[str]:
    """What will be transferred, as labels, in table order.

    Read from a plain list, not from the checkbox widgets: Streamlit discards
    keyed widget state once the widget stops being rendered, so the tickboxes
    are gone by the time the review screen asks what was selected.
    """
    chosen = set(st.session_state["selected"])
    seen, out = set(), []
    for _, lab, _, _, _ in INSTRUMENT_GROUPS:
        if lab in chosen and lab not in seen:
            seen.add(lab)
            out.append(lab)
    return out + [u["label"] for u in extra_units()]


# ---- Stage 1 inheritance ---------------------------------------------------

def stage1_design(construct: str, phenotype: str) -> str | None:
    s1 = st.session_state["stage1"]
    if not s1:
        return None
    return s1.get("designs", {}).get(construct, {}).get(phenotype)


def unit_constructs_of(label: str) -> list[str]:
    for u in extra_units():
        if u["label"] == label:
            return [] if u["domain"] == OTHER_DOMAIN else [u["domain"]]
    return unit_constructs(label)


def seed_design(label: str, phenotype: str) -> str | None:
    """Inherit CS/LT from whichever Stage 1 construct this option serves.

    An option can serve several constructs — the three exposure questionnaires
    each cover lifestyle, environment and head trauma — so the strongest answer
    wins. An option feeding one longitudinal construct is treated as longitudinal.
    """
    scope = SCALE_PHENOTYPES.get(label)
    if scope and phenotype not in scope:
        return None

    s1 = st.session_state["stage1"]
    if not s1:
        return CROSS_SECTIONAL
    # Typing a measure into the free-text table is an explicit statement that it
    # is collected, so it never opens at None — even where Stage 1 said the
    # domain was absent. The review screen reports the disagreement instead.
    if any(u["label"] == label for u in extra_units()):
        return CROSS_SECTIONAL

    known = s1.get("designs", {})
    cons = [c for c in unit_constructs_of(label) if c in known]
    if not cons:
        # Stage 1 never asked about this domain — added deliberately here.
        return CROSS_SECTIONAL
    answers = [known[c].get(phenotype) for c in cons]
    if LONGITUDINAL in answers:
        return LONGITUDINAL
    if CROSS_SECTIONAL in answers:
        return CROSS_SECTIONAL
    return None


def design_of(label: str, phenotype: str) -> str | None:
    cell = st.session_state["designs"].get(label, {})
    if phenotype in cell:
        return cell[phenotype]
    return seed_design(label, phenotype)


def items_for(phenotype: str) -> list[str]:
    return [m for m in selected_instruments() if design_of(m, phenotype) is not None]
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



# --------------------------------------------------------------------------
# Long-format export
# --------------------------------------------------------------------------

def melt_grid(df: pd.DataFrame, item_class: str, design: str) -> list[dict]:
    """One row per phenotype x item x period."""
    if df is None or df.empty:
        return []
    rows, vcols = [], numeric_cols(df)
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
        for period, cols in periods.items():
            n_new = int(r[cols["new"]]) if "new" in cols else 0
            n_fu = int(r[cols["followup"]]) if "followup" in cols else 0
            if n_new == 0 and n_fu == 0 and period != "baseline":
                continue
            rows.append({"phenotype": r["Phenotype"], "item_class": item_class,
                         "item": r["Item"],
                         "dictionary_modalities": "; ".join(
                             unit_modalities(r["Item"])) or "",
                         "design": design, "period": period,
                         "n_new": n_new, "n_followup": n_fu,
                         "interval": r.get("Repeat interval", ""),
                         "note": r.get("Note", "")})
    return rows


def to_long() -> pd.DataFrame:
    meta = st.session_state["meta"]
    rows = melt_grid(st.session_state["dna"], "sample", CROSS_SECTIONAL)
    for key, cls in [("samples", "sample"), ("clinical", "instrument")]:
        for (pheno, design), df in st.session_state[key].items():
            rows += melt_grid(df, cls, design)
    if not rows:
        return pd.DataFrame()

    long = pd.DataFrame(rows)
    base = date.fromisoformat(meta["deadline"])

    def year_deadline(p):
        if p == "baseline":
            return meta["deadline"]
        try:
            return base.replace(year=int(p)).isoformat()
        except ValueError:                      # 29 Feb in a non-leap year
            return date(int(p), base.month, 28).isoformat()

    long["deadline"] = long["period"].map(year_deadline)
    long["n_total"] = long["n_new"] + long["n_followup"]
    for k, v in [("cohort_id", meta["cohort_id"]), ("contact_name", meta["contact_name"]),
                 ("contact_email", meta["contact_email"]),
                 ("study_status", meta["study_status"])]:
        long[k] = v
    cols = ["cohort_id", "contact_name", "contact_email", "study_status",
            "phenotype", "item_class", "item", "dictionary_modalities", "design",
            "period", "deadline", "n_new", "n_followup", "n_total", "interval",
            "note"]
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
    part = (long[long["item"] != "DNA"].groupby(["phenotype", "item"])["n_new"].sum())
    for (pheno, item), n in part.items():
        cap = denom.get(pheno, 0)
        if cap and n > cap:
            warnings.append(f"{pheno} / {item}: {int(n)} participants planned, more "
                            f"than the {cap} with DNA. Fine for autopsy or "
                            f"clinical-only subsets — otherwise check the numbers.")
    lng = long[long["design"] == LONGITUDINAL]
    if not lng.empty and lng["n_followup"].sum() == 0:
        warnings.append("Instruments marked longitudinal have no follow-up numbers.")
    miss = lng[(lng["n_followup"] > 0) &
               (lng["interval"].astype(str).str.strip() == "")]
    if not miss.empty:
        warnings.append(f"{len(miss)} longitudinal rows have follow-up numbers but "
                        f"no repeat interval.")

    # the check that only exists because both stages live in one system
    s1 = st.session_state["stage1"]
    if s1:
        chosen = set(selected_instruments())
        for con, cells in s1.get("designs", {}).items():
            claimed = [p for p, d in cells.items() if d and p in phenos()]
            if not claimed or con in NOT_OFFERED_IN_STAGE2:
                continue
            options = ({g["label"] for g in groups_for(con)}
                       | {u["label"] for u in extra_units() if u["domain"] == con})
            if not (chosen & options):
                warnings.append(f"Stage 1 reported **{con}** for "
                                f"{', '.join(claimed)}, but nothing in this plan "
                                f"carries it.")
    return errors, warnings


# --------------------------------------------------------------------------
# Screens
# --------------------------------------------------------------------------

def screen_cohort():
    st.header("1. Cohort and agreement")
    st.caption("Filled once, when the DTA/MTA is drawn up. For an ongoing study "
               "you project year by year — you are not asked to come back and "
               "re-report.")

    up = st.file_uploader("Load the Stage 1 Site Interest submission (JSON)",
                          type="json")
    if up is not None and not st.session_state.get("_s1_loaded"):
        s1 = json.load(up)
        st.session_state["stage1"] = s1
        study = s1.get("study", {})
        for wk, val in [("w_cohort_id", study.get("w_study_short", "")),
                        ("w_contact_name", study.get("w_contact_name", "")),
                        ("w_contact_email", study.get("w_contact_email", "")),
                        ("w_phenotypes", study.get("w_phenotypes", [])),
                        ("w_samples", [b for b in study.get("w_biosamples", [])
                                       if b != "DNA"])]:
            if val:
                st.session_state[wk] = val
        if study.get("w_year_end"):
            st.session_state["w_final_year"] = int(study["w_year_end"])
        st.session_state["_s1_loaded"] = True
        st.session_state["selected"] = []
        st.session_state["designs"] = {}
        st.session_state["_inst_init"] = False
        for k in [k for k in st.session_state
                  if str(k).startswith(("inst::", "seg::", "other::"))]:
            del st.session_state[k]
        reset_editors()
        st.success("Stage 1 loaded. Instruments are pre-selected on screen 2.")

    s1 = st.session_state["stage1"]
    if s1:
        n = sum(1 for cells in s1.get("designs", {}).values()
                if any(v for v in cells.values()))
        st.info(f"Stage 1 submitted {s1.get('submitted', '?')} — "
                f"{n} domains reported.")
    else:
        st.warning("No Stage 1 submission loaded. You can still fill this in from "
                   "scratch, but nothing will be pre-selected and the coverage "
                   "check on the review screen will be skipped.")

    c1, c2, c3 = st.columns(3)
    c1.text_input("GP2 cohort ID", key="w_cohort_id")
    c2.text_input("Contact name", key="w_contact_name")
    c3.text_input("Contact email", key="w_contact_email")

    st.multiselect("Phenotypes covered by this agreement", PHENOTYPES,
                   key="w_phenotypes")
    st.radio("Is recruitment or follow-up still running?", ["Ongoing", "Completed"],
             key="w_status", horizontal=True)
    if st.session_state["w_status"] == "Ongoing":
        c1, c2 = st.columns(2)
        c1.number_input("Last year you expect to collect data", date.today().year,
                        date.today().year + 20, key="w_final_year")
        c2.date_input("First transfer deadline", key="w_deadline")
        sync_from_widgets()
        years = plan_years()
        if years:
            st.info(f"You will project **{len(years)}** years: {years[0]}–{years[-1]}.")
    else:
        st.date_input("Transfer deadline", key="w_deadline")
    sync_from_widgets()


def offered_options(reported: list[str]) -> list[dict]:
    """One row per instrument, not per (construct, instrument) pair.

    The three exposure questionnaires serve lifestyle, environment and head
    trauma at once. Listing them three times would mean three switches driving
    one decision, so each appears once with every domain it covers named.
    """
    by_label: dict[str, dict] = {}
    for con, lab, mods, dflt, note in INSTRUMENT_GROUPS:
        if con not in reported:
            continue
        if lab in by_label:
            by_label[lab]["domains"].append(con)
            continue
        by_label[lab] = {"label": lab, "domains": [con], "modalities": mods,
                         "default": dflt, "note": note, "construct": con}
    return list(by_label.values())


def extras_table(name: str, domains: list[str], caption: str = "") -> None:
    """Free-text measures, as a table the cohort can add rows to.

    A dict keyed by domain would allow exactly one entry each, which is wrong —
    a cohort can run two depression scales. Rows it is.
    """
    if not domains:
        return
    if caption:
        st.caption(caption)
    mine = [e for e in st.session_state["extras"] if e.get("domain") in domains]

    def build():
        rows = [{"Domain": e["domain"], "Measure": e["measure"]} for e in mine]
        return pd.DataFrame(rows or [{"Domain": None, "Measure": ""}])

    src = editor_source(name, (tuple(domains), len(mine)), build)
    edited = st.data_editor(
        src, hide_index=True, width="stretch", num_rows="dynamic",
        key=editor_key(name),
        column_config={
            "Domain": st.column_config.SelectboxColumn(options=domains,
                                                       width="medium"),
            "Measure": st.column_config.TextColumn(
                "Questionnaire or measure", width="large"),
        })
    kept = [e for e in st.session_state["extras"] if e.get("domain") not in domains]
    for r in edited.itertuples():
        d = None if pd.isna(r.Domain) else str(r.Domain).strip()
        m = "" if pd.isna(r.Measure) else str(r.Measure).strip()
        if d and m:
            kept.append({"domain": d, "measure": m})
    st.session_state["extras"] = kept


def screen_instruments():
    st.header("2. What will be transferred")
    _, l2, _, bios = load_vocab()
    if not phenos():
        st.warning("Select phenotypes on screen 1 first.")
        return

    st.subheader("Biosamples")
    st.multiselect("Biosamples in this transfer, besides DNA",
                   [b for b in bios.biosample if b != "DNA"], key="w_samples")

    st.subheader("Instruments")
    s1 = st.session_state["stage1"]
    if s1:
        reported = [c for c, cells in s1.get("designs", {}).items()
                    if any(v for p, v in cells.items() if p in phenos())]
        st.caption("Everything Stage 1 said you collect, in one table. The "
                   "instrument most cohorts use is ticked; the alternatives are "
                   "listed so you can see what else counts.")
    else:
        reported = sorted({c for c, _, _, _, _ in INSTRUMENT_GROUPS})
        st.caption("No Stage 1 answers, so every domain is shown.")

    dropped = [c for c in reported if c in NOT_OFFERED_IN_STAGE2]
    reported = [c for c in reported if c not in NOT_OFFERED_IN_STAGE2]
    options = offered_options(reported)
    if not options:
        st.info("Nothing to plan for the domains reported.")
        return

    sel = set(st.session_state["selected"])
    first_visit = not st.session_state["_inst_init"]
    key_cols = ["Domain", "Instrument"]

    def build():
        rows = []
        for o in options:
            g = {"construct": o["construct"], "label": o["label"],
                 "default": o["default"]}
            rows.append({
                "Domain": ", ".join(o["domains"]),
                "Instrument": o["label"],
                "Transfer": (default_on(g, phenos()) if first_visit
                             else o["label"] in sel),
                "What it is": o["note"],
            })
        return pd.DataFrame(rows)

    src = editor_source("instruments", tuple(o["label"] for o in options), build)
    edited = st.data_editor(
        src, hide_index=True, width="stretch", key=editor_key("instruments"),
        column_config={
            "Domain": st.column_config.TextColumn(disabled=True, width="medium"),
            "Instrument": st.column_config.TextColumn(disabled=True, width="medium"),
            "Transfer": st.column_config.CheckboxColumn(width="small"),
            "What it is": st.column_config.TextColumn(disabled=True, width="large"),
        })
    st.session_state["selected"] = sorted(
        r.Instrument for r in edited.itertuples() if r.Transfer)
    st.session_state["_inst_init"] = True

    st.subheader("Anything not listed in these domains")
    st.caption("A measure you use that is not in the table above. One domain can "
               "carry several — add a row for each.")
    extras_table("extras_reported", [c for c in reported if c not in NO_OTHER])

    st.subheader("Anything else to share?")
    remaining = [c for c, _, _, _, _ in INSTRUMENT_GROUPS
                 if c not in reported and c not in NOT_OFFERED_IN_STAGE2]
    remaining = sorted(set(remaining))
    st.caption("Domains Stage 1 did not report. Adding one here brings its "
               "instruments into the plan.")
    st.multiselect("Domains to add", remaining, key="w_extra_domains")
    added = st.session_state["w_extra_domains"]
    if added:
        extra_opts = offered_options(added)
        sel2 = set(st.session_state["selected"])

        def build2():
            return pd.DataFrame([{
                "Domain": ", ".join(o["domains"]), "Instrument": o["label"],
                "Transfer": o["label"] in sel2, "What it is": o["note"],
            } for o in extra_opts])

        src2 = editor_source("instruments_extra",
                             tuple(o["label"] for o in extra_opts), build2)
        edited2 = st.data_editor(
            src2, hide_index=True, width="stretch",
            key=editor_key("instruments_extra"),
            column_config={
                "Domain": st.column_config.TextColumn(disabled=True, width="medium"),
                "Instrument": st.column_config.TextColumn(disabled=True,
                                                          width="medium"),
                "Transfer": st.column_config.CheckboxColumn(width="small"),
                "What it is": st.column_config.TextColumn(disabled=True,
                                                          width="large"),
            })
        for r in edited2.itertuples():
            sel2.add(r.Instrument) if r.Transfer else sel2.discard(r.Instrument)
        st.session_state["selected"] = sorted(sel2)

    extras_table("extras_other",
                 [c for c in remaining if c not in NO_OTHER] + [OTHER_DOMAIN],
                 caption="Or a measure with no GP2 domain at all — pick "
                         f"**{OTHER_DOMAIN}** as the domain.")

    chosen = selected_instruments()
    c1, c2 = st.columns(2)
    c1.metric("Instruments selected", len(chosen))
    c2.metric("Domains covered", len({c for m in chosen
                                      for c in unit_constructs_of(m)}))
    if dropped:
        st.caption("Reported in Stage 1 but not planned here: "
                   + ", ".join(dropped) + ".")

    missing, unreachable = vocab_check(l2)
    if missing or unreachable:
        with st.expander("⚠︎ Data dictionary consistency", expanded=False):
            if missing:
                st.warning("Named in this app but not in the dictionary — renamed, "
                           "or not added yet: " + ", ".join(missing))
            if unreachable:
                st.info("In the dictionary but no option here would transfer it: "
                        + ", ".join(unreachable))
            st.caption("Edit `INSTRUMENT_GROUPS` at the top of this file to "
                       "reconcile.")


def screen_design():
    st.header("3. Cross-sectional or longitudinal")
    chosen, ps = selected_instruments(), phenos()
    if not chosen or not ps:
        st.info("Select instruments on screen 2 first.")
        return

    if st.session_state["stage1"]:
        st.caption("Inherited from your Stage 1 answers — an instrument serving a "
                   "longitudinal domain arrives as **LT**. Change anything that "
                   "differs at instrument level.")
    else:
        st.caption("No Stage 1 answers to inherit, so everything starts at **CS**.")
    st.caption(f"**{NOT_COLLECTED}** not collected in that group · **CS** once per "
               f"person · **LT** repeated over time.")

    head = st.columns([3] + [1] * len(ps))
    head[0].caption("")
    for col, p in zip(head[1:], ps):
        col.caption(f"**{p}**")
    for m in chosen:
        cols = st.columns([3] + [1] * len(ps))
        cols[0].markdown(f"**{m}**")
        served = unit_constructs_of(m)
        if served:
            cols[0].caption(", ".join(served))
        for col, p in zip(cols[1:], ps):
            key = f"seg::{m}::{p}"
            if key not in st.session_state:
                # design_of(), not seed_design(): the control is re-created every
                # time the screen is revisited, so it must come back to whatever
                # was stored, not to the Stage 1 default.
                st.session_state[key] = SHORT[design_of(m, p)]
            col.segmented_control(f"{m} · {p}", [NOT_COLLECTED, "CS", "LT"],
                                  key=key, label_visibility="collapsed")
            st.session_state["designs"].setdefault(m, {})[p] = \
                LONG_LABEL.get(st.session_state[key] or NOT_COLLECTED)


def screen_dna():
    st.header("4. DNA transfer plan")
    basis, why = dna_basis()
    st.caption("DNA defines the cohort size everything else is measured against. "
               "One row per participant — no repeats.")
    if why:
        st.info(f"Stage 1 says {why}, so these numbers start from your **{basis}** "
                f"counts. Enter the participants who will end up with usable DNA — "
                f"that may be fewer than the samples shipped.")
    if not phenos():
        st.warning("Select phenotypes on screen 1 first.")
        return
    vcols = value_columns(new_years=True, followup=False)
    key_cols = ["Phenotype", "Item"]

    def build():
        new = make_grid([{"Phenotype": p, "Item": "DNA"} for p in phenos()],
                        vcols, interval=False)
        est = stage1_samples()
        basis, _ = dna_basis()
        if not est.empty and st.session_state["dna"] is None:
            rows = est[est.item == basis]
            for idx, r in new.iterrows():
                e = rows[rows.phenotype == r["Phenotype"]]
                if len(e) and pd.notna(e.n_now.iloc[0]):
                    new.at[idx, "Baseline N"] = int(e.n_now.iloc[0])
        spec = st.session_state.get("_demo_dna")
        if spec and st.session_state["dna"] is None:
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

    src = editor_source("dna", (tuple(phenos()), tuple(vcols)), build)
    st.session_state["dna"] = st.data_editor(
        src, hide_index=True, width="stretch", key=editor_key("dna"),
        column_config=grid_config(key_cols, vcols, False))
    if is_ongoing():
        st.caption("Baseline is everyone already recruited. Each year column is how "
                   "many NEW participants you expect to add that year.")
    totals = dna_totals()
    cols = st.columns(max(len(totals), 1))
    for c, (p, n) in zip(cols, totals.items()):
        c.metric(p, n)
    st.metric("Total participants with DNA", sum(totals.values()))


def count_screen(kind: str, header: str, caption: str, empty: str,
                 items_fn, store_key: str) -> None:
    st.header(header)
    if not phenos():
        st.warning("Select phenotypes on screen 1 first.")
        return
    st.caption(caption)
    if st.session_state.get("dna") is not None:
        st.info(PREFILL_NOTE[kind])

    xs_cols = value_columns(new_years=True, followup=False)
    lg_cols = value_columns(new_years=True, followup=True)
    key_cols = ["Phenotype", "Item"]
    store, any_rows = {}, False

    for pheno in phenos():
        mine = items_fn(pheno)
        if not mine:
            continue
        any_rows = True
        xs = [i for i in mine if item_design(kind, i, pheno) == CROSS_SECTIONAL]
        lg = [i for i in mine if item_design(kind, i, pheno) == LONGITUDINAL]
        with st.expander(pheno, expanded=(pheno == phenos()[0])):
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
                    merged = carry_over(st.session_state[store_key].get((pheno, design)),
                                        new, key_cols)
                    return apply_prefill(merged, kind, pheno, design, vcols)

                src = editor_source(name, (tuple(items), tuple(vcols)), build)
                store[(pheno, design)] = st.data_editor(
                    src, hide_index=True, width="stretch", key=editor_key(name),
                    column_config=grid_config(key_cols, vcols, interval))
    if not any_rows:
        st.info(empty)
    st.session_state[store_key] = store


PREFILL_NOTE = {
    "instrument": "Pre-filled from your DNA numbers, on the assumption that most "
                  "genotyped participants were also assessed. **Correct anything "
                  "that differs** — partial coverage is normal and we would rather "
                  "have the real number than the optimistic one.",
    "sample": "Pre-filled from your DNA numbers as a starting point. Biosample "
              "coverage is usually well below the genotyped count — CSF and brain "
              "especially — so **expect to reduce most of these**.",
}


def item_design(kind: str, item: str, phenotype: str) -> str | None:
    """Biosample design is asked here; instrument design comes from screen 3."""
    if kind == "instrument":
        return design_of(item, phenotype)
    return st.session_state["designs"].get(f"sample::{item}", {}).get(
        phenotype, CROSS_SECTIONAL)


def samples_for(phenotype: str) -> list[str]:
    return list(st.session_state["w_samples"])


def screen_samples():
    count_screen("sample", "5. Biosamples",
                 "Counts are participants, not tubes.",
                 "No biosamples selected on screen 2.",
                 samples_for, "samples")


def screen_instruments_counts():
    count_screen("instrument", "6. Instrument numbers",
                 "Counts are participants, not visits. One section per phenotype.",
                 "No instruments selected on screen 2.",
                 items_for, "clinical")


def dna_basis() -> tuple[str, str]:
    """(biosample the denominator comes from, why).

    A cohort holding extracted DNA is counted on its DNA. One that needs GP2 to
    extract is counted on the material it ships, because that is what limits how
    many participants can ever have DNA.
    """
    s1 = st.session_state["stage1"]
    if not s1:
        return "DNA", ""
    study = s1.get("study", {})
    if study.get("w_dna_local", "Yes") == "Yes":
        return "DNA", "extracted DNA is already available"
    src = study.get("w_dna_source", "Blood")
    sample = DNA_SOURCE_SAMPLE.get(src)
    if not sample:
        other = study.get("w_dna_source_other", "").strip()
        return (other or "DNA"), f"DNA will be extracted from {other or src.lower()}"
    return sample, f"DNA will be extracted from {src.lower()} after transfer"


def stage1_samples() -> pd.DataFrame:
    """Stage 1's biosample estimates, as (phenotype, item, now, horizon)."""
    s1 = st.session_state["stage1"]
    if not s1:
        return pd.DataFrame()
    rows = [r for r in s1.get("plan", []) if r.get("kind") == "biosample"]
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def reconcile(long: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Compare the firm plan against what Stage 1 estimated.

    Differences are expected — Stage 1 is an estimate made before any agreement,
    often months earlier and sometimes by someone else. Nothing here blocks
    submission. The point is that GP2 can see where a cohort's offer moved, and
    in which direction, which is invisible today because the two live in
    separate systems.
    """
    s1 = st.session_state["stage1"]
    if not s1 or long.empty:
        return pd.DataFrame(), []

    notes: list[str] = []
    ps = set(phenos())

    # --- numbers, per phenotype x sample
    est = stage1_samples()
    rows = []
    if not est.empty:
        planned = (long[long.item_class == "sample"]
                   .groupby(["phenotype", "item"])["n_new"].sum())
        pairs = set(planned.index) | {
            (r.phenotype, r.item) for r in est.itertuples() if r.phenotype in ps}
        for pheno, item in sorted(pairs):
            e = est[(est.phenotype == pheno) & (est.item == item)]
            now = int(e.n_now.iloc[0]) if len(e) and pd.notna(e.n_now.iloc[0]) else None
            hor = int(e.n_horizon.iloc[0]) if len(e) and pd.notna(e.n_horizon.iloc[0]) else None
            got = int(planned.get((pheno, item), 0))
            if now is None and got == 0:
                continue
            flag = ""
            if hor is None:
                flag = "not offered at Stage 1"
            elif got == 0:
                flag = "estimated, not in this plan"
            elif now is not None and got < now:
                flag = f"below what already existed at Stage 1 ({now})"
            elif abs(got - hor) > max(10, 0.1 * hor):
                flag = "up" if got > hor else "down"
            rows.append({"Phenotype": pheno, "Sample": item,
                         "Stage 1 now": now, "Stage 1 projected": hor,
                         "Stage 2 planned": got, "Flag": flag})

    # --- design: a domain reported longitudinal that arrives cross-sectional
    for con, cells in s1.get("designs", {}).items():
        if con in NOT_OFFERED_IN_STAGE2:
            continue
        for pheno, d in cells.items():
            if d != LONGITUDINAL or pheno not in ps:
                continue
            serving = [m for m in selected_instruments()
                       if con in unit_constructs_of(m)]
            designs = {design_of(m, pheno) for m in serving}
            if serving and LONGITUDINAL not in designs:
                notes.append(f"**{con}** was reported longitudinal for {pheno}, "
                             f"but every instrument covering it here is "
                             f"cross-sectional or not collected.")

    # --- instruments planned for domains Stage 1 never mentioned
    reported = {c for c, cells in s1.get("designs", {}).items()
                if any(v for v in cells.values())}
    added = sorted({m for m in selected_instruments()
                    if not (set(unit_constructs_of(m)) & reported)})
    if added:
        notes.append("Planned but not reported at Stage 1: " + ", ".join(added)
                     + ". Not a problem — Stage 1 is an estimate — but worth a "
                       "look if it was unintended.")

    # --- phenotypes
    s1_ph = set(s1.get("study", {}).get("w_phenotypes", []))
    if s1_ph:
        extra = ps - s1_ph
        gone = s1_ph - ps
        if extra:
            notes.append("Phenotypes in this agreement that Stage 1 did not list: "
                         + ", ".join(sorted(extra)) + ".")
        if gone:
            notes.append("Phenotypes reported at Stage 1 but not covered here: "
                         + ", ".join(sorted(gone)) + ".")
    return pd.DataFrame(rows), notes


def build_pdf(long: pd.DataFrame) -> bytes:
    """Screens 1-6 as the document that goes with the DTA/MTA."""
    m = st.session_state["meta"]
    basis, why = dna_basis()
    s1 = st.session_state["stage1"]
    years = plan_years()
    sections = [
        ("1. Cohort and agreement", [report.fields([
            ("Cohort", m["cohort_id"]),
            ("Contact", f"{m['contact_name']} · {m['contact_email']}"),
            ("Phenotypes", ", ".join(phenos())),
            ("Status", m["study_status"]),
            ("Deadline", m["deadline"]),
            ("Projected years", ", ".join(str(y) for y in years) or "single transfer"),
            ("Stage 1 submitted", (s1 or {}).get("submitted", "not loaded")),
            ("Cohort size counted on", f"{basis}" + (f" — {why}" if why else "")),
        ])]),
    ]

    chosen = selected_instruments()
    if chosen:
        rows = [{"Instrument": c, "Domains": ", ".join(unit_constructs_of(c)),
                 "Dictionary modalities": "; ".join(unit_modalities(c)) or "—"}
                for c in chosen]
        sections.append(("2. Instruments to be transferred",
                         report.frame(pd.DataFrame(rows),
                                      widths=[26, 30, 44])))

    if not long.empty:
        design = (long[long.item_class == "instrument"]
                  .pivot_table(index="item", columns="phenotype", values="design",
                               aggfunc="first").fillna("None")
                  .replace({CROSS_SECTIONAL: "CS", LONGITUDINAL: "LT"})
                  .reset_index().rename(columns={"item": "Instrument"}))
        sections.append(("3. Cross-sectional or longitudinal",
                         report.frame(design)))

        for cls, title in [("sample", "4-5. DNA and biosamples"),
                           ("instrument", "6. Instrument numbers")]:
            sub = long[long.item_class == cls]
            if sub.empty:
                continue
            tab = (sub.pivot_table(index=["phenotype", "item"], columns="period",
                                   values="n_total", aggfunc="sum", fill_value=0)
                   .reset_index().rename(columns={"phenotype": "Phenotype",
                                                  "item": "Item"}))
            sections.append((title, report.frame(tab)))

    table, notes = reconcile(long)
    if s1:
        content = [Paragraph2("Stage 1 was an estimate made before any agreement, "
                              "so these are not expected to match exactly.")]
        if not table.empty:
            content += report.frame(table)
        for n in notes:
            content.append(Paragraph2(n.replace("**", "")))
        sections.append(("Reconciliation with Stage 1", content))
    return report.build("GP2 Data & Sample Transfer Plan",
                        report.stamp(m["cohort_id"]), sections)


def Paragraph2(text: str):
    from reportlab.platypus import Paragraph
    return Paragraph(report.esc(text), report.BODY)


def screen_review():
    st.header("7. Review and submit")
    long = to_long()
    errors, warnings = validate(long)
    for e in errors:
        st.error(e)
    for w in warnings:
        st.warning(w)
    if long.empty:
        return

    denom = dna_totals()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Participants with DNA", sum(denom.values()))
    c2.metric("Instruments", long[long.item_class == "instrument"]["item"].nunique())
    c3.metric("Planned participants", int(long["n_new"].sum()))
    c4.metric("Planned follow-up", int(long["n_followup"].sum()))

    if is_ongoing() and plan_years():
        st.subheader("Plan by year")
        st.dataframe(long.groupby("period")[["n_new", "n_followup"]].sum()
                     .rename(columns={"n_new": "New participants",
                                      "n_followup": "Follow-up"}), width="stretch")

    st.subheader("Coverage against DNA")
    cov = long[long["item"] != "DNA"].copy()
    if not cov.empty and denom:
        agg = cov.groupby(["item", "phenotype"])["n_new"].sum().reset_index()
        agg["pct"] = (100 * agg["n_new"] / agg["phenotype"].map(denom)
                      .replace(0, float("nan")).astype(float)).round(0)
        st.dataframe(agg.pivot(index="item", columns="phenotype", values="pct")
                     .style.format("{:.0f}%", na_rep="—"), width="stretch")

    table, notes = reconcile(long)
    if st.session_state["stage1"]:
        st.subheader("Reconciliation with Stage 1")
        st.caption("Stage 1 was an estimate made before any agreement, so these "
                   "will not match exactly and are not expected to. Nothing here "
                   "blocks submission — it is here so the change is visible.")
        if not table.empty:
            flagged = int((table.Flag != "").sum())
            st.dataframe(table, hide_index=True, width="stretch")
            st.caption(f"{flagged} of {len(table)} sample rows differ enough to "
                       f"flag (more than 10 participants or 10%).")
        for n in notes:
            st.info(n)
        if table.empty and not notes:
            st.success("The plan matches what Stage 1 reported.")

    st.subheader("What gets stored")
    st.dataframe(long, hide_index=True, width="stretch")
    st.caption("One row per phenotype x instrument x period. Adding an instrument, "
               "a phenotype or a year never changes the schema.")

    cid = st.session_state["meta"]["cohort_id"] or "draft"
    c1, c2, c3 = st.columns(3)
    c1.download_button("Download plan (CSV)", long.to_csv(index=False),
                       file_name=f"transfer_plan_{cid}.csv", mime="text/csv")
    snap = {"stage": 2, "meta": st.session_state["meta"],
            "phenotypes": phenos(), "instruments": selected_instruments(),
            "designs": st.session_state["designs"],
            "stage1_submitted": (st.session_state["stage1"] or {}).get("submitted"),
            "plan": long.to_dict("records")}
    c2.download_button("Save draft (JSON)", json.dumps(snap, indent=2, default=str),
                       file_name=f"transfer_plan_{cid}.json",
                       mime="application/json")
    c3.download_button("Download report (PDF)", build_pdf(long),
                       file_name=f"transfer_plan_{cid}.pdf",
                       mime="application/pdf")


# --------------------------------------------------------------------------
# Shell
# --------------------------------------------------------------------------

STEPS = {
    "1. Cohort & agreement": screen_cohort,
    "2. What to transfer": screen_instruments,
    "3. CS / LT": screen_design,
    "4. DNA": screen_dna,
    "5. Biosamples": screen_samples,
    "6. Instrument numbers": screen_instruments_counts,
    "7. Review & submit": screen_review,
}

DEMO_DNA = {"PD": (300, [200, 100, 0]), "Control": (300, [0, 0, 0]),
            "Prodromal": (200, [100, 100, 0])}


def load_demo():
    """A cohort that already submitted Stage 1, so inheritance is visible."""
    st.session_state["stage1"] = {
        "submitted": date.today().isoformat(),
        "designs": {
            "Demographics": {"PD": CROSS_SECTIONAL, "Control": CROSS_SECTIONAL,
                             "Prodromal": CROSS_SECTIONAL},
            "Diagnosis": {"PD": CROSS_SECTIONAL, "Control": CROSS_SECTIONAL,
                          "Prodromal": CROSS_SECTIONAL},
            "UPDRS (MDS / original)": {"PD": LONGITUDINAL, "Control": None,
                                       "Prodromal": LONGITUDINAL},
            "Cognition": {"PD": LONGITUDINAL, "Control": CROSS_SECTIONAL,
                          "Prodromal": LONGITUDINAL},
            "Depression": {"PD": LONGITUDINAL, "Control": None,
                           "Prodromal": CROSS_SECTIONAL},
            "RBD": {"PD": CROSS_SECTIONAL, "Control": None,
                    "Prodromal": LONGITUDINAL},
            "Head trauma": {"PD": CROSS_SECTIONAL, "Control": CROSS_SECTIONAL,
                            "Prodromal": None},
            "Motor staging (H&Y)": {"PD": LONGITUDINAL, "Control": None,
                                    "Prodromal": None},
        },
        "study": {},
    }
    st.session_state.update({
        "w_cohort_id": "DEMO-COHORT", "w_contact_name": "A. Example",
        "w_contact_email": "a.example@institution.edu", "w_status": "Ongoing",
        "w_final_year": date.today().year + 2,
        "w_phenotypes": ["PD", "Control", "Prodromal"],
        "w_samples": ["blood", "plasma", "CSF"], "w_extra_domains": [],
    })
    st.session_state["designs"] = {}
    st.session_state["selected"] = []
    st.session_state["extras"] = []
    st.session_state["_inst_init"] = False
    st.session_state["dna"] = None
    st.session_state["_demo_dna"] = DEMO_DNA
    st.session_state["samples"] = {}
    st.session_state["clinical"] = {}
    st.session_state["_prefilled"] = set()
    for k in [k for k in st.session_state
              if str(k).startswith(("seg::", "inst::", "other::"))]:
        del st.session_state[k]
    reset_editors()


def sidebar():
    st.sidebar.title("GP2 transfer plan")
    st.sidebar.caption("Stage 2 prototype — not a live collection.")
    step = st.sidebar.radio("Step", list(STEPS), label_visibility="collapsed")
    st.sidebar.divider()
    if st.sidebar.button("Load an example cohort"):
        load_demo()
        st.rerun()
    _, l2, _, bios = load_vocab()
    st.sidebar.caption(f"Vocabulary: {len(l2)} instruments, {len(bios)} biosamples.")
    st.sidebar.divider()
    st.sidebar.caption("Stage 1 suggests instruments; it never decides them. The "
                       "review screen reconciles this plan against what Stage 1 "
                       "estimated.")
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
