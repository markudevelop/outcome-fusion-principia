#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
claude plugin marketplace add "$DIR"
echo "Marketplace added: outcome-fusion-local"
echo "Now open Claude Code and run: /plugin install outcome-fusion-principia@outcome-fusion-local"
echo "Then run: /reload-plugins"
