#!/bin/sh
# Warm benchmark: one warm-up pass, then three rounds of single, parallel 4, parallel 8.
# Peak RSS from /usr/bin/time -l (bytes; parent process only for the parallel modes).
ROOT="$1"; B="$(dirname "$0")/bench.py"
uv run python "$B" "$ROOT" single > /dev/null
for round in 1 2 3; do
  for mode in "single" "parallel 4" "parallel 8"; do
    echo "round $round: $mode"
    /usr/bin/time -l uv run python "$B" "$ROOT" $mode 2>&1 | grep -E '"mode"|real|maximum resident'
  done
done
