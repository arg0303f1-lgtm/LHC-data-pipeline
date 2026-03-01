// event_generator.cpp
// Divij Bhoj, 2026
//
// Implements the three physics processes and JSON serialization.
// The kinematics are simplified but physically motivated —
// Breit-Wigner for resonances, exponential pT spectra for jets,
// and a rough power-law for QCD background.

#include "event_generator.h"
#include <nlohmann/json.hpp>
#include <algorithm>

namespace lhc {

EventGenerator::EventGenerator(uint64_t run_number, unsigned seed)
    : rng_(seed), run_number_(run_number) {}

uint64_t EventGenerator::current_timestamp_ms() {
    return static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count()
    );
}

// Sample from a Breit-Wigner (Cauchy) distribution.
// We clamp to [10, 200] GeV to avoid unphysical tails —
// doesn't matter much for the pipeline demo but keeps the
// invariant mass histograms looking reasonable.
double EventGenerator::breit_wigner(double mass, double width) {
    std::cauchy_distribution<double> bw(mass, width / 2.0);
    double m;
    do { m = bw(rng_); } while (m < 10.0 || m > 200.0);
    return m;
}

Particle EventGenerator::make_muon(double pt, double eta, double phi, int charge) {
    Particle p{};
    p.pdg_id = charge > 0 ? -pdg::MUON : pdg::MUON;  // convention: μ⁻ = +13
    p.pt = pt; p.eta = eta; p.phi = phi;
    p.mass = constants::MUON_MASS;
    double p_mag = pt * std::cosh(eta);
    p.energy = std::sqrt(p_mag * p_mag + p.mass * p.mass);
    p.is_isolated = true;
    return p;
}

Particle EventGenerator::make_jet(double pt, double eta, double phi, int pdg) {
    Particle p{};
    p.pdg_id = pdg; p.pt = pt; p.eta = eta; p.phi = phi;
    // jets pick up mass from their constituent hadrons
    std::uniform_real_distribution<double> mass_dist(5.0, 30.0);
    p.mass = mass_dist(rng_);
    double p_mag = pt * std::cosh(eta);
    p.energy = std::sqrt(p_mag * p_mag + p.mass * p.mass);
    p.is_isolated = false;
    return p;
}

Particle EventGenerator::make_electron(double pt, double eta, double phi, int charge) {
    Particle p{};
    p.pdg_id = charge > 0 ? -pdg::ELECTRON : pdg::ELECTRON;
    p.pt = pt; p.eta = eta; p.phi = phi;
    p.mass = constants::ELECTRON_MASS;
    double p_mag = pt * std::cosh(eta);
    p.energy = std::sqrt(p_mag * p_mag + p.mass * p.mass);
    p.is_isolated = true;
    return p;
}

// Sprinkle in some soft pileup particles — mostly pions and kaons
// from minimum-bias interactions. The count follows a Poisson distribution
// centered around the configured mean pileup.
void EventGenerator::add_pileup_particles(Event& evt) {
    int n = pileup_dist_(rng_);
    for (int i = 0; i < n; ++i) {
        double pt = 0.5 + pt_exp_(rng_);
        if (pt > 5.0) pt = 5.0;  // pileup stays soft
        int pdg_choices[] = {pdg::PION_PLUS, -pdg::PION_PLUS, pdg::KAON_PLUS, -pdg::KAON_PLUS};
        Particle p{};
        p.pdg_id = pdg_choices[static_cast<int>(uniform_01_(rng_) * 4) % 4];
        p.pt = pt; p.eta = eta_dist_(rng_); p.phi = phi_dist_(rng_);
        p.mass = constants::PION_MASS;
        double p_mag = pt * std::cosh(p.eta);
        p.energy = std::sqrt(p_mag * p_mag + p.mass * p.mass);
        p.is_isolated = false;
        evt.particles.push_back(p);
    }
}

// --------------------------------------------------------------------------
// Event generation — the process mix is ~65% QCD, ~25% Z→μμ, ~10% ttbar.
// Not physically accurate cross-sections obviously, but gives us a nice
// distribution of event types for the trigger system to work with.
// --------------------------------------------------------------------------

Event EventGenerator::generate() {
    double r = uniform_01_(rng_);
    if (r < 0.65)      return generate_qcd_background();
    else if (r < 0.90) return generate_z_to_mumu();
    else                return generate_ttbar();
}

