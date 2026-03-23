#!/usr/bin/env bash
# ============================================================================
# import_skills.sh — Import SKILL.md files from any GitHub repo into ChromaDB
#
# Usage:
#   ./scripts/import_skills.sh                          # interactive (auto port 9000)
#   ./scripts/import_skills.sh <repo_url> [branch]      # non-interactive
#   ./scripts/import_skills.sh --dry-run <repo_url>      # preview only
#   ./scripts/import_skills.sh --port 8888 <repo_url>    # custom ChromaDB port
#
# Environment:
#   MCP_CHROMA_PORT  — ChromaDB port (default: 9000 for Docker setup)
#   IMPORT_WORKERS   — Number of threads (default: 5)
#
# Examples:
#   ./scripts/import_skills.sh https://github.com/HoangNguyen0403/agent-skills-standard develop
#   ./scripts/import_skills.sh --dry-run https://github.com/user/repo main
#   MCP_CHROMA_PORT=8888 ./scripts/import_skills.sh https://github.com/user/repo
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ---------------------------------------------------------------------------
# Resolve script directory (handles symlinks)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SEED_SCRIPT="$SCRIPT_DIR/seed_skills.py"
PYTHON="${PYTHON:-python3}"
CLONE_DIR=""
DRY_RUN=""
WORKERS="${IMPORT_WORKERS:-5}"
CHROMA_PORT="${MCP_CHROMA_PORT:-9000}"

# ---------------------------------------------------------------------------
# Cleanup on exit
# ---------------------------------------------------------------------------
cleanup() {
    if [[ -n "$CLONE_DIR" && -d "$CLONE_DIR" ]]; then
        echo -e "${YELLOW}🧹 Cleaning up: $CLONE_DIR${NC}"
        rm -rf "$CLONE_DIR"
    fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo -e "${BOLD}${CYAN}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║       🧠 MCP Skill Importer — ChromaDB L2 Seeder       ║"
echo "║                    v1.0.14                              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
REPO_URL=""
BRANCH=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        --workers)
            WORKERS="$2"
            shift 2
            ;;
        --port)
            CHROMA_PORT="$2"
            shift 2
            ;;
        -*)
            echo -e "${RED}❌ Unknown option: $1${NC}"
            exit 1
            ;;
        *)
            if [[ -z "$REPO_URL" ]]; then
                REPO_URL="$1"
            elif [[ -z "$BRANCH" ]]; then
                BRANCH="$1"
            fi
            shift
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Interactive prompts (if not passed as args)
# ---------------------------------------------------------------------------
if [[ -z "$REPO_URL" ]]; then
    echo -e "${BOLD}🔗 Enter GitHub repo URL:${NC}"
    echo -e "   ${YELLOW}(e.g. https://github.com/HoangNguyen0403/agent-skills-standard)${NC}"
    read -rp "   > " REPO_URL
    echo ""
fi

if [[ -z "$REPO_URL" ]]; then
    echo -e "${RED}❌ Repo URL is required!${NC}"
    exit 1
fi

if [[ -z "$BRANCH" ]]; then
    echo -e "${BOLD}🌿 Enter branch name ${YELLOW}(default: develop)${NC}${BOLD}:${NC}"
    read -rp "   > " BRANCH
    BRANCH="${BRANCH:-develop}"
    echo ""
fi

# ---------------------------------------------------------------------------
# Validate prerequisites
# ---------------------------------------------------------------------------
echo -e "${CYAN}🔍 Checking prerequisites...${NC}"

# Python
if ! command -v "$PYTHON" &>/dev/null; then
    echo -e "${RED}❌ Python3 not found. Install Python 3.10+${NC}"
    exit 1
fi
echo -e "   ✅ Python: $($PYTHON --version 2>&1)"

# chromadb module
if ! "$PYTHON" -c "import chromadb" 2>/dev/null; then
    echo -e "${RED}❌ chromadb not installed. Run: pip install chromadb${NC}"
    exit 1
