#!/usr/bin/env python3
"""
Check the app's vocabulary against the GP2 Data Dictionary.

    python check_vocab.py                      # fetch the dictionary from GitHub
    python check_vocab.py --dd local.csv       # or check against a local copy
    python check_vocab.py --vocab stage2/vocab --app stage2/transfer_plan_stage2_app.py

Read-only by design. It never edits the vocabulary, because roughly a third of
the item tags and all of the INSTRUMENT_GROUPS decisions are human judgement
that a diff cannot reproduce. It tells you what changed and what that breaks;
you decide what it should mean.

Exit code 1 if anything needs a human, 0 otherwise — so it can run in CI.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import io
import sys
import urllib.request
from pathlib import Path

import pandas as pd

DEFAULT_DD = ("https://raw.githubusercontent.com/GP2code/GP2-Data-Dictionary/"
              "main/GP2_Data_Dictionary_ver1.1-3.csv")

# Reported but deliberately not transferred — not a gap.
IGNORED_CONSTRUCTS = {"EXCLUDE", "MULTIPLE"}


def load_dd(src: str) -> pd.DataFrame:
    if src.startswith(("http://", "https://")):
        raw = urllib.request.urlopen(src, timeout=30).read()
        dd = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig")
    else:
        dd = pd.read_csv(src, encoding="utf-8-sig")
    for c in ("Modality", "Item"):
        dd[c] = dd[c].astype(str).str.strip()
    return dd


def load_instrument_groups(app_path: Path) -> list[tuple]:
    """Read INSTRUMENT_GROUPS out of the app without importing streamlit."""
    tree = ast.parse(app_path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") == "INSTRUMENT_GROUPS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit(f"INSTRUMENT_GROUPS not found in {app_path}")


def suggest_renames(gone: set[str], new: set[str]) -> list[tuple[str, str, float]]:
    """A rename looks identical to a delete plus an add, so the best we can do
    is point at the likely pairs and let a person confirm."""
    out = []
    for g in sorted(gone):
        match = difflib.get_close_matches(g, sorted(new), n=1, cutoff=0.75)
        if match:
            ratio = difflib.SequenceMatcher(None, g, match[0]).ratio()
            out.append((g, match[0], ratio))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dd", default=DEFAULT_DD)
    ap.add_argument("--vocab", default="vocab")
    ap.add_argument("--app", default="transfer_plan_stage2_app.py")
    args = ap.parse_args()

    vocab = Path(args.vocab)
    dd = load_dd(args.dd)
    l2 = pd.read_csv(vocab / "gp2_L2_to_L1.csv")
    tags = pd.read_csv(vocab / "gp2_L3_item_tags.csv")
    groups = load_instrument_groups(Path(args.app))
    pend_file = vocab / "pending_modalities.txt"
    pending = {l.strip() for l in pend_file.read_text().splitlines()
               if l.strip() and not l.startswith("#")} if pend_file.exists() else set()

    dd_mods = set(dd.Modality)
    map_mods = set(l2.l2_modality.astype(str).str.strip())
    grp_mods = {m for _, _, mods, _, _ in groups for m in mods}
    tag_mods = set(tags.l2_modality.astype(str).str.strip())

    blocking, advisory = [], []

    def section(title: str, items, level: list, hint: str = ""):
        if not items:
            return
        level.append(title)
        print(f"\n## {title}  ({len(items)})")
        if hint:
            print(f"   {hint}")
        for x in sorted(items):
            print(f"   - {x}")

    print(f"Dictionary : {args.dd}")
    print(f"             {len(dd)} items, {len(dd_mods)} modalities")
    print(f"Vocabulary : {vocab}  ({len(map_mods)} modalities mapped)")
    print(f"App table  : {args.app}  ({len({g[1] for g in groups})} options)")

    # ---- modality level ---------------------------------------------------
    new_mods = dd_mods - map_mods
    gone_mods = map_mods - dd_mods - pending
    section("Modalities in the dictionary with no construct",
            new_mods, blocking,
            "Add a row to gp2_L2_to_L1.csv, or they can never be transferred.")
    section("Modalities referenced by the vocabulary but no longer in the "
            "dictionary", gone_mods, blocking,
            "Renamed or removed upstream. Fix gp2_L2_to_L1.csv.")
    section("Modalities named in INSTRUMENT_GROUPS but not in the dictionary",
            grp_mods - dd_mods - pending, blocking,
            "The app would offer something that cannot be delivered.")
    section("Pending — named in the app, waiting on the dictionary",
            (grp_mods - dd_mods) & pending, advisory,
            "Declared in vocab/pending_modalities.txt. Remove from that file "
            "once the dictionary has them.")

    renames = suggest_renames(gone_mods, new_mods)
    if renames:
        advisory.append("possible renames")
        print(f"\n## Possible renames  ({len(renames)})")
        print("   A rename is indistinguishable from a delete plus an add. "
              "Confirm each by hand.")
        for old, new, r in renames:
            print(f"   - {old!r}  ->  {new!r}   (similarity {r:.2f})")

    offered = {c for c, _, _, _, _ in groups}
    unreachable = sorted(
        m for m in dd_mods & map_mods - grp_mods
        if l2.loc[l2.l2_modality == m, "primary_l1"].iloc[0] in offered)
    section("In the dictionary, mapped, but no Stage 2 option transfers them",
            unreachable, advisory,
            "Fine if deliberate — otherwise add them to INSTRUMENT_GROUPS.")

    # ---- item level, only where item tags carry meaning --------------------
    tagged = sorted(tag_mods & dd_mods)
    item_new, item_gone = [], []
    for m in tagged:
        dd_items = set(dd.loc[dd.Modality == m, "Item"])
        tg_items = set(tags.loc[tags.l2_modality == m, "item"].astype(str).str.strip())
        item_new += [f"{m} / {i}" for i in dd_items - tg_items]
        item_gone += [f"{m} / {i}" for i in tg_items - dd_items]
    section("New items in cross-cutting instruments, not yet tagged",
            item_new, blocking,
            "These carry the many-to-many mapping, so an untagged item is a "
            "construct silently losing coverage.")
    section("Tagged items that no longer exist in the dictionary",
            item_gone, advisory, "Stale rows in gp2_L3_item_tags.csv.")

    moved = []
    home = dd.drop_duplicates("Item").set_index("Item")["Modality"].to_dict()
    for r in tags.itertuples():
        it = str(r.item).strip()
        now = home.get(it)
        if now and now != str(r.l2_modality).strip():
            moved.append(f"{it}: {r.l2_modality} -> {now}")
    section("Items that moved to a different modality", sorted(set(moved)),
            blocking, "Their tags are filed against the old form.")

    print("\n" + "=" * 68)
    if blocking:
        print(f"NEEDS ATTENTION — {len(blocking)} blocking check(s): "
              + "; ".join(blocking))
    elif advisory:
        print(f"OK, with {len(advisory)} advisory note(s).")
    else:
        print("OK — vocabulary and dictionary agree.")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
