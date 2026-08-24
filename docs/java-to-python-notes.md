# Python backend, for a Java developer

Your reference while working through `api_server.py`.

---

## 1. The mental map

| Java / Spring Boot | Python / FastAPI |
|---|---|
| Maven / Gradle | `pip` + `requirements.txt` (or `uv`) |
| `pom.xml` dependencies | `requirements.txt` / `pyproject.toml` |
| JVM + classpath | `venv` folder (one per project) |
| Embedded Tomcat | `uvicorn` |
| `@SpringBootApplication` | `app = FastAPI()` |
| `@RestController` | plain module + `@app.get/post` |
| `@RequestMapping("/api/v1")` | `APIRouter(prefix="/api/v1")` |
| `@GetMapping("/x")` | `@app.get("/x")` |
| `@PathVariable int id` | `def f(id: int)` + `{id}` in the path |
| `@RequestParam String q` | `q: str = Query(None)` |
| `@RequestBody AskRequest` | `body: AskRequest` (a Pydantic model) |
| `@Valid` + Bean Validation | Pydantic does it automatically -> 422 |
| DTO + Lombok + Jackson | one Pydantic `BaseModel` |
| `@Service` / `@Component` | a plain class or function |
| `@Autowired` | `Depends(get_thing)` |
| `@ControllerAdvice` | `@app.exception_handler(SomeError)` |
| `Filter` / `HandlerInterceptor` | `@app.middleware("http")` |
| `@PostConstruct` / `@PreDestroy` | `lifespan` (before/after `yield`) |
| `ResponseStatusException` | `raise HTTPException(404, "...")` |
| springdoc / Swagger config | free at `/docs` and `/redoc` |
| JUnit + MockMvc | `pytest` + `TestClient` |
| `application.properties` | `.env` + `os.getenv` (python-dotenv) |
| Checked exceptions | none - Python has only unchecked |
| `interface` + `implements` | duck typing (or `typing.Protocol`) |
| `Optional<T>` | `T | None` |
| `List<T>` / `Map<K,V>` | `list[T]` / `dict[K, V]` |

**The single biggest difference:** in Spring, annotations carry the metadata.
In FastAPI, **type hints** carry it. `def ask(body: AskRequest, faq_id: int)` is
enough for FastAPI to parse the body, validate it, coerce the path param, return
422 on bad input, and generate OpenAPI docs. Type hints are not optional
decoration here - they are the framework's input.

---

## 2. Daily commands

```powershell
cd D:\WORK\faq-chatbot
.\venv\Scripts\Activate.ps1              # like setting JAVA_HOME per shell
python -m uvicorn api_server:app --reload --port 8000
```

`--reload` = Spring DevTools. Edit a file, server restarts.
Then open <http://127.0.0.1:8000/docs> and click "Try it out".

Add a dependency:

```powershell
pip install some-package
pip freeze > requirements.txt
```

Leave the venv: `deactivate`.

---

## 3. Python syntax you will hit immediately

```python
# no braces - indentation IS the block. No semicolons.
def greet(name: str, times: int = 1) -> str:      # default arg, return type
    return ("hi " + name + "\n") * times          # str * int repeats it

# f-string == String.format, but inline
msg = f"{name} asked {times} times"

# list comprehension == stream().filter().map().toList()
names = [u.name for u in users if u.active]

# dict == Map, literal syntax
cfg = {"port": 8000, "debug": True}
cfg.get("host", "127.0.0.1")     # like map.getOrDefault

# tuple == immutable fixed-size record, unpacks like destructuring
q, a = ("What?", "This.")

# truthiness: empty list/str/dict/0/None are all falsy
if not items: ...

# there is no `new`, no `public/private` (a leading _ means "internal, please")
# `self` is an explicit first parameter, not an implicit `this`
```

Gotchas that bite Java devs:

- `==` compares **values** (like `.equals`). `is` compares identity. Use `==`.
- Default args are evaluated **once**: never write `def f(items=[])`. Use
  `def f(items=None)` then `items = items or []`.
- Mutable default / shared state bugs are the Python equivalent of NPEs.
- Indentation errors are compile errors. Configure your editor: 4 spaces.

---

## 4. Sync vs async (`def` vs `async def`)

FastAPI accepts both.

- `def` handler -> runs in a threadpool. Safe for blocking code
  (database drivers, `requests`, the LangChain call in this project).
- `async def` handler -> runs on the event loop. Only use it if everything
  inside is awaited and non-blocking (`httpx`, `asyncpg`).

**Rule: if you are unsure, use plain `def`.** One blocking call inside an
`async def` freezes the entire server - there is no thread pool to absorb it.
That is the #1 production mistake in FastAPI.

---

## 5. Real project layout (when one file gets too big)

```
app/
  main.py            # creates FastAPI(), includes routers
  api/
    routes_faq.py    # APIRouter  -> your @RestController
  schemas/
    faq.py           # Pydantic models -> your DTOs
  services/
    faq_service.py   # business logic -> your @Service
  repositories/
    faq_repo.py      # DB access -> your @Repository / JPA
  core/
    config.py        # pydantic-settings -> @ConfigurationProperties
    deps.py          # shared Depends() providers
tests/
  test_faq.py
```

Wiring routers together:

```python
# app/api/routes_faq.py
router = APIRouter(prefix="/faqs", tags=["faqs"])

@router.get("/{faq_id}")
def get_faq(faq_id: int): ...

# app/main.py
app.include_router(router)
```

---

## 6. Testing (do this early)

```python
# tests/test_api.py
from fastapi.testclient import TestClient
from api_server import app

client = TestClient(app)          # like MockMvc, but it runs the real app

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_ask_rejects_short_question():
    r = client.post("/ask", json={"question": "hi"})
    assert r.status_code == 422
```

```powershell
pip install pytest
pytest -q
```

`assert` replaces `assertEquals`. pytest shows you the diff on failure.

---

## 7. The stack to learn next, in order

1. **FastAPI + Pydantic** - you are here. Master `Depends`, routers, response
   models, error handling.
2. **SQLAlchemy 2.0 + Alembic** - this is Hibernate + Flyway. The single
   biggest chunk of "Python backend developer". Use it with PostgreSQL.
3. **pytest** - fixtures are the killer feature (dependency injection for tests).
4. **Auth** - JWT via `python-jose` + `passlib[bcrypt]`, wired through
   `Depends(get_current_user)`. That is your Spring Security filter chain.
5. **Docker** - same as Java, but images are smaller and startup is instant.
6. **Async + background work** - `Celery` or `arq` (like `@Async` / JMS).
7. **Tooling** - `ruff` (lint + format, replaces Checkstyle + Spotless),
   `mypy` (static type checking - brings back what the Java compiler gave you).
   Add both to CI on day one; they close most of the gap you feel from losing
   the compiler.

Skip Django unless a job asks for it. FastAPI + SQLAlchemy is where the
Java-to-Python backend jobs actually are.
