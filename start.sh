#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ ! -f "venv/bin/python3" ]; then
    echo "Virtual environment not found. Please follow the README instructions to set it up."
    exit 1
fi
# Run in the background
./venv/bin/python3 main.pyw &