// Z → μ⁺μ⁻
// The bread and butter of dilepton analyses. We generate the Z mass
// from a Breit-Wigner, decay it into two muons in the rest frame,
// then boost everything into the lab frame. This way the dimuon
// invariant mass actually peaks at ~91 GeV like it should.
Event EventGenerator::generate_z_to_mumu() {
    Event evt{};
    evt.event_id = ++event_counter_;
    evt.run_number = run_number_;
    evt.timestamp_ms = current_timestamp_ms();
    evt.event_type = "z_mumu";
    evt.primary_vertices = 1 + static_cast<int>(pileup_dist_(rng_) * 0.3);

    double z_mass = breit_wigner(constants::Z_MASS, constants::Z_WIDTH);

    // Z boson lab-frame kinematics
    std::exponential_distribution<double> z_pt_dist(0.03);
    double z_pt = z_pt_dist(rng_);
    double z_rapidity = std::normal_distribution<double>(0.0, 1.5)(rng_);
    double z_phi = phi_dist_(rng_);

    // Decay in Z rest frame: muons are back-to-back, each with E = M/2
    double cos_theta = std::uniform_real_distribution<double>(-1.0, 1.0)(rng_);
    double sin_theta = std::sqrt(1.0 - cos_theta * cos_theta);
    double phi_star = phi_dist_(rng_);

    double p_star = z_mass / 2.0;  // muon mass is negligible vs M_Z

    // muon 1 in Z rest frame
    double px1_rf = p_star * sin_theta * std::cos(phi_star);
    double py1_rf = p_star * sin_theta * std::sin(phi_star);
    double pz1_rf = p_star * cos_theta;
    double e1_rf  = p_star;

    // muon 2 is opposite
    double px2_rf = -px1_rf;
    double py2_rf = -py1_rf;
    double pz2_rf = -pz1_rf;
    double e2_rf  =  p_star;

    // longitudinal boost from Z rapidity
    double beta_z  = std::tanh(z_rapidity);
    double gamma_z = std::cosh(z_rapidity);

    // boost muons (longitudinal)
    double e1_l  = gamma_z * (e1_rf + beta_z * pz1_rf);
    double pz1_l = gamma_z * (pz1_rf + beta_z * e1_rf);
    double e2_l  = gamma_z * (e2_rf + beta_z * pz2_rf);
    double pz2_l = gamma_z * (pz2_rf + beta_z * e2_rf);


    // Now apply transverse boost/rotation to both muons
    // Instead of splitting pT, we'll treat the Z boson as having a pT
    // and correctly rotate/boost the system.
    // For simplicity and correctness: boost along Z direction in transverse plane
    double z_px = z_pt * std::cos(z_phi);
    double z_py = z_pt * std::sin(z_phi);
    double z_ee = std::sqrt(z_pt * z_pt + z_mass * z_mass * gamma_z * gamma_z);
    double beta_t_x = z_px / z_ee;
    double beta_t_y = z_py / z_ee;
    double gamma_t  = 1.0 / std::sqrt(std::max(1e-10, 1.0 - beta_t_x * beta_t_x - beta_t_y * beta_t_y));

    auto boost = [&](double e_in, double px_in, double py_in, double pz_in) {
        double bp = beta_t_x * px_in + beta_t_y * py_in;
        double e_out  = gamma_t * (e_in + bp);
        double fact   = (gamma_t - 1.0) * bp / (beta_t_x * beta_t_x + beta_t_y * beta_t_y + 1e-10) + gamma_t * e_in;
        double px_out = px_in + fact * beta_t_x;
        double py_out = py_in + fact * beta_t_y;
        double pz_out = pz_in;
        return std::make_tuple(e_out, px_out, py_out, pz_out);
    };

    auto [e1, px1, py1, pz1] = boost(e1_l, px1_rf, py1_rf, pz1_l);
    auto [e2, px2, py2, pz2] = boost(e2_l, px2_rf, py2_rf, pz2_l);

    // convert (px, py, pz, E) → (pt, eta, phi, E) for each muon
    auto to_obs = [](double px, double py, double pz) {
        double pt  = std::sqrt(px * px + py * py);
        double p   = std::sqrt(px * px + py * py + pz * pz);
        double eta = 0.5 * std::log((p + pz) / std::max(p - pz, 1e-10));
        double phi = std::atan2(py, px);
        return std::make_tuple(pt, eta, phi);
    };

    auto [pt1, eta1, phi1] = to_obs(px1, py1, pz1);
    auto [pt2, eta2, phi2] = to_obs(px2, py2, pz2);

    Particle mu1{};
    mu1.pdg_id = -pdg::MUON; mu1.pt = pt1; mu1.eta = eta1;
    mu1.phi = phi1; mu1.energy = e1;
    mu1.mass = constants::MUON_MASS; mu1.is_isolated = true;

    Particle mu2{};
    mu2.pdg_id = pdg::MUON; mu2.pt = pt2; mu2.eta = eta2;
    mu2.phi = phi2; mu2.energy = e2;
    mu2.mass = constants::MUON_MASS; mu2.is_isolated = true;

    evt.particles.push_back(mu1);
    evt.particles.push_back(mu2);


    // toss in a few ISR jets
    int n_jets = std::poisson_distribution<int>(2)(rng_);
    for (int i = 0; i < n_jets; ++i) {
        double jpt = 20.0 + pt_exp_(rng_) * 50.0;
        evt.particles.push_back(make_jet(jpt, eta_dist_(rng_), phi_dist_(rng_)));
    }

    add_pileup_particles(evt);

    // Z events have small genuine MET (no neutrinos), so this is
    // mostly detector resolution smearing
    double met_x = std::normal_distribution<double>(0.0, 15.0)(rng_);
    double met_y = std::normal_distribution<double>(0.0, 15.0)(rng_);
    evt.met = std::sqrt(met_x * met_x + met_y * met_y);
    evt.met_phi = std::atan2(met_y, met_x);
    evt.num_muons = 2;
    evt.num_electrons = 0;
    evt.num_jets = n_jets;
    evt.num_particles = static_cast<int>(evt.particles.size());
    evt.sum_et = 0;
    for (const auto& p : evt.particles) evt.sum_et += p.pt;
    return evt;
}

