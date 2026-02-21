#!/usr/bin/env bash
# MDx Code installer
# Usage: curl -fsSL https://raw.githubusercontent.com/dhotherm/mdx-code/main/install.sh | bash

set -euo pipefail

# Colors (respect NO_COLOR)
if [ -z "${NO_COLOR:-}" ] && [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    DIM='\033[2m'
    BOLD='\033[1m'
    RESET='\033[0m'
else
    RED='' GREEN='' DIM='' BOLD='' RESET=''
fi

info()  { echo -e "  ${GREEN}✓${RESET} $1"; }
warn()  { echo -e "  ${RED}✗${RESET} $1"; }
dim()   { echo -e "  ${DIM}$1${RESET}"; }

echo ""
echo -e "  ${BOLD}MDx Code${RESET} — The AI Engineering Manager"
echo ""

# Check Python version (3.10+)
if ! command -v python3 &> /dev/null; then
    warn "Python 3 not found. Install Python 3.10+ first."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    warn "Python $PYTHON_VERSION found. MDx Code requires 3.10+."
    exit 1
fi
info "Python $PYTHON_VERSION"

# Check pip
if ! python3 -m pip --version &> /dev/null; then
    warn "pip not found. Install pip first."
    exit 1
fi

# Install MDx Code
dim "Installing MDx Code..."
if python3 -m pip install --quiet --user mdx-code 2>/dev/null; then
    info "MDx Code installed"
elif python3 -m pip install --quiet --user git+https://github.com/dhotherm/mdx-code.git 2>/dev/null; then
    info "MDx Code installed (from GitHub)"
else
    warn "Installation failed. Try manually: pip install git+https://github.com/dhotherm/mdx-code.git"
    exit 1
fi

# Verify installation
if command -v mdx &> /dev/null; then
    MDX_VERSION=$(mdx --version 2>/dev/null || echo "unknown")
    info "$MDX_VERSION"
else
    # Check if user pip bin is in PATH
    USER_BIN=$(python3 -m site --user-base)/bin
    if [ -f "$USER_BIN/mdx" ]; then
        warn "mdx installed but not in PATH."
        echo ""
        echo "  Add this to your shell config:"
        echo ""
        echo "    export PATH=\"$USER_BIN:\$PATH\""
        echo ""
        exit 1
    fi
    warn "Installation succeeded but 'mdx' command not found."
    exit 1
fi

# Detect existing backends (preview, not full setup)
echo ""
dim "Detecting AI coding tools..."

BACKEND_COUNT=0

if command -v claude &> /dev/null; then
    CLAUDE_VER=$(claude --version 2>/dev/null | head -1 || echo "installed")
    info "Claude Code    $CLAUDE_VER"
    BACKEND_COUNT=$((BACKEND_COUNT + 1))
else
    dim "Claude Code    not found"
fi

if command -v gemini &> /dev/null; then
    GEMINI_VER=$(gemini --version 2>/dev/null | head -1 || echo "installed")
    info "Gemini CLI     $GEMINI_VER"
    BACKEND_COUNT=$((BACKEND_COUNT + 1))
else
    dim "Gemini CLI     not found"
fi

if command -v codex &> /dev/null; then
    CODEX_VER=$(codex --version 2>/dev/null | head -1 || echo "installed")
    info "Codex CLI      $CODEX_VER"
    BACKEND_COUNT=$((BACKEND_COUNT + 1))
else
    dim "Codex CLI      not found"
fi

echo ""
if [ "$BACKEND_COUNT" -gt 0 ]; then
    info "$BACKEND_COUNT backend(s) detected. You're ready."
else
    warn "No backends found. Install at least one:"
    dim "  Claude Code: npm install -g @anthropic-ai/claude-code"
    dim "  Gemini CLI:  npm install -g @google/gemini-cli"
    dim "  Codex CLI:   npm install -g @openai/codex"
fi

echo ""
echo -e "  ${BOLD}Get started:${RESET} run ${GREEN}mdx${RESET}"
echo ""
