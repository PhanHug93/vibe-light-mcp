#!/usr/bin/env python3
"""Scan configured skill repositories and write candidate manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import SKILL_REGISTRY_DIR  # noqa: E402

SOURCES_SCHEMA = "local-skill-sources/v0.0.1"
CANDIDATE_SCHEMA = "local-skill-candidate/v0.0.1"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_SAFE_ID_RE = re.compile(r"[^a-z0-9]+")
_DESTRUCTIVE_RE = re.compile(r"\brm\s+-rf\b|delete\s+all|drop\s+database", re.I)
_NETWORK_INSTALL_RE = re.compile(r"curl\s+.*\|\s*(sh|bash)|wget\s+.*\|\s*(sh|bash)", re.I)
_SECRET_RE = re.compile(r"\b(api[_-]?key|secret|token|password|authorization)\b", re.I)
_EXTERNAL_API_RE = re.compile(r"\b(openai|anthropic|github|slack|notion|jira)\s+api\b", re.I)


class CandidateSkip(ValueError):
    """Raised when a skill file is not importable as a candidate."""


def _as_posix(path: Path) -> str:
    return path.as_posix().strip("/")


def _path_is_under(path: Path, prefixes: list[str]) -> bool:
    rel = _as_posix(path)
    for prefix in prefixes:
        cleaned = prefix.strip("/")
        if rel == cleaned or rel.startswith(f"{cleaned}/"):
            return True
    return False


def parse_skill_markdown(path: Path, text: str) -> dict[str, str]:
    """Parse a SKILL.md file into frontmatter metadata and body."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise CandidateSkip(f"Missing YAML frontmatter: {path}")
    frontmatter = yaml.safe_load(match.group(1))
    if not isinstance(frontmatter, dict):
        raise CandidateSkip(f"Invalid YAML frontmatter: {path}")
    name = str(frontmatter.get("name", "")).strip()
    description = str(frontmatter.get("description", "")).strip()
    body = text[match.end() :].strip()
    if not name:
        raise CandidateSkip(f"Missing skill name: {path}")
    if not description:
        raise CandidateSkip(f"Missing skill description: {path}")
    if not body:
        raise CandidateSkip(f"Missing skill body: {path}")
    return {"name": name, "description": description, "body": body}


def _normalize_id_part(value: str) -> str:
    normalized = _SAFE_ID_RE.sub("-", value.lower()).strip("-")
    return re.sub(r"-+", "-", normalized)


def normalize_candidate_id(source_id: str, skill_path: Path) -> str:
    """Build a deterministic candidate id from source id and skill parent path."""
    parent = skill_path.parent
    parts = list(parent.parts)
    if len(parts) >= 2 and parts[0] == "skills" and parts[1].startswith("."):
        parts = parts[2:]
    elif parts[:1] == ["skills"]:
        parts = parts[1:]
    path_part = _normalize_id_part("-".join(parts))
    return f"{_normalize_id_part(source_id)}__{path_part}"


def _license_kind(text: str) -> str | None:
    lowered = text.lower()
    if "apache license" in lowered or "apache-2.0" in lowered:
        return "Apache-2.0"
    if "mit license" in lowered or "permission is hereby granted" in lowered:
        return "MIT"
    if "all rights reserved" in lowered or "source-available" in lowered:
        return "source-available"
    if "figma developer terms" in lowered:
        return "custom"
    return None


def _find_license_file(repo_root: Path, skill_path: Path, policy: str) -> Path | None:
    candidates: list[Path] = []
    if policy == "per_skill":
        candidates.extend(
            [
                skill_path.parent / "LICENSE.txt",
                skill_path.parent / "LICENSE",
                skill_path.parent / "license.txt",
            ]
        )
    candidates.extend(
        [
            repo_root / "LICENSE",
            repo_root / "LICENSE.txt",
            repo_root / "license.txt",
        ]
    )
    return next((path for path in candidates if path.is_file()), None)


def classify_license(
    repo_root: Path,
    skill_path: Path,
    source: dict[str, Any],
) -> dict[str, str]:
    """Classify license status without granting trust to unclear content."""
    policy = str(source.get("default_license_policy", "repo"))
    license_file = _find_license_file(repo_root, skill_path, policy)
    if license_file is None:
        return {"status": "review", "kind": "unknown", "file": ""}
    text = license_file.read_text(encoding="utf-8", errors="replace")
    kind = _license_kind(text) or "custom"
    if kind in {"MIT", "Apache-2.0"}:
        status = "accepted"
    elif kind == "source-available":
        status = "review"
    else:
        status = "review"
    return {
        "status": status,
        "kind": kind,
        "file": _as_posix(license_file.relative_to(repo_root)),
    }


