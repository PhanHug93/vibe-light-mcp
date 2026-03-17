# Python — Testing Deep Dive (pytest)

## Project Setup

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --strict-markers --strict-config -x"
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks integration tests",
    "e2e: marks end-to-end tests",
]
```

## Fixtures

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

# --- Scope Levels ---
@pytest.fixture  # function scope (default) — mỗi test tạo mới
def user():
    return User(name="test", email="test@example.com")

@pytest.fixture(scope="module")  # shared across module
def db_connection():
    conn = create_connection()
    yield conn
    conn.close()

@pytest.fixture(scope="session")  # shared across toàn bộ test session
def app():
    return create_app(testing=True)

# --- Async Fixtures ---
@pytest.fixture
async def async_client(app):
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

# --- Factory Pattern ---
@pytest.fixture
def make_user():
    def _make(name: str = "test", **kwargs) -> User:
        return User(name=name, **kwargs)
    return _make

# --- Conftest.py hierarchy ---
# tests/conftest.py         → shared fixtures cho toàn project
# tests/unit/conftest.py    → fixtures riêng cho unit tests
# tests/integration/conftest.py → fixtures riêng cho integration
```

## Parametrize

```python
@pytest.mark.parametrize("input_val,expected", [
    ("hello", "HELLO"),
    ("world", "WORLD"),
    ("", ""),
])
def test_uppercase(input_val, expected):
    assert input_val.upper() == expected

# Multiple parameters
@pytest.mark.parametrize("x", [1, 2, 3])
@pytest.mark.parametrize("y", [10, 20])
def test_multiply(x, y):
    assert x * y > 0  # 6 test cases (cartesian product)

# IDs for readable output
@pytest.mark.parametrize("status,expected", [
    pytest.param(200, True, id="success"),
    pytest.param(404, False, id="not_found"),
    pytest.param(500, False, id="server_error"),
])
def test_is_success(status, expected):
    assert is_success(status) == expected
```

## Mocking

```python
from unittest.mock import patch, MagicMock, AsyncMock

# Patch object method
def test_send_email(mocker):  # pytest-mock
    mock_send = mocker.patch("mypackage.services.email.send")
    notify_user(user)
    mock_send.assert_called_once_with(user.email, subject=mocker.ANY)

# Async mock
async def test_fetch_data(mocker):
    mock_client = AsyncMock()
    mock_client.get.return_value = Response(200, json={"id": 1})
    service = DataService(client=mock_client)
    result = await service.fetch(1)
    assert result.id == 1

# Context manager mock
def test_file_read(mocker):
    mocker.patch("builtins.open", mocker.mock_open(read_data="content"))
    assert read_config() == "content"

# Side effects
def test_retry_logic(mocker):
    mock_call = mocker.patch("mypackage.api.fetch")
    mock_call.side    _effect = [ConnectionError(), ConnectionError(), {"data": "ok"}]
    result = fetch_with_retry(max_retries=3)
    assert result == {"data": "ok"}
    assert mock_call.call_count == 3
```

## Exception Testing

```python
def test_raises_not_found():
    with pytest.raises(NotFoundError, match="User not found"):
        service.get_user("nonexistent")

def test_raises_validation():
    with pytest.raises(ValidationError) as exc_info:
        User(email="invalid")
    assert "email" in str(exc_info.value)
```

## Async Testing

```python
# pytest-asyncio required
import pytest

@pytest.mark.asyncio
async def test_async_operation():
    result = await async_service.process()
    assert result.status == "completed"

# Fixture + async
@pytest.fixture
async def populated_db(db_session):
    await db_session.execute(insert(User).values(name="test"))
    await db_session.commit()
    yield db_session
    await db_session.execute(delete(User))
    await db_session.commit()
```

## Coverage Configuration

```toml
# pyproject.toml
[tool.coverage.run]
source = ["src/mypackage"]
omit = ["*/tests/*", "*/migrations/*"]
branch = true

[tool.coverage.report]
fail_under = 80
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "if __name__ == .__main__.",
]
```

## Test Organization Anti-patterns ❌

- Test files quá lớn (>300 lines) → chia theo behavior
- Assert không có message → `assert result == expected, f"Got {result}"`
- Test phụ thuộc lẫn nhau (order-dependent)
- Mock quá nhiều → test không reflect reality
- Không clean up fixtures → `yield` + cleanup code
- Test database thật trong unit tests → dùng mock/fake
