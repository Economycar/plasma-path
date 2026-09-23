#!/usr/bin/env bash
# Start the Plasma Path web UI.  First run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd "$(dirname "$0")"
exec .venv/bin/python app/server.py
