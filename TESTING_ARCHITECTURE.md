# Testing Architecture — Visual Overview

Two diagrams for the interview: how a single test run flows through the
stack, and how CI/CD automates that same flow on every push.

## 1. Test Execution Flow

```mermaid
flowchart TD
    subgraph Runner["pytest + Playwright (Python)"]
        A[pytest collects tests] --> B{Marker filter}
        B -->|"-m smoke"| C[Critical-path subset]
        B -->|"-m regression / full run"| D[Full 88-test suite]
        C --> E[Test execution]
        D --> E
    end

    E --> F{Test type}

    F -->|"tests/api/*"| G[playwright.request\nAPI context]
    F -->|"tests/ui/*"| H[Playwright browser\nChromium/Firefox/WebKit]

    H --> I[pages/ Page Object Model\nLoginPage, TeaRatePage,\nFertilizerStockRequestPage]
    I --> J[React Frontend\nlocalhost:5174]

    G --> K[Spring Boot REST API\nlocalhost:8080]
    J -->|HTTP calls| K

    K --> L[(PostgreSQL\nTea DB)]
    J -.->|real login| M[Firebase Auth\nIdentity Toolkit API]

    E --> N[Cross-verification]
    N --> O[psycopg2 direct DB query]
    N --> P[API response assertion]
    O --> L

    E --> Q[Reporting]
    Q --> R[HTML report\nreports/report.html]
    Q --> S[Screenshot on failure\nscreenshots/]
    Q --> T[Structured log\nreports/test_execution.log]
```

**Key point for the interview:** tests don't just trust the UI or the API in
isolation — a UI test that submits a form (e.g. Tea Rate) is cross-verified
against the database or the API afterward, because a frontend can show a
fake success message even when the backend call silently failed.

## 2. CI/CD Pipeline (GitHub Actions)

```mermaid
flowchart LR
    A[git push / PR] --> B[GitHub Actions triggered]
    B --> C1[Checkout\nplaywright-tests]
    B --> C2[Checkout\ntea-factory-backend]
    B --> C3[Checkout\ntea-factory-frontend-web]

    C1 & C2 & C3 --> D[Spin up postgres:16\nservice container]
    D --> E[Build & start backend\nmvnw package + java -jar]
    E --> F[Install & start frontend\nnpm ci + vite dev]
    F --> G[wait-on: both respond]

    G --> H[pytest -m smoke -n auto\nparallel execution]
    H --> I{Result}
    I -->|Pass| J[Upload HTML report\n+ log as artifacts]
    I -->|Fail| K[Upload report\n+ screenshots for debugging]

    L[workflow_dispatch\nmanual trigger] --> M[full-regression job\nall 3 browsers, full suite]
```

**Key point for the interview:** backend, frontend, and this test suite are
three separate GitHub repos (not a monorepo), so the pipeline checks each
one out independently and lays them out as siblings on the runner before
building anything.

## 3. Test Organization Summary

```mermaid
flowchart TD
    Suite[88 tests] --> API[tests/api/\n17 files]
    Suite --> UI[tests/ui/\n14 files]

    API --> APIMarker[pytestmark = api]
    UI --> UIMarker[pytestmark = ui]

    APIMarker --> Smoke1[smoke: auth, ping]
    UIMarker --> Smoke2[smoke: login]

    Smoke1 & Smoke2 --> FastCI[Runs on every push/PR\n~15s wall time, parallel]
    API & UI --> Full[Runs on-demand\nfull-regression job]
```