// tt̄ → ℓ + jets (semi-leptonic)
// One top decays leptonically (W → ℓν), the other hadronically (W → qq̄).
// So we expect: 1 lepton, large MET from the neutrino, 4-6 jets (2 b-tagged).
Event EventGenerator::generate_ttbar() {
    Event evt{};
    evt.event_id = ++event_counter_;
    evt.run_number = run_number_;
    evt.timestamp_ms = current_timestamp_ms();
    evt.event_type = "ttbar";
    evt.primary_vertices = 1 + static_cast<int>(pileup_dist_(rng_) * 0.3);

    // decide if the lepton is a muon or electron (50/50)
    bool is_muon = uniform_01_(rng_) < 0.5;
    std::exponential_distribution<double> lep_pt_dist(0.02);
    double lep_pt  = 25.0 + lep_pt_dist(rng_);
    double lep_eta = std::normal_distribution<double>(0.0, 1.8)(rng_);
    double lep_phi = phi_dist_(rng_);
    int charge = uniform_01_(rng_) < 0.5 ? +1 : -1;

    if (is_muon) {
        evt.particles.push_back(make_muon(lep_pt, lep_eta, lep_phi, charge));
        evt.num_muons = 1; evt.num_electrons = 0;
    } else {
        evt.particles.push_back(make_electron(lep_pt, lep_eta, lep_phi, charge));
        evt.num_muons = 0; evt.num_electrons = 1;
    }

    // 4-7 jets total: first two are b-jets, rest are light jets from W and ISR
    std::uniform_int_distribution<int> njet_dist(4, 7);
    int n_jets = njet_dist(rng_);
    evt.num_jets = n_jets;

    for (int i = 0; i < n_jets; ++i) {
        double jpt  = 30.0 + std::exponential_distribution<double>(0.015)(rng_);
        double jeta = std::normal_distribution<double>(0.0, 2.0)(rng_);
        double jphi = phi_dist_(rng_);
        int pdg = (i < 2) ? pdg::BOTTOM : pdg::GLUON;  // tag the b-jets
        evt.particles.push_back(make_jet(jpt, jeta, jphi, pdg));
    }

    add_pileup_particles(evt);

    // large MET from the neutrino — roughly opposite the lepton in phi
    double nu_pt  = 20.0 + std::exponential_distribution<double>(0.02)(rng_);
    double nu_phi = lep_phi + constants::PI + std::normal_distribution<double>(0.0, 0.5)(rng_);
    evt.met = nu_pt + std::abs(std::normal_distribution<double>(0.0, 10.0)(rng_));
    evt.met_phi = nu_phi;
    evt.num_particles = static_cast<int>(evt.particles.size());
    evt.sum_et = 0;
    for (const auto& p : evt.particles) evt.sum_et += p.pt;
    return evt;
}

