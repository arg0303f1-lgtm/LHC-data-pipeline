#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# LHC Data Pipeline — Setup Script
# ──────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  LHC Data Pipeline — Setup                   ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── 1. Build C++ Event Generator ────────────────────────────
info "Building C++ event generator..."
cd "$PROJECT_DIR/event_generator"

if command -v cmake &> /dev/null && command -v g++ &> /dev/null; then
    mkdir -p build && cd build
    cmake .. -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -5
    make -j"$(nproc)" 2>&1 | tail -3
    ok "Event generator built: event_generator/build/event_generator"
else
    warn "cmake or g++ not found — skipping C++ build"
    warn "Install with: sudo apt install cmake g++ (Ubuntu/Debian)"
fi

# ── 2. Install Python Dependencies ──────────────────────────
info "Installing Python dependencies..."
cd "$PROJECT_DIR"

if command -v pip3 &> /dev/null; then
    pip3 install -r requirements.txt --quiet 2>/dev/null || pip install -r requirements.txt --quiet
    ok "Python packages installed"
elif command -v pip &> /dev/null; then
    pip install -r requirements.txt --quiet
    ok "Python packages installed"
else
    warn "pip not found — install Python dependencies manually"
fi

# ── 3. Create data directory ────────────────────────────────
mkdir -p "$PROJECT_DIR/data"
ok "Data directory ready"

# ── 4. Docker check ─────────────────────────────────────────
if command -v docker &> /dev/null; then
    ok "Docker found"
    info "Start Kafka with: docker compose up -d"
else
    warn "Docker not found — needed for Kafka"
    warn "Install from: https://docs.docker.com/get-docker/"
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  Setup Complete!                              ║"
echo "╠══════════════════════════════════════════════╣"
echo "║                                              ║"
echo "║  Quick Start:                                ║"
echo "║  1. docker compose up -d                     ║"
echo "║  2. ./event_generator/build/event_generator \ ║"
echo "║       -n 50000 | python -m pipeline.producer ║"
echo "║  3. python -m pipeline.consumer              ║"
echo "║  4. python -m dashboard.server               ║"
echo "║  5. Open http://localhost:5000                ║"
echo "║                                              ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
