"""
Trigger logic for filtering LHC events.
Divij Bhoj, 2026

These are simplified versions of the trigger paths you'd find in
ATLAS or CMS — obviously the real triggers run on FPGAs and are
way more complex, but the logic is the same idea: quickly decide
if an event is interesting enough to keep.

Currently implemented:
  - HLT_mu25      : single isolated muon with pT > 25 GeV
  - HLT_2mu_Zmass : opposite-sign dimuon pair near the Z mass
  - HLT_4j50      : at least 4 jets above 50 GeV
  - HLT_met50     : missing transverse energy above 50 GeV
"""

import math
from pipeline.config import (
    TRIGGER_MUON_PT_MIN,
    TRIGGER_DIMUON_MASS_LOW,
    TRIGGER_DIMUON_MASS_HIGH,
    TRIGGER_JET_PT_MIN,
    TRIGGER_MULTI_JET_COUNT,
    TRIGGER_MET_MIN,
)

MUON = 13
ELECTRON = 11


def compute_invariant_mass(p1: dict, p2: dict) -> float:
    """
    Compute invariant mass of two particles from their 4-momenta.
    Standard textbook formula: M² = (E₁+E₂)² - |p₁+p₂|²
    """
    e  = p1["energy"] + p2["energy"]
    px = p1["pt"] * math.cos(p1["phi"]) + p2["pt"] * math.cos(p2["phi"])
    py = p1["pt"] * math.sin(p1["phi"]) + p2["pt"] * math.sin(p2["phi"])
    pz = p1["pt"] * math.sinh(p1["eta"]) + p2["pt"] * math.sinh(p2["eta"])
    m2 = e * e - px * px - py * py - pz * pz
    return math.sqrt(max(0.0, m2))


def delta_r(p1: dict, p2: dict) -> float:
    """
    ΔR = √(Δη² + Δφ²) — the standard angular separation metric
    used everywhere in collider physics. Two objects with ΔR < 0.4
    are typically considered overlapping.
    """
    deta = p1["eta"] - p2["eta"]
    dphi = p1["phi"] - p2["phi"]
    while dphi > math.pi:
        dphi -= 2.0 * math.pi
    while dphi < -math.pi:
        dphi += 2.0 * math.pi
    return math.sqrt(deta * deta + dphi * dphi)


def apply_triggers(event: dict) -> dict:
    """
    Run all trigger paths on a single event.

    Returns a dict with each trigger's pass/fail decision plus
    any computed observables (dimuon mass, leading pT values).
    In a real experiment, this would run at ~100 kHz on custom hardware.
    Here we just do it in Python because we can.
    """
    results = {
        "single_muon": False,
        "dimuon_z": False,
        "multi_jet": False,
        "high_met": False,
        "any_trigger": False,
        "dimuon_mass": None,
        "leading_muon_pt": None,
        "leading_jet_pt": None,
    }

    particles = event.get("particles", [])

    # grab all isolated muons and sort by pT (highest first)
    muons = [
        p for p in particles
        if abs(p["pdg_id"]) == MUON and p.get("is_isolated", False)
    ]
    muons.sort(key=lambda p: p["pt"], reverse=True)

    if muons:
        results["leading_muon_pt"] = muons[0]["pt"]

    # --- single muon trigger ---
    # pretty straightforward: is there a hard isolated muon?
    high_pt_muons = [m for m in muons if m["pt"] > TRIGGER_MUON_PT_MIN]
    results["single_muon"] = len(high_pt_muons) > 0

    # --- dimuon Z trigger ---
    # look for opposite-sign muon pairs and pick the one closest
    # to the Z mass. this is how you'd reconstruct Z → μμ candidates.
    if len(muons) >= 2:
        pos_muons = [m for m in muons if m["pdg_id"] < 0]   # μ⁺ has pdg = -13
        neg_muons = [m for m in muons if m["pdg_id"] > 0]   # μ⁻ has pdg = +13
        best_mass = None
        for mp in pos_muons:
            for mn in neg_muons:
                mass = compute_invariant_mass(mp, mn)
                if best_mass is None or abs(mass - 91.2) < abs(best_mass - 91.2):
                    best_mass = mass
        if best_mass is not None:
            results["dimuon_mass"] = round(best_mass, 3)
            if TRIGGER_DIMUON_MASS_LOW < best_mass < TRIGGER_DIMUON_MASS_HIGH:
                results["dimuon_z"] = True

    # --- multi-jet trigger ---
    # count jets above the pT threshold (non-isolated particles)
    jets = [
        p for p in particles
        if not p.get("is_isolated", True) and p["pt"] > TRIGGER_JET_PT_MIN
    ]
    jets.sort(key=lambda p: p["pt"], reverse=True)

    if jets:
        results["leading_jet_pt"] = jets[0]["pt"]

    results["multi_jet"] = len(jets) >= TRIGGER_MULTI_JET_COUNT

    # --- MET trigger ---
    # large missing energy usually means neutrinos (from W/Z/top decays)
    results["high_met"] = event.get("met", 0) > TRIGGER_MET_MIN

    # final decision: did ANY trigger fire?
    results["any_trigger"] = any([
        results["single_muon"],
        results["dimuon_z"],
        results["multi_jet"],
        results["high_met"],
    ])

    return results
