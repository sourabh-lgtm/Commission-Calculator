#!/bin/bash
set -e

echo "Starting Commission Calculator..."

if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 not found. Please install Python 3.12+"
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "Installing dependencies..."
pip install -r requirements.txt --quiet

echo ""
echo "Launching Commission Calculator at http://localhost:8050"
python3 launch.py "$@"
