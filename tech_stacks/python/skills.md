# Python — Skills (Terminal Commands)

## Environment Setup

```bash
# Tạo virtual environment (uv — preferred)
uv venv
source .venv/bin/activate

# Tạo virtual environment (stdlib)
python3 -m venv .venv
source .venv/bin/activate

# Deactivate
deactivate

# Python version check
python3 --version
which python3
```

## Dependency Management

```bash
# uv (modern, fast)
uv pip install -r requirements.txt
uv pip install fastapi uvicorn
uv lock
uv sync

# pip-tools (lockfile workflow)
pip-compile pyproject.toml -o requirements.txt
pip-compile --extra dev -o requirements-dev.txt
pip-sync requirements.txt requirements-dev.txt

# pip (basic)
pip install -e ".[dev]"
pip install -r requirements.txt
pip freeze > requirements.txt
pip list --outdated
```

## Testing (pytest)

```bash
# Run all tests
pytest

# Verbose output
pytest -v

# Run specific file / class / test
pytest tests/test_users.py
pytest tests/test_users.py::TestUserService
pytest tests/test_users.py::TestUserService::test_create

# Run by marker
pytest -m "not slow"
pytest -m integration

# Coverage
pytest --cov=src/mypackage --cov-report=html --cov-report=term-missing
open htmlcov/index.html

# Parallel execution
pytest -n auto       # requires pytest-xdist

# Failed tests only (re-run)
pytest --lf          # last-failed
pytest --ff          # failed-first

# Watch mode
ptw                  # requires pytest-watch

# Show print output
pytest -s

# Stop on first failure
pytest -x
```

## Linting & Formatting

```bash
# Ruff (all-in-one linter + formatter)
ruff check .                  # lint
ruff check . --fix            # auto-fix
ruff format .                 # format (Black-compatible)
ruff format --check .         # format check (CI)

# Type checking
mypy src/                     # strict type check
pyright src/                  # alternative

# Security audit
pip-audit                     # check installed packages
bandit -r src/                # security linter

# Pre-commit (run all hooks)
pre-commit run --all-files
pre-commit install            # install git hooks
```

## Server / API Development

```bash
# FastAPI development server
uvicorn src.mypackage.main:app --reload --host 0.0.0.0 --port 8000

# Production (gunicorn + uvicorn workers)
gunicorn src.mypackage.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Flask development
flask --app src/mypackage/main run --debug --port 5000

# Django
python manage.py runserver
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

## Database

```bash
# Alembic migrations (SQLAlchemy)
alembic init migrations
alembic revision --autogenerate -m "add users table"
alembic upgrade head
alembic downgrade -1
alembic history

# Django migrations
python manage.py makemigrations
python manage.py migrate
python manage.py showmigrations
```

## Debugging & Profiling

```bash
# Interactive debugger
python3 -m pdb script.py
# In code: import pdb; pdb.set_trace()
# Or: breakpoint()  (Python 3.7+)

# Profiling
python3 -m cProfile -s cumtime script.py
py-spy record -o profile.svg -- python3 script.py
py-spy top -- python3 script.py

# Memory profiling
python3 -m memory_profiler script.py
# Or: tracemalloc (stdlib)

# Line profiling
kernprof -l -v script.py
```

## Packaging & Distribution

```bash
# Build package
python3 -m build

# Upload to PyPI
twine upload dist/*

# Upload to test PyPI
twine upload --repository testpypi dist/*

# Install local package in editable mode
pip install -e .
pip install -e ".[dev]"
```

## Docker

```bash
# Build
docker build -t myapp .
docker build --target production -t myapp:prod .

# Run
docker run -p 8000:8000 --env-file .env myapp
docker compose up -d
docker compose logs -f app

# Multi-stage Dockerfile pattern
# Stage 1: builder (install deps)
# Stage 2: runtime (copy only needed files)
```

## Script Utilities

```bash
# Run module as script
python3 -m mypackage.cli

# One-liner HTTP server
python3 -m http.server 8080

# JSON pretty print
echo '{"a":1}' | python3 -m json.tool

# Generate secret key
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Check import paths
python3 -c "import mypackage; print(mypackage.__file__)"
```

## Debug Workflow

```bash
# 1. Reproduce issue
# 2. Add breakpoint() at suspect location
# 3. Run with debugger
python3 -m pdb script.py
# 4. Inspect variables: p var_name, pp dict_var
# 5. Step through: n (next), s (step into), c (continue)
# 6. Write regression test
pytest tests/test_regression.py -v
```

## Optimization Workflow

```bash
# 1. Profile first — identify bottleneck
py-spy record -o profile.svg -- python3 script.py

# 2. Measure baseline
python3 -m timeit -s "setup_code" "code_to_measure"

# 3. Apply targeted fix

# 4. Re-measure
pytest --benchmark-only  # requires pytest-benchmark

# 5. If < 5% improvement → revert
```