// QCD multi-jet background
// The workhorse of hadron colliders — lots of jets with a steeply
// falling pT spectrum (roughly pT^-4). Occasionally a jet fakes
// a muon, which is why we need isolation cuts in the trigger.
Event EventGenerator::generate_qcd_background() {
    Event evt{};
    evt.event_id = ++event_counter_;
    evt.run_number = run_number_;
    evt.timestamp_ms = current_timestamp_ms();
    evt.event_type = "qcd";
    evt.primary_vertices = 1 + static_cast<int>(pileup_dist_(rng_) * 0.3);

    std::uniform_int_distribution<int> njet_dist(2, 8);
    int n_jets = njet_dist(rng_);
    evt.num_jets = n_jets;

    for (int i = 0; i < n_jets; ++i) {
        // power-law spectrum: sample via inverse CDF of p(pT) ~ pT^-4
        double u = uniform_01_(rng_);
        double jpt = 20.0 / std::pow(std::max(u, 0.001), 0.25);
        if (jpt > 2000.0) jpt = 2000.0;
        evt.particles.push_back(make_jet(jpt, std::normal_distribution<double>(0.0, 2.5)(rng_), phi_dist_(rng_)));
    }

    // ~5% of QCD events produce a fake (non-isolated) muon from heavy-flavor decay
    if (uniform_01_(rng_) < 0.05) {
        double lpt = 10.0 + pt_exp_(rng_) * 20.0;
        auto mu = make_muon(lpt, eta_dist_(rng_), phi_dist_(rng_), uniform_01_(rng_) < 0.5 ? +1 : -1);
        mu.is_isolated = false;  // this is the key — isolation kills fakes
        evt.particles.push_back(mu);
        evt.num_muons = 1;
    } else {
        evt.num_muons = 0;
    }
    evt.num_electrons = 0;

    add_pileup_particles(evt);

    // QCD events have small genuine MET (just mismeasurement)
    double mx = std::normal_distribution<double>(0.0, 20.0)(rng_);
    double my = std::normal_distribution<double>(0.0, 20.0)(rng_);
    evt.met = std::sqrt(mx * mx + my * my);
    evt.met_phi = std::atan2(my, mx);
    evt.num_particles = static_cast<int>(evt.particles.size());
    evt.sum_et = 0;
    for (const auto& p : evt.particles) evt.sum_et += p.pt;
    return evt;
}

// --------------------------------------------------------------------------
// JSON output — one line per event, compact format.
// We round floating-point values to 3 decimal places to keep
// the output size manageable without losing meaningful precision.
// --------------------------------------------------------------------------

std::string Event::to_json() const {
    nlohmann::json j;
    j["event_id"]         = event_id;
    j["run_number"]       = run_number;
    j["timestamp_ms"]     = timestamp_ms;
    j["event_type"]       = event_type;
    j["num_particles"]    = num_particles;
    j["met"]              = std::round(met * 1000.0) / 1000.0;
    j["met_phi"]          = std::round(met_phi * 1000.0) / 1000.0;
    j["sum_et"]           = std::round(sum_et * 100.0) / 100.0;
    j["num_jets"]         = num_jets;
    j["num_muons"]        = num_muons;
    j["num_electrons"]    = num_electrons;
    j["primary_vertices"] = primary_vertices;

    auto& pa = j["particles"] = nlohmann::json::array();
    for (const auto& p : particles) {
        pa.push_back({
            {"pdg_id",      p.pdg_id},
            {"pt",          std::round(p.pt  * 1000.0) / 1000.0},
            {"eta",         std::round(p.eta * 1000.0) / 1000.0},
            {"phi",         std::round(p.phi * 1000.0) / 1000.0},
            {"energy",      std::round(p.energy * 1000.0) / 1000.0},
            {"mass",        std::round(p.mass   * 1000.0) / 1000.0},
            {"is_isolated", p.is_isolated}
        });
    }
    return j.dump();
}

} // namespace lhc