def assess_risk(repo_root: Path, skill_path: Path, text: str) -> dict[str, Any]:
    """Classify candidate risk from static text and adjacent directories only."""
    flags: list[str] = []
    skill_dir = skill_path.parent
    for dirname, flag in (
        ("scripts", "has_scripts_directory"),
        ("references", "has_references_directory"),
        ("assets", "has_assets_directory"),
    ):
        if (skill_dir / dirname).is_dir():
            flags.append(flag)
    if _NETWORK_INSTALL_RE.search(text):
        flags.append("mentions_network_install")
    if _DESTRUCTIVE_RE.search(text):
        flags.append("mentions_destructive_command")
    if _SECRET_RE.search(text):
        flags.append("mentions_secret_or_token")
    if _EXTERNAL_API_RE.search(text):
        flags.append("mentions_external_api")
    lowered_path = _as_posix(skill_path).lower()
    if "/personal/" in lowered_path or "obsidian" in text.lower():
        flags.append("personal_workflow")

    high_flags = {"mentions_destructive_command"}
    medium_flags = {
        "has_scripts_directory",
        "mentions_network_install",
        "mentions_secret_or_token",
        "mentions_external_api",
    }
    if any(flag in high_flags for flag in flags):
        level = "high"
    elif any(flag in medium_flags for flag in flags):
        level = "medium"
    else:
        level = "low"
    return {"level": level, "flags": sorted(dict.fromkeys(flags))}


def _infer_facets(skill_path: Path, parsed: dict[str, str]) -> list[str]:
    text = " ".join([_as_posix(skill_path), parsed["name"], parsed["description"]]).lower()
    mappings = {
        "testing": ["test", "pytest", "playwright", "jest", "qa"],
        "security": ["security", "threat", "secret", "owasp"],
        "frontend": ["react", "frontend", "ui", "webapp"],
        "mcp": ["mcp"],
        "python": ["python", "pytest"],
        "typescript": ["typescript", "javascript", "node"],
        "documentation": ["docs", "documentation", "readme", "writing"],
    }
    facets = []
    for facet, keywords in mappings.items():
        if any(keyword in text for keyword in keywords):
            facets.append(facet)
    return sorted(dict.fromkeys(facets))


def _manifest_for_skill(
    *,
    repo_root: Path,
    source: dict[str, Any],
    skill_path: Path,
    relpath: Path,
    parsed: dict[str, str],
    license_info: dict[str, str],
    risk: dict[str, Any],
    commit: str,
    full_text: str,
) -> dict[str, Any]:
    candidate_id = normalize_candidate_id(str(source["id"]), relpath)
    status = "candidate" if license_info["status"] == "accepted" else "review"
    return {
        "schema_version": CANDIDATE_SCHEMA,
        "id": candidate_id,
        "name": parsed["name"],
        "description": parsed["description"],
        "status": status,
        "source_tier": str(source.get("source_tier", "community")),
        "source": {
            "source_id": str(source["id"]),
            "repo": str(source["repo"]),
            "url": str(source["url"]),
            "ref": str(source.get("ref", "")),
            "commit": commit,
            "path": _as_posix(relpath),
        },
        "license": license_info,
        "risk": risk,
        "facets": _infer_facets(relpath, parsed),
        "languages": [],
        "platforms": [],
        "aliases": [_normalize_id_part(parsed["name"])],
        "content": {
            "kind": "skill_markdown",
            "sha256": hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
            "char_count": len(full_text),
            "text": parsed["body"],
        },
    }


def _write_yaml_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    temp_path.replace(path)


