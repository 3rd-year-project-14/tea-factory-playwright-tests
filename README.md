# PureLeaf Tea Factory — Test Automation

End-to-end and API test suite for the PureLeaf Tea Factory Management System
(React + Tailwind frontend, Spring Boot backend, PostgreSQL, Firebase Auth),
built with **Python + Playwright + pytest**.

## 1. Overview

The suite is split into two layers, following the test pyramid:

- **API tests** (`tests/api/`) — fast, direct HTTP calls against the Spring
  Boot backend via `playwright.request`. Used for the bulk of business-logic
  coverage (auth, CRUD, calculations, validation).
- **UI tests** (`tests/ui/`) — real Chromium browser sessions driving the
  React frontend, reserved for flows that matter end-to-end: login, and any
  form that's actually wired to the backend (not every "management" page is —
  see `UI_TESTS_INTERVIEW_GUIDE.md` for the investigation behind that call).

Both layers cross-verify against PostgreSQL directly (`psycopg2`) where the
API alone can't confirm a side effect (e.g. a role change, a deleted row).

## 2. Architecture

```
playwright-tests/
├── pages/              Page Object Model — one class per real, backend-wired
│                        UI flow (LoginPage, TeaRatePage, FertilizerStockRequestPage).
│                        Not every page gets a wrapper: read-only/mock pages have
│                        no stable interactive surface worth abstracting.
├── tests/
│   ├── api/             Backend REST API tests
│   └── ui/               Browser tests (Playwright + pytest-playwright fixtures)
├── utils/
│   └── test_data.py      Loads non-secret fixture data from data/test_data.json
├── data/
│   └── test_data.json    Reusable form inputs / sample payloads (no secrets)
├── screenshots/          Auto-captured on test failure (gitignored)
├── reports/               HTML test report output (gitignored)
├── conftest.py            Fixtures: browser config, api_context, db_conn, Firebase auth
├── pytest.ini              pytest + reporting configuration
└── requirements.txt
```

Credentials (test user email/password, Firebase API key) live in `.env` and
are never committed or duplicated into `data/test_data.json` — that file is
strictly for non-secret sample values (e.g. a gross-sale-average number, a
stock-request quantity).

## 3. Installation

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
playwright install                # downloads Chromium/Firefox/WebKit binaries
```

Create a `.env` file (see `.env` keys below) with:

```
FIREBASE_API_KEY=...
TEST_USER_EMAIL=...
TEST_USER_PASSWORD=...
TEST_USER_UID=...
SLOWMO_MS=0        # optional: ms delay between actions, useful with --headed
```

The backend (`localhost:8080`) and frontend (`localhost:5174`) must be
running locally — `conftest.py` points at those URLs.

## 4. Running Tests

```bash
# Everything (API + UI), headless, Chromium
pytest

# UI tests only, watch it run
pytest tests/ui --headed

# A single module / test
pytest tests/ui/test_login_ui.py -k test_valid_login_redirects_away_from_login_page

# Cross-browser
pytest --browser firefox
pytest --browser webkit
pytest --browser chromium --browser firefox --browser webkit   # all three

# Smoke subset only (login + auth + health check) -- fast sanity check
pytest -m smoke

# Everything except smoke (full regression pool)
pytest -m "not smoke"

# API-only / UI-only
pytest -m api
pytest -m ui

# Parallel execution (pytest-xdist) -- distributes tests across workers
pytest -n auto        # one worker per CPU core
pytest -n 4            # explicit worker count
```

## 5. Test Organization (Markers)

Registered in `pytest.ini`:

| Marker | Meaning |
|---|---|
| `smoke` | Critical-path tests (login, auth, health check) — run on every push |
| `regression` | Everything else — full functional coverage |
| `api` | Backend REST API tests (applied file-wide via `pytestmark` in `tests/api/`) |
| `ui` | Browser-driven frontend tests (applied file-wide via `pytestmark` in `tests/ui/`) |

## 6. Reporting & Failure Diagnostics

Configured in `pytest.ini`:

- **HTML report** — every run writes `reports/report.html` (self-contained,
  open directly in a browser). Shows pass/fail per test, duration, and
  captured output.
- **Screenshot on failure** — any failing UI test automatically saves a
  screenshot to `screenshots/`, named after the test.
- **Structured execution log** — `conftest.py` hooks `pytest_runtest_makereport`
  to write one line per test (`PASSED`/`FAILED`/`SKIPPED`, duration, full
  node ID) to `reports/test_execution.log`, independent of console output —
  useful for CI log inspection without re-running.

```bash
pytest --html=reports/report.html --self-contained-html   # explicit form (also the default via addopts)
```

## 7. CI/CD

`.github/workflows/playwright-tests.yml` runs on every push/PR:

1. Checks out **three separate repos** as sibling directories on the runner —
   this test suite, `tea-factory-backend`, and `tea-factory-frontend-web` are
   not a monorepo, so each needs its own `actions/checkout` step.
2. Spins up a `postgres:16` service container (matches `conftest.py`'s `DB_CONFIG`).
3. Builds and starts the Spring Boot backend (`mvnw package` + `java -jar`).
4. Installs and starts the Vite frontend dev server on port 5174.
5. Waits for both to respond (`wait-on`), then runs `pytest -m smoke -n auto`.
6. Uploads the HTML report + failure screenshots as build artifacts.

A second job (`full-regression`) runs the entire suite across all three
browsers, triggered manually via `workflow_dispatch` (or adjust the `on:`
block to run it nightly on a schedule).

Requires these repository secrets:

- `FIREBASE_API_KEY`, `TEST_USER_EMAIL`, `TEST_USER_PASSWORD` — the suite
  authenticates against a real Firebase project (see
  `conftest.py::firebase_id_token`); this can't be mocked away without
  changing the app's auth flow itself.
- `FIREBASE_CREDENTIALS` — the backend's `FirebaseConfig.java` needs Admin SDK
  credentials to verify login tokens. Locally it reads the gitignored
  `firebase-service-account.json`; that file doesn't exist on the CI runner,
  so paste its contents **base64-encoded** into this secret (matches the
  deployed-container path `FirebaseConfig.java` already supports):
  `base64 -w0 firebase-service-account.json` (macOS: `base64 -i firebase-service-account.json`).
  Never commit that JSON file or paste its raw contents anywhere outside the
  GitHub secret field itself — it's an Admin SDK key with full project access.

## 8. Locator Strategy

Priority order used throughout `pages/` and `tests/`:
`get_by_role` → `get_by_label` → `get_by_placeholder` → `get_by_text` →
CSS selector (only where the form has no accessible role/label — several
forms in this app aren't using `htmlFor`/`id` label association, a known
frontend gap documented in `UI_TESTS_INTERVIEW_GUIDE.md`).

## 9. Further Reading

- `INTERVIEW_NOTES.md` — API testing walkthrough and findings (Sinhala + English).
- `UI_TESTS_INTERVIEW_GUIDE.md` — UI testing strategy, why certain pages were
  skipped, and frontend gaps discovered while writing these tests.
