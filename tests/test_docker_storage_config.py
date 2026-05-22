"""Tests for Docker storage layout and bundled local skill registry."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_bundles_skill_registry_and_defaults() -> None:
    dockerfile = (ROOT / "deploy/docker/Dockerfile").read_text(encoding="utf-8")

    assert "COPY --chown=mcpuser:mcpuser skill_registry/ ./skill_registry/" in dockerfile
    assert (
        "COPY --chown=mcpuser:mcpuser skill_registry/ /opt/mcp-defaults/skill_registry/"
        in dockerfile
    )
    assert (
        "MCP_SKILL_STORE_PATH=/app/skill_registry/index/skill_store.sqlite"
        in dockerfile
    )
    assert "MCP_CHROMA_HOST=memorydb" in dockerfile
    assert 'VOLUME ["/data", "/app/tech_stacks", "/app/skill_registry"]' in dockerfile
    assert "python scripts/build_skill_store.py" in dockerfile
    assert "--registry-dir /app/skill_registry" in dockerfile
    assert "--output /app/skill_registry/index/skill_store.sqlite" in dockerfile


def test_compose_uses_docker_named_volumes_for_runtime_storage() -> None:
    compose_path = ROOT / "deploy/compose/docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    assert "memorydb" in compose["services"]
    assert "chromadb" not in compose["services"]
    assert compose["services"]["memorydb"]["container_name"] == "mcp-memorydb"
    assert "memorydb_data:/chroma/chroma" in compose["services"]["memorydb"]["volumes"]
    assert "memorydb" in compose["services"]["mcp_server"]["depends_on"]
    assert "MCP_CHROMA_HOST=memorydb" in compose["services"]["mcp_server"]["environment"]

    volumes = compose["services"]["mcp_server"]["volumes"]
    assert "mcp_data:/data" in volumes
    assert "tech_stacks_data:/app/tech_stacks" in volumes
    assert "skill_registry_data:/app/skill_registry" in volumes
    assert not any("../../tech_stacks" in volume for volume in volumes)

    declared_volumes = compose["volumes"]
    assert "memorydb_data" in declared_volumes
    assert "chroma_data" not in declared_volumes
    assert "mcp_data" in declared_volumes
    assert "tech_stacks_data" in declared_volumes
    assert "skill_registry_data" in declared_volumes


def test_entrypoint_seeds_empty_docker_volumes_from_image_defaults() -> None:
    entrypoint = (ROOT / "deploy/docker/entrypoint.sh").read_text(encoding="utf-8")

    assert "/opt/mcp-defaults/tech_stacks" in entrypoint
    assert "/opt/mcp-defaults/skill_registry" in entrypoint
    assert 'seed_if_empty "/opt/mcp-defaults/skill_registry" "/app/skill_registry"' in entrypoint
    assert 'seed_if_empty "/opt/mcp-defaults/tech_stacks" "/app/tech_stacks"' in entrypoint


def test_entrypoint_builds_missing_skill_store_inside_volume() -> None:
    entrypoint = (ROOT / "deploy/docker/entrypoint.sh").read_text(encoding="utf-8")

    assert 'SKILL_REGISTRY_DIR="${MCP_SKILL_REGISTRY_DIR:-/app/skill_registry}"' in entrypoint
    assert (
        'SKILL_STORE_PATH="${MCP_SKILL_STORE_PATH:-$SKILL_REGISTRY_DIR/index/skill_store.sqlite}"'
        in entrypoint
    )
    assert 'python scripts/build_skill_store.py \\' in entrypoint
    assert '--registry-dir "$SKILL_REGISTRY_DIR" \\' in entrypoint
    assert '--output "$SKILL_STORE_PATH"' in entrypoint


def test_dockerignore_excludes_generated_sqlite_artifacts() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "*.sqlite" in dockerignore


def test_runtime_config_honors_docker_storage_environment_paths() -> None:
    config = (ROOT / "src/config.py").read_text(encoding="utf-8")

    assert 'os.getenv("MCP_TECH_STACKS_DIR"' in config
    assert 'os.getenv("MCP_SKILL_REGISTRY_DIR"' in config
    assert '"MCP_SKILL_STORE_PATH"' in config
    assert 'os.getenv("MCP_USAGE_LOG_DIR"' in config