fi
echo -e "   ✅ chromadb: installed"

# seed_skills.py exists
if [[ ! -f "$SEED_SCRIPT" ]]; then
    echo -e "${RED}❌ seed_skills.py not found at: $SEED_SCRIPT${NC}"
    exit 1
fi
echo -e "   ✅ seed_skills.py: found"

# git
if ! command -v git &>/dev/null; then
    echo -e "${RED}❌ git not found${NC}"
    exit 1
fi
echo -e "   ✅ git: $(git --version)"
echo ""

# ---------------------------------------------------------------------------
# Clone repo
# ---------------------------------------------------------------------------
CLONE_DIR="$(mktemp -d /tmp/skill-import-XXXXXX)"
echo -e "${CYAN}⏳ Cloning ${BOLD}$REPO_URL${NC}${CYAN} (branch: ${BOLD}$BRANCH${NC}${CYAN})...${NC}"

if ! git clone --branch "$BRANCH" --depth 1 --quiet "$REPO_URL" "$CLONE_DIR" 2>&1; then
    echo -e "${RED}❌ Git clone failed! Check URL and branch name.${NC}"
    exit 1
fi

# ---------------------------------------------------------------------------
# Detect skills/ directory
# ---------------------------------------------------------------------------
SKILLS_DIR=""
if [[ -d "$CLONE_DIR/skills" ]]; then
    SKILLS_DIR="$CLONE_DIR/skills"
elif [[ -d "$CLONE_DIR/src/skills" ]]; then
    SKILLS_DIR="$CLONE_DIR/src/skills"
else
    # Search for any SKILL.md to find the skills root
    FIRST_SKILL=$(find "$CLONE_DIR" -name "SKILL.md" -type f | head -1)
    if [[ -n "$FIRST_SKILL" ]]; then
        # Go up 3 levels: SKILL.md → skill-name → category → skills/
        SKILLS_DIR="$(dirname "$(dirname "$(dirname "$FIRST_SKILL")")")"
    fi
fi

if [[ -z "$SKILLS_DIR" || ! -d "$SKILLS_DIR" ]]; then
    echo -e "${RED}❌ Could not find skills/ directory in the repo!${NC}"
    echo "   Expected structure: skills/{category}/{skill-name}/SKILL.md"
    exit 1
fi

SKILL_COUNT=$(find "$SKILLS_DIR" -name "SKILL.md" -type f | wc -l | tr -d ' ')
CATEGORY_COUNT=$(find "$SKILLS_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')

echo -e "${GREEN}✅ Found ${BOLD}${SKILL_COUNT}${NC}${GREEN} skills in ${BOLD}${CATEGORY_COUNT}${NC}${GREEN} categories${NC}"
echo -e "   📁 Skills dir: $SKILLS_DIR"
echo ""

# ---------------------------------------------------------------------------
# Run Python importer
# ---------------------------------------------------------------------------
if [[ -n "$DRY_RUN" ]]; then
    echo -e "${YELLOW}🔍 DRY-RUN mode — no data will be written${NC}"
fi

echo -e "${CYAN}🚀 Starting import (${WORKERS} threads)...${NC}"
echo ""

# Run from PROJECT_ROOT so src/ is importable
PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH:-}" \
    "$PYTHON" "$SEED_SCRIPT" \
    "$SKILLS_DIR" \
    --workers "$WORKERS" \
    --port "$CHROMA_PORT" \
    $DRY_RUN

EXIT_CODE=$?

echo ""
if [[ $EXIT_CODE -eq 0 ]]; then
    echo -e "${GREEN}${BOLD}🎉 Import completed successfully!${NC}"
    if [[ -f "$SCRIPT_DIR/last_import_report.json" ]]; then
        echo -e "   📄 Report: $SCRIPT_DIR/last_import_report.json"
    fi
else
    echo -e "${RED}${BOLD}❌ Import failed (exit code: $EXIT_CODE)${NC}"
fi

exit $EXIT_CODE
