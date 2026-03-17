# Python — Rules

## Project Structure

- **`pyproject.toml`-first** (PEP 621): single source of truth cho metadata, deps, tool config
- **`src/` layout** bắt buộc cho packages: `src/mypackage/`, tránh flat layout implicit import issues
- Cấu trúc chuẩn:
  ```
  project/
  ├── pyproject.toml
  ├── src/
  │   └── mypackage/
  │       ├── __init__.py
  │       ├── core/          # Business logic, domain models
  │       ├── api/           # FastAPI routers, Flask blueprints
  │       ├── services/      # Application services, use cases
  │       ├── repositories/  # Data access layer
  │       └── utils/         # Shared utilities
  ├── tests/
  │   ├── conftest.py
  │   ├── unit/
  │   └── integration/
  └── scripts/               # One-off scripts, CLI tools
  ```
- **Không** dùng `setup.py` (legacy), `setup.cfg` (deprecated)
- Module exports qua `__init__.py` — explicit, không dùng `__all__` quá lớn

## Type Safety (Bắt buộc)

- Type hints cho **mọi** function signature (PEP 484/585/604):
  ```python
  from __future__ import annotations

  def process_items(items: list[str], limit: int = 10) -> dict[str, int]:
      ...
  ```
- `from __future__ import annotations` ở đầu mỗi file (PEP 563)
- Union syntax mới: `str | None` thay vì `Optional[str]`
- Generic syntax mới: `list[int]` thay vì `List[int]`
- `mypy --strict` hoặc `pyright` cho static type checking
- Typing patterns nâng cao:
  ```python
  from typing import TypeVar, Protocol, TypeAlias

  T = TypeVar("T")
  JSON: TypeAlias = dict[str, "JSON"] | list["JSON"] | str | int | float | bool | None

  class Repository(Protocol):
      async def get(self, id: str) -> Model | None: ...
      async def save(self, entity: Model) -> None: ...
  ```

## Error Handling

- Custom exception hierarchy kế thừa từ base domain error:
  ```python
  class AppError(Exception):
      """Base cho tất cả application errors."""

  class NotFoundError(AppError):
      def __init__(self, entity: str, id: str) -> None:
          super().__init__(f"{entity} not found: {id}")

  class ValidationError(AppError): ...
  class AuthenticationError(AppError): ...
  ```
- **Cấm**: bare `except:`, `except Exception: pass`
- Logging exception info: `logger.exception("msg")` — **không** `logger.error(str(e))`
- `try/except` scope nhỏ nhất có thể — bao bọc chỉ code có thể raise
- Resource cleanup: `contextlib.asynccontextmanager`, `try/finally`, `with` statement

## Async / Concurrency

- `asyncio` là primary async runtime — **không** mix với threading trừ khi cần thiết
- `async def` cho I/O-bound: HTTP calls, database, file I/O
- Patterns:
  ```python
  # TaskGroup (Python 3.11+) — structured concurrency
  async with asyncio.TaskGroup() as tg:
      task1 = tg.create_task(fetch_users())
      task2 = tg.create_task(fetch_orders())
  users, orders = task1.result(), task2.result()

  # Semaphore — rate limiting
  sem = asyncio.Semaphore(10)
  async def limited_fetch(url: str) -> Response:
      async with sem:
          return await client.get(url)

  # Timeout
  async with asyncio.timeout(30):
      result = await long_operation()
  ```
- **Cấm**: `loop.run_until_complete()` trong async context, `asyncio.get_event_loop()` (deprecated)
- Blocking I/O trong async: chạy qua `asyncio.to_thread()` hoặc `loop.run_in_executor()`
- Cancellation handling: luôn `try/finally` cleanup, check `asyncio.current_task().cancelled()`

## Data Modeling

- **Pydantic v2** cho external data (API request/response, config, serialization):
  ```python
  from pydantic import BaseModel, Field, field_validator

  class UserCreate(BaseModel):
      model_config = ConfigDict(strict=True, frozen=True)

      name: str = Field(min_length=1, max_length=100)
      email: str = Field(pattern=r"^[\w.-]+@[\w.-]+\.\w+$")
      age: int = Field(ge=0, le=150)

      @field_validator("name")
      @classmethod
      def strip_name(cls, v: str) -> str:
          return v.strip()
  ```
- **`dataclasses`** cho internal domain models (không cần serialization):
  ```python
  from dataclasses import dataclass, field

  @dataclass(frozen=True, slots=True)
  class Money:
      amount: Decimal
      currency: str = "USD"
  ```
