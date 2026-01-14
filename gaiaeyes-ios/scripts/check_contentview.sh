#!/usr/bin/env bash
set -euo pipefail

FILE="ios/GaiaExporter/Views/ContentView.swift"

if [[ ! -f "$FILE" ]]; then
  echo "error: missing $FILE" >&2
  exit 1
fi

if command -v xcrun >/dev/null 2>&1; then
  echo "Running swiftc syntax check for ContentView.swift…"
  xcrun swiftc -typecheck "$FILE" 2>&1 | sed -n '1,120p'
else
  echo "warning: xcrun not found; skipping swiftc -typecheck probe" >&2
fi

if [[ $(grep -Fxc "struct ContentView: View {" "$FILE") -ne 1 ]]; then
  echo "error: struct declaration must be exactly 'struct ContentView: View {'" >&2
  exit 1
fi

if grep -n "<#.*#>" "$FILE" >/dev/null; then
  first=$(grep -n "<#.*#>" "$FILE" | head -n1)
  echo "error: placeholder token found: $first" >&2
  exit 1
fi

python3 <<'PY'
from pathlib import Path
import sys
import re

path = Path("ios/GaiaExporter/Views/ContentView.swift")
text = path.read_text()

def check_balanced(marker: str) -> None:
    idx = text.find(marker)
    if idx == -1:
        print(f"error: missing {marker.strip()}", file=sys.stderr)
        sys.exit(1)
    start = text.find('{', idx)
    if start == -1:
        print(f"error: missing opening brace for {marker.strip()}", file=sys.stderr)
        sys.exit(1)
    depth = 0
    pos = start
    while pos < len(text):
        ch = text[pos]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return
            if depth < 0:
                print(f"error: brace mismatch near line containing {marker.strip()}", file=sys.stderr)
                sys.exit(1)
        pos += 1
    print(f"error: unterminated block for {marker.strip()}", file=sys.stderr)
    sys.exit(1)

check_balanced("struct ContentView: View {")
check_balanced("    var body: some View {")
if "private var contentViewBody: some View {" in text:
    check_balanced("    private var contentViewBody: some View {")

block_start = text.index("struct ContentView: View {")
block_open = text.index('{', block_start)
depth = 0
pos = block_open
while pos < len(text):
    if text[pos] == '{':
        depth += 1
    elif text[pos] == '}':
        depth -= 1
        if depth == 0:
            break
    pos += 1
block = text[block_open + 1:pos]
depth = 0
body_count = 0
for line in block.splitlines():
    trimmed = line.strip()
    if trimmed.startswith("var body: some View {") and depth == 0:
        body_count += 1
    depth += line.count('{')
    depth -= line.count('}')
if body_count != 1:
    print(f"error: expected exactly one 'var body: some View {{' at top level (found {body_count})", file=sys.stderr)
    sys.exit(1)

invalid_style = re.compile(r"\.foregroundS(?!tyle)")
invalid_trunc = re.compile(r"\.foreground(?!Style)(?!Color)")
for idx, line in enumerate(text.splitlines(), 1):
    if invalid_style.search(line):
        print(f"error: truncated modifier near line {idx}: {line.strip()}", file=sys.stderr)
        sys.exit(1)
    if invalid_trunc.search(line):
        print(f"error: truncated modifier near line {idx}: {line.strip()}", file=sys.stderr)
        sys.exit(1)
PY

echo "ContentView.swift passed smoke checks."