def scan_local_source(
    repo_root: Path,
    source: dict[str, Any],
    output_dir: Path,
    *,
    commit: str,
) -> dict[str, Any]:
    """Scan one local checkout and write candidate manifests."""
    source_id = str(source["id"])
    summary = {"source_id": source_id, "written": 0, "skipped": 0, "review": 0}
    source_output = output_dir / source_id
    source_output.mkdir(parents=True, exist_ok=True)
    for stale in source_output.glob("*.yaml"):
        stale.unlink()

    if source.get("import_policy") == "skip":
        return summary

    allowed_paths = [str(value) for value in source.get("allowed_paths", [])]
    skipped_paths = [str(value) for value in source.get("skipped_paths", [])]
    max_skill_chars = int(source.get("max_skill_chars", 60000))

    for skill_path in sorted(repo_root.rglob("SKILL.md")):
        relpath = skill_path.relative_to(repo_root)
        if allowed_paths and not _path_is_under(relpath, allowed_paths):
            summary["skipped"] += 1
            continue
        if skipped_paths and _path_is_under(relpath, skipped_paths):
            summary["skipped"] += 1
            continue
        full_text = skill_path.read_text(encoding="utf-8", errors="replace")
        if len(full_text) > max_skill_chars:
            summary["skipped"] += 1
            continue
        try:
            parsed = parse_skill_markdown(relpath, full_text)
            license_info = classify_license(repo_root, skill_path, source)
            risk = assess_risk(repo_root, skill_path, full_text)
        except CandidateSkip:
            summary["skipped"] += 1
            continue
        if license_info["status"] == "rejected" or risk["level"] == "high":
            summary["skipped"] += 1
            continue
        manifest = _manifest_for_skill(
            repo_root=repo_root,
            source=source,
            skill_path=skill_path,
            relpath=relpath,
            parsed=parsed,
            license_info=license_info,
            risk=risk,
            commit=commit,
            full_text=full_text,
        )
        if manifest["status"] == "review":
            summary["review"] += 1
        manifest_path = source_output / f"{manifest['id']}.yaml"
        _write_yaml_atomic(manifest_path, manifest)
        summary["written"] += 1
    return summary


def load_sources(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != SOURCES_SCHEMA:
        raise ValueError(f"Unsupported skill sources schema: {path}")
    sources = data.get("sources")
    if not isinstance(sources, list):
        raise ValueError("sources.yaml must contain a sources list.")
    required = {"id", "repo", "url", "ref", "source_tier", "allowed_paths", "import_policy"}
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("Each source must be a mapping.")
        missing = sorted(required.difference(source))
        if missing:
            raise ValueError(f"Source {source.get('id', '<unknown>')} missing: {missing}")
    return sources


def _git(args: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def _clone_source(source: dict[str, Any], parent: Path) -> tuple[Path, str]:
    checkout = parent / str(source["id"])
    _git(
        [
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--branch",
            str(source["ref"]),
            str(source["url"]),
            str(checkout),
        ]
    )
    commit = _git(["rev-parse", "HEAD"], cwd=checkout)
    return checkout, commit


def scan_sources(
    sources_path: Path,
    output_dir: Path,
    *,
    continue_on_error: bool = False,
) -> dict[str, Any]:
    sources = load_sources(sources_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="skill-source-scan-") as tmp:
        tmp_path = Path(tmp)
        for source in sources:
            if source.get("import_policy") == "skip":
                summaries.append(
                    {
                        "source_id": source["id"],
                        "written": 0,
                        "skipped": 0,
                        "review": 0,
                        "status": "skipped_by_policy",
                    }
                )
                continue
            try:
                checkout, commit = _clone_source(source, tmp_path)
                summary = scan_local_source(checkout, source, output_dir, commit=commit)
                summary["status"] = "success"
                summaries.append(summary)
            except Exception as exc:
                if not continue_on_error:
                    raise
                summaries.append(
                    {
                        "source_id": source.get("id", "unknown"),
                        "written": 0,
                        "skipped": 0,
                        "review": 0,
                        "status": "error",
                        "error": str(exc),
                    }
                )
    return {
        "sources": summaries,
        "written": sum(int(item.get("written", 0)) for item in summaries),
        "review": sum(int(item.get("review", 0)) for item in summaries),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan skill sources into candidates.")
    parser.add_argument(
        "--sources",
        type=Path,
        default=SKILL_REGISTRY_DIR / "sources.yaml",
        help="Path to skill source configuration.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=SKILL_REGISTRY_DIR / "candidates",
        help="Candidate manifest output directory.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue scanning other sources when one clone or scan fails.",
    )
    args = parser.parse_args()
    result = scan_sources(
        args.sources,
        args.output_dir,
        continue_on_error=args.continue_on_error,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