- **Không** dùng plain dict cho structured data — luôn dùng model
- `model_config = ConfigDict(frozen=True)` cho immutable models
- DTO mapping tách biệt: API DTO ↔ Domain Model ↔ DB Entity

## Dependency Injection

- Constructor injection — **không** dùng global state, singleton pattern:
  ```python
  class UserService:
      def __init__(self, repo: UserRepository, cache: CacheClient) -> None:
          self._repo = repo
          self._cache = cache
  ```
- `typing.Protocol` cho interface definitions — loose coupling
- Configuration qua `pydantic_settings.BaseSettings`:
  ```python
  from pydantic_settings import BaseSettings

  class Settings(BaseSettings):
      model_config = SettingsConfigDict(env_file=".env")
      database_url: str
      redis_url: str = "redis://localhost:6379"
      debug: bool = False
  ```

## Security

- `.env` + `python-dotenv` / `pydantic_settings` — **never** hardcode secrets
- `secrets` module cho token generation — **không** dùng `random`
- Input validation tại boundary (Pydantic models, `Field` constraints)
- SQL: parameterized queries exclusively — **cấm** string interpolation
- Dependencies: `pip-audit` hoặc `safety` cho vulnerability scanning
- Passwords: `bcrypt` hoặc `argon2-cffi` — **không** MD5/SHA cho passwords

## Performance

- **Profiling trước khi optimize** — `py-spy`, `cProfile`, `line_profiler`
- Generators / iterators cho large datasets:
  ```python
  # ✅ Memory-efficient
  def read_large_file(path: Path) -> Iterator[str]:
      with open(path) as f:
          yield from f

  # ❌ Load toàn bộ vào RAM
  lines = open(path).readlines()
  ```
- `__slots__` cho data-heavy classes
- Lazy imports cho heavy modules (numpy, pandas, torch)
- Connection pooling: `httpx.AsyncClient()`, `asyncpg.create_pool()`
- Caching: `functools.lru_cache`, `functools.cache` (3.9+), `@cached_property`

## Code Style & Linting

- **`ruff`** — single tool cho both linting + formatting:
  ```toml
  # pyproject.toml
  [tool.ruff]
  target-version = "py312"
  line-length = 88

  [tool.ruff.lint]
  select = ["E", "W", "F", "I", "N", "UP", "B", "A", "S", "T20", "PT", "RUF"]
  ```
- Line length: 88 (Black-compatible)
- Import order: stdlib → third-party → local (enforced by `ruff` `I` rules)
- Docstrings: Google style cho public APIs
- Naming: `snake_case` functions/vars, `PascalCase` classes, `UPPER_SNAKE` constants

## Packaging & Dependencies

- `uv` (preferred) hoặc `pip-tools` cho dependency management
- Pin dependencies: `uv lock` / `pip-compile` → lockfile
- Virtual environment bắt buộc — **không** install vào system Python
- Separate dependency groups:
  ```toml
  [project]
  dependencies = ["fastapi>=0.100", "pydantic>=2.0"]

  [project.optional-dependencies]
  dev = ["pytest", "ruff", "mypy", "pre-commit"]
  ```

## Logging

- `logging` module chuẩn — **không** dùng `print()` cho production:
  ```python
  import logging
  logger = logging.getLogger(__name__)
  logger.info("Processing user %s", user_id)  # lazy formatting
  ```
- Structured logging: `structlog` cho production (JSON output)
- **Không** dùng f-string trong log calls — dùng `%s` formatting (lazy evaluation)
- Log levels: DEBUG (dev), INFO (flow), WARNING (recoverable), ERROR (failure), CRITICAL (fatal)

## Anti-patterns ❌

- Mutable default arguments: `def f(items=[])` → `def f(items: list | None = None)`
- Bare `except:` hoặc `except Exception: pass`
- `from module import *` — pollutes namespace
- `global` keyword — use dependency injection
- `eval()` / `exec()` — security risk, never with user input
- `type()` checks → dùng `isinstance()` hoặc structural typing
- Nested try/except quá sâu (>2 levels)
- Business logic trong `__init__.py`
- Circular imports → restructure hoặc dùng `TYPE_CHECKING`
- `os.system()` / `subprocess.call()` → dùng `subprocess.run()` với `check=True`

## Logic Correctness

- Comparisons: `is None` / `is not None` — **không** `== None`
- Boolean checks: `if items:` thay vì `if len(items) > 0`
- Walrus operator khi phù hợp: `if (m := re.match(pattern, text)):`
- `match/case` (Python 3.10+) cho complex conditionals
- Enum cho fixed choices — **không** magic strings
