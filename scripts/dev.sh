#!/usr/bin/env bash
set -e

echo "Start gateway in one terminal:"
echo "  cd apps/gateway && pnpm install && pnpm dev"

echo "Start agent worker in another terminal:"
echo "  cd apps/agent && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python -m ag3nt_agent.worker"
