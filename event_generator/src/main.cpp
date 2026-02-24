// main.cpp
// Divij Bhoj, 2026
//
// CLI tool that generates simulated LHC events and dumps them as
// one-JSON-per-line to stdout. Designed to be piped directly into
// the Kafka producer:
//
//   ./event_generator -n 50000 | python -m pipeline.producer
//
// Supports rate limiting (--rate), custom seeds (-s), and infinite
// streaming mode (-n 0). Progress is printed to stderr so it
// doesn't interfere with the JSON output on stdout.

#include "event_generator.h"

#include <chrono>
#include <csignal>
#include <cstdlib>
#include <iostream>
#include <string>
#include <thread>

static volatile bool g_running = true;
void signal_handler(int) { g_running = false; }

void print_usage(const char* prog) {
    std::cerr
        << "Usage: " << prog << " [OPTIONS]\n"
        << "\nSimulates LHC proton-proton collision events and outputs JSON to stdout.\n"
        << "\nOptions:\n"
        << "  -n NUM     Number of events (0 = infinite, default: 1000)\n"
        << "  -r NUM     Run number (default: 1)\n"
        << "  -s NUM     Random seed (default: 42)\n"
        << "  -d MS      Delay between events in ms (default: 0)\n"
        << "  --rate HZ  Target event rate in Hz (default: unlimited)\n"
        << "  --pileup N Mean pileup interactions (default: 25)\n"
        << "  -h         Show this help\n"
        << "\nExamples:\n"
        << "  " << prog << " -n 50000                       # 50k events, full speed\n"
        << "  " << prog << " -n 0 --rate 100                # infinite stream at 100 Hz\n"
        << "  " << prog << " -n 10000 | python -m pipeline.producer  # pipe to Kafka\n";
}

int main(int argc, char* argv[]) {
    uint64_t num_events  = 1000;
    uint64_t run_number  = 1;
    unsigned seed        = 42;
    int      delay_ms    = 0;
    double   target_rate = 0;
    int      pileup      = 25;

    // quick and dirty arg parsing — works fine for a tool like this
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if      (arg == "-n"       && i+1 < argc) num_events  = std::stoull(argv[++i]);
        else if (arg == "-r"       && i+1 < argc) run_number  = std::stoull(argv[++i]);
        else if (arg == "-s"       && i+1 < argc) seed        = std::stoul(argv[++i]);
        else if (arg == "-d"       && i+1 < argc) delay_ms    = std::stoi(argv[++i]);
        else if (arg == "--rate"   && i+1 < argc) target_rate = std::stod(argv[++i]);
        else if (arg == "--pileup" && i+1 < argc) pileup      = std::stoi(argv[++i]);
        else if (arg == "-h" || arg == "--help") { print_usage(argv[0]); return 0; }
        else { std::cerr << "Unknown option: " << arg << "\n"; print_usage(argv[0]); return 1; }
    }

    if (target_rate > 0) delay_ms = static_cast<int>(1000.0 / target_rate);

    std::signal(SIGINT,  signal_handler);
    std::signal(SIGPIPE, signal_handler);

    lhc::EventGenerator gen(run_number, seed);
    gen.set_pileup(pileup);

    // all status output goes to stderr so stdout is pure JSON
    std::cerr << "╔══════════════════════════════════════════╗\n"
              << "║   LHC Event Generator v1.0               ║\n"
              << "╠══════════════════════════════════════════╣\n"
              << "║  Run:     " << run_number << "\n"
              << "║  Seed:    " << seed << "\n"
              << "║  Events:  " << (num_events == 0 ? "infinite" : std::to_string(num_events)) << "\n"
              << "║  Pileup:  <" << pileup << ">\n"
              << "║  Rate:    " << (delay_ms > 0 ? std::to_string(1000/delay_ms) + " Hz" : "max") << "\n"
              << "╚══════════════════════════════════════════╝\n";

    uint64_t count = 0;
    auto start = std::chrono::steady_clock::now();

    while (g_running && (num_events == 0 || count < num_events)) {
        auto event = gen.generate();
        std::cout << event.to_json() << '\n';
        ++count;

        if (delay_ms > 0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(delay_ms));
        }

        // periodic progress update (every 10k events)
        if (count % 10000 == 0) {
            auto now = std::chrono::steady_clock::now();
            double elapsed = std::chrono::duration<double>(now - start).count();
            std::cerr << "\r  Generated " << count << " events ("
                      << static_cast<int>(count / elapsed) << " evt/s)" << std::flush;
        }
    }

    auto end = std::chrono::steady_clock::now();
    double total = std::chrono::duration<double>(end - start).count();
    std::cerr << "\n\n  Done: " << count << " events in " << total << "s ("
              << static_cast<int>(count / total) << " evt/s)\n";

    return 0;
}
