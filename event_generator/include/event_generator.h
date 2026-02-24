// event_generator.h
// Divij Bhoj, 2026
//
// Simulates pp collision events loosely based on 13 TeV LHC conditions.
// Nothing fancy — just enough physics to produce realistic-looking
// JSON output that the Kafka pipeline can chew on.
//
// Three processes right now:
//   - Z → μ⁺μ⁻       (clean dilepton signal)
//   - tt̄ → ℓ + jets   (semi-leptonic top pair)
//   - QCD multi-jet    (the background that never goes away)

#pragma once

#include <cstdint>
#include <cmath>
#include <chrono>
#include <random>
#include <string>
#include <vector>

namespace lhc {

// PDG codes — just the ones we actually use
namespace pdg {
    constexpr int ELECTRON    = 11;
    constexpr int MUON        = 13;
    constexpr int NEUTRINO_E  = 12;
    constexpr int NEUTRINO_MU = 14;
    constexpr int PHOTON      = 22;
    constexpr int PION_PLUS   = 211;
    constexpr int KAON_PLUS   = 321;
    constexpr int PROTON      = 2212;
    constexpr int BOTTOM      = 5;
    constexpr int GLUON       = 21;
    constexpr int Z_BOSON     = 23;
    constexpr int W_PLUS      = 24;
}

// Physical constants in natural units (GeV where applicable)
// Values from PDG 2024 — good enough for simulation purposes
namespace constants {
    constexpr double Z_MASS        = 91.1876;
    constexpr double Z_WIDTH       = 2.4952;
    constexpr double W_MASS        = 80.379;
    constexpr double TOP_MASS      = 172.76;
    constexpr double MUON_MASS     = 0.10566;
    constexpr double ELECTRON_MASS = 0.000511;
    constexpr double PION_MASS     = 0.13957;
    constexpr double PI            = 3.14159265358979323846;
    constexpr double SQRT_S        = 13000.0;  // Run 2 center-of-mass energy
}

// Minimal 4-vector representation for a reconstructed particle
struct Particle {
    int    pdg_id;
    double pt;           // transverse momentum [GeV]
    double eta;          // pseudorapidity
    double phi;          // azimuthal angle [rad]
    double energy;       // total energy [GeV]
    double mass;         // invariant mass [GeV]
    bool   is_isolated;  // passes isolation cut (relevant for leptons)

    // handy for computing invariant masses later
    double px() const { return pt * std::cos(phi); }
    double py() const { return pt * std::sin(phi); }
    double pz() const { return pt * std::sinh(eta); }
};

// One collision event — contains everything the trigger system needs
struct Event {
    uint64_t    event_id;
    uint64_t    run_number;
    uint64_t    timestamp_ms;
    std::string event_type;       // "z_mumu", "ttbar", or "qcd"
    int         num_particles;
    std::vector<Particle> particles;
    double      met;              // missing transverse energy [GeV]
    double      met_phi;          // MET direction
    double      sum_et;           // scalar sum of all pT
    int         num_jets;
    int         num_muons;
    int         num_electrons;
    int         primary_vertices; // rough pileup proxy

    // serialize to a single JSON line for piping to the producer
    std::string to_json() const;
};

// Generates random collision events with configurable conditions.
// Not meant to replace Pythia — just realistic enough to exercise
// the full pipeline (trigger logic, histograms, dashboard, etc.)
class EventGenerator {
public:
    explicit EventGenerator(uint64_t run_number = 1, unsigned seed = 42);

    // pick a random process weighted roughly by cross-section
    Event generate();

    // or generate a specific process directly
    Event generate_z_to_mumu();
    Event generate_ttbar();
    Event generate_qcd_background();

    void     set_pileup(int mean)    { mean_pileup_ = mean; pileup_dist_ = std::poisson_distribution<int>(mean); }
    uint64_t events_generated() const { return event_counter_; }

private:
    std::mt19937_64 rng_;
    uint64_t event_counter_ = 0;
    uint64_t run_number_;
    int      mean_pileup_ = 25;

    // distributions we reuse across events (avoids re-creating them)
    std::uniform_real_distribution<double>  uniform_01_{0.0, 1.0};
    std::uniform_real_distribution<double>  phi_dist_{-constants::PI, constants::PI};
    std::normal_distribution<double>        eta_dist_{0.0, 2.5};
    std::exponential_distribution<double>   pt_exp_{0.1};
    std::poisson_distribution<int>          pileup_dist_{25};

    // internal helpers
    double   breit_wigner(double mass, double width);
    Particle make_muon(double pt, double eta, double phi, int charge);
    Particle make_jet(double pt, double eta, double phi, int pdg = pdg::GLUON);
    Particle make_electron(double pt, double eta, double phi, int charge);
    void     add_pileup_particles(Event& evt);
    uint64_t current_timestamp_ms();
};

} // namespace lhc
