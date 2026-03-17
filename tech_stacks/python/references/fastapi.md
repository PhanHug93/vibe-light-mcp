# Python — FastAPI Deep Dive

## Project Architecture

```
src/mypackage/
├── main.py              # FastAPI app factory, lifespan
├── config.py            # Settings (pydantic_settings)
├── dependencies.py      # Shared DI dependencies
├── api/
│   ├── __init__.py
│   ├── v1/
│   │   ├── __init__.py
│   │   ├── router.py    # Include all v1 routers
│   │   ├── users.py     # User endpoints
│   │   └── orders.py    # Order endpoints
│   └── middleware.py
├── models/              # Pydantic schemas (request/response)
│   ├── users.py
│   └── common.py
├── services/            # Business logic
│   └── user_service.py
├── repositories/        # Data access
│   └── user_repo.py
└── db/
    ├── session.py       # DB session management
    └── models.py        # SQLAlchemy models
```

## App Factory & Lifespan

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: init connections, pools, caches
    db_pool = await create_db_pool()
    redis = await create_redis_client()
    app.state.db_pool = db_pool
    app.state.redis = redis

    yield  # App runs here

    # Shutdown: cleanup
    await db_pool.close()
    await redis.close()

def create_app() -> FastAPI:
    app = FastAPI(
        title="My API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(v1_router, prefix="/api/v1")
    return app

app = create_app()
```

## Dependency Injection

```python
from fastapi import Depends, Request
from typing import Annotated

# Database session dependency
async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.app.state.session_factory() as session:
        yield session

# Service dependency (composed)
async def get_user_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserService:
    repo = UserRepository(db)
    return UserService(repo)

# Usage in endpoint
@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    user = await service.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.model_validate(user)
```

## Pydantic Models (Request / Response)

```python
from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import datetime

# Request model — validation tại boundary
class UserCreate(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=r"^[\w.-]+@[\w.-]+\.\w+$")
    role: UserRole = UserRole.USER

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return v.strip().title()

# Response model — serialization
class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str
    created_at: datetime

# Pagination response
class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    has_next: bool
```

## Error Handling

```python
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

# Custom exception handler
class AppError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "type": type(exc).__name__},
    )

# Validation error customization
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation failed",
            "details": exc.errors(),
        },
    )
```

## Middleware

```python
from fastapi.middleware.cors import CORSMiddleware
import time

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom middleware — request timing
@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    response.headers["X-Process-Time"] = f"{elapsed:.4f}"
    return response
```

## Authentication

```python
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    token = credentials.credentials
    payload = decode_jwt(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.get(User, payload["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# Protected endpoint
@router.get("/me")
async def get_me(
    user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    return UserResponse.model_validate(user)
```

## Testing FastAPI

```python
import pytest
from httpx import AsyncClient, ASGITransport

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_create_user(client: AsyncClient):
    response = await client.post("/api/v1/users", json={
        "name": "John",
        "email": "john@example.com",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "John"

@pytest.mark.asyncio
async def test_get_user_not_found(client: AsyncClient):
    response = await client.get("/api/v1/users/nonexistent")
    assert response.status_code == 404
```

## Anti-patterns ❌

- Business logic trong endpoint functions → dùng service layer
- `@app.on_event("startup")` (deprecated) → dùng `lifespan`
- Raw SQL trong endpoints → dùng repository pattern
- Không type hint response → luôn dùng `-> ResponseModel`
- Global mutable state → dùng `app.state` hoặc dependency injection
- Synchronous blocking calls trong async endpoints
- Không validation input → Pydantic models tại boundary
