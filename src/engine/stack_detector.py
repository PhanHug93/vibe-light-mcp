"""Stack Detector — Tech stack auto-detection via file signatures + keyword scan.

Standalone module, no MCP dependency. Extracted from ``server.py`` (SRP).

Usage::

    from src.engine.stack_detector import detect_stack_enhanced, read_knowledge
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration — Stack Signatures & Keyword Triggers
# ---------------------------------------------------------------------------

# Ordered by specificity: most specific first.
STACK_SIGNATURES: list[tuple[str, str]] = [
    ("settings.gradle.kts", "kmp"),
    ("build.gradle.kts",    "android_kotlin"),
    ("build.gradle",        "android_kotlin"),
    ("pubspec.yaml",        "flutter_dart"),
    ("Podfile",             "ios_swift"),
    ("Package.swift",       "ios_swift"),
    ("pyproject.toml",      "python"),
    ("setup.py",            "python"),
    ("Pipfile",             "python"),
    ("requirements.txt",    "python"),
    ("package.json",        "react_native"),  # disambiguated via keyword scan
    ("package.json",        "vue_js"),
]

STACK_TRIGGERS: dict[str, dict[str, list[str]]] = {
    "python": {
        "extensions": [".py", ".pyi"],
        "keywords": [
            "FastAPI", "@app.route", "BaseModel", "pydantic",
            "async def", "asyncio", "pytest", "django",
            "flask", "SQLAlchemy", "dataclass", "import typing",
            "def main", "if __name__", "from __future__",
        ],
    },
    "android_kotlin": {
        "extensions": [".kt", ".kts"],
        "keywords": [
            "@Composable", "ViewModel", "Hilt", "@Inject", "@Provides",
            "suspend fun", "StateFlow", "viewModelScope", "NavHost",
            "Room", "@Entity", "@Dao", "Retrofit", "OkHttpClient",
        ],
    },
    "flutter_dart": {
        "extensions": [".dart"],
        "keywords": [
            "StatelessWidget", "StatefulWidget", "BuildContext",
            "Bloc", "Cubit", "Provider", "GetX", "Riverpod",
            "GoRouter", "AutoRoute", "pubspec",
        ],
    },
    "kmp": {
        "extensions": [".kt", ".kts"],
        "keywords": [
            "expect ", "actual ", "commonMain", "Multiplatform",
            "iosMain", "androidMain", "KMM",
        ],
    },
    "vue_js": {
        "extensions": [".vue", ".ts", ".js"],
        "keywords": [
            "defineComponent", "ref(", "reactive(", "computed(",
            "Pinia", "createApp", "createRouter", "<template>",
            "v-model", "v-if", "v-for",
        ],
    },
    "react_native": {
        "extensions": [".tsx", ".ts", ".jsx"],
        "keywords": [
            "react-native", "React Native", "NavigationContainer",
            "createNativeStackNavigator", "FlatList", "StyleSheet",
            "useNavigation", "Pressable", "SafeAreaView",
        ],
    },
    "ios_swift": {
        "extensions": [".swift"],
        "keywords": [
            "@State", "@Binding", "@ObservedObject", "@StateObject",
            "NavigationStack", "@MainActor", "async throws",
            "UIViewController", "SwiftUI", "Combine",
        ],
    },
}

_SEARCH_DEPTH: int = 1  # root + one level deep
_KEYWORD_SCAN_MAX_FILES: int = 20
_KEYWORD_SCAN_MAX_BYTES: int = 50_000  # per file


# ---------------------------------------------------------------------------
# Detection Functions
# ---------------------------------------------------------------------------


def _detect_by_signature(project_path: Path) -> str | None:
    """Scan *project_path* for signature files and return the stack key."""
    for depth in range(_SEARCH_DEPTH + 1):
        search_dirs: list[Path] = (
            [project_path] if depth == 0
            else [d for d in project_path.iterdir() if d.is_dir()]
        )
        for directory in search_dirs:
            for signature, stack in STACK_SIGNATURES:
                if (directory / signature).exists():
                    return stack
    return None


def _scan_keywords(project_path: Path, stack: str) -> dict[str, int]:
    """Scan source files for keyword hits. Returns {keyword: count}."""
    triggers = STACK_TRIGGERS.get(stack)
    if not triggers:
        return {}

    extensions = set(triggers["extensions"])
    keywords = triggers["keywords"]
    hits: dict[str, int] = {}
    files_scanned = 0

    for source_file in project_path.rglob("*"):
        if files_scanned >= _KEYWORD_SCAN_MAX_FILES:
            break
        if not source_file.is_file():
            continue
        if source_file.suffix not in extensions:
            continue
        # Skip hidden dirs, build dirs, etc.
        parts = source_file.relative_to(project_path).parts
        if any(p.startswith(".") or p in ("build", "node_modules", ".gradle") for p in parts):
            continue

        try:
            content = source_file.read_text(encoding="utf-8", errors="ignore")
            if len(content) > _KEYWORD_SCAN_MAX_BYTES:
                content = content[:_KEYWORD_SCAN_MAX_BYTES]
        except (OSError, UnicodeDecodeError):
            continue

        files_scanned += 1
        for kw in keywords:
            count = content.count(kw)
            if count > 0:
                hits[kw] = hits.get(kw, 0) + count

    return hits


def detect_stack_enhanced(project_path: Path) -> dict:
    """Enhanced detection: file signature + keyword scan.

    Returns dict with: stack, method, keyword_hits, confidence.
    """
    stack = _detect_by_signature(project_path)
    method = "file_signature" if stack else "none"

    if stack is None:
        # Fallback: try keyword-only detection across all stacks
        best_stack = None
        best_score = 0
        for candidate_stack in STACK_TRIGGERS:
            hits = _scan_keywords(project_path, candidate_stack)
            score = sum(hits.values())
            if score > best_score:
                best_score = score
                best_stack = candidate_stack
        if best_stack and best_score >= 3:
            stack = best_stack
            method = "keyword_only"

    # Keyword scan for matched stack
    keyword_hits: dict[str, int] = {}
    confidence = 0.0
    if stack:
        keyword_hits = _scan_keywords(project_path, stack)
        total_hits = sum(keyword_hits.values())
        unique_keywords = len(keyword_hits)

        if method == "file_signature":
            confidence = min(0.7 + (unique_keywords * 0.05), 1.0)
        else:
            confidence = min(0.3 + (unique_keywords * 0.07), 0.9)

        if method == "file_signature" and keyword_hits:
            method = "file_signature + keyword_scan"

    return {
        "stack": stack,
        "method": method,
        "keyword_hits": keyword_hits,
        "confidence": round(confidence, 2),
    }


# ---------------------------------------------------------------------------
# Knowledge Reader
# ---------------------------------------------------------------------------


def read_knowledge(stack: str, tech_stacks_dir: Path) -> dict:
    """Read core rules/skills + list available references for *stack*.

    Args:
        stack: The tech stack key (e.g. ``android_kotlin``).
        tech_stacks_dir: Absolute path to the ``tech_stacks/`` directory.
    """
    stack_dir: Path = tech_stacks_dir / stack
    result: dict[str, str | list[str]] = {}

    # Core files (always loaded)
    for filename in ("rules.md", "skills.md"):
        filepath: Path = stack_dir / filename
        try:
            result[filename] = filepath.read_text(encoding="utf-8")
        except FileNotFoundError:
            result[filename] = f"⚠ {filepath} not found."

    # Progressive disclosure: list references (loaded on demand)
    refs_dir = stack_dir / "references"
    if refs_dir.is_dir():
        result["available_references"] = sorted(
            f.name for f in refs_dir.iterdir()
            if f.is_file() and f.suffix == ".md"
        )
    else:
        result["available_references"] = []

    return result
