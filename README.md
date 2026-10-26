# UK Wind Power Forecasting & Accuracy Dashboard

An operational analytics dashboard and REST API built for an energy utility's day-ahead power purchasing team in the Great Britain (GB) electricity market. The platform evaluates national wind generation forecasts against settlement outturns across January 2026, enforcing realistic day-ahead trading gate-closure cutoff rules.

---

## 1. Executive Summary & Domain Scope

In the GB wholesale electricity market, day-ahead power trading requires commercial purchasing teams to lock their anticipated physical positions before submitting orders to power exchanges (such as EPEX SPOT GB Day-Ahead auction, where order books close at 09:20 UK local time).

This system provides:
1. **Automated Elexon BMRS ingestion**: Ingests actual outturn generation (`FUELHH`, wind fuel type) and national wind forecasts (`WINDFOR`).
2. **Deterministic Day-Ahead Cutoff Engine**: Selects the exact forecast available to a trader at a configurable decision freeze (default: **09:00 UTC on D-1**).
3. **Multi-resolution settlement alignment**: Matches 30-minute half-hourly outturns to hourly forecast cadences via two-period mean aggregation (Method A) and point matching (Method B).
4. **Accuracy metrics suite**: Computes MAE, RMSE, Mean Error (Bias), MAPE, and WAPE across custom date ranges and cutoff times.
5. **Interactive trading dashboard**: Four dedicated views for operational visibility, forecast evolution auditing, error distribution, and settlement data verification.

> [!IMPORTANT]
> **Procurement Shortfall Disclaimer**  
> Wind forecast error is **not** equivalent to portfolio procurement shortfall or cash-out imbalance penalties. A utility's procurement volume depends on consumer demand profiles, contracted supply positions, plant outages, and hedging strategies—none of which are published in public transmission generation streams. This platform analyzes the accuracy of the underlying physical wind forecast signal only.

---

## 2. January 2026 Benchmark Findings

Evaluated over the full month of January 2026 (744 delivery hours, 100% data completeness):

| Metric | January 2026 Outturn | Units | Interpretation |
| :--- | :--- | :--- | :--- |
| **Evaluated Hours ($N$)** | 744 | Hours | 31 days $\times$ 24 hours (Zero missing hours) |
| **Average Actual Generation** | 11,577.63 | MW | Average GB wind outturn across January 2026 |
| **Average Day-Ahead Forecast** | 13,429.53 | MW | Selected day-ahead forecast at 09:00 UTC D-1 |
| **Mean Absolute Error (MAE)** | 2,142.12 | MW | Average magnitude of forecast error |
| **Root Mean Squared Error (RMSE)** | 2,611.70 | MW | Quadratic error penalizing large forecast misses |
| **Mean Error (Bias: $F - A$)** | **+1,851.90** | MW | **Substantial systemic over-forecasting** by day-ahead models |
| **Mean Absolute Percentage Error (MAPE)** | 22.38% | % | Calculated strictly on non-zero actuals |
| **Weighted Absolute Percentage Error (WAPE)** | 18.50% | % | $\sum \|F - A\| / \sum A$ volume-weighted error |
| **Unmatched Forecasts / Actuals** | 0 / 0 | Intervals | Full overlap achieved across all 744 intervals |

**Key Commercial Takeaway**: Day-ahead wind forecasts consistently overestimated GB wind production throughout January 2026 by an average of **+1,851.9 MW**. A purchasing team relying unadjusted on this raw day-ahead forecast would have systematically under-procured alternative generation or hedges, exposing the utility to system buy price (cash-out) penalties during delivery.

---

## 3. Methodology & Technical Decisions

### 3.1. Day-Ahead Decision Cutoff Rule
- **Default Cutoff**: `09:00 UTC on D-1` (where $D$ is the delivery date).
- **Market Justification**: In Great Britain, EPEX SPOT GB Day-Ahead auction order books close at 09:20 UK local time (GMT in January). Purchasing teams must formulate bids, aggregate portfolio positions, and submit auction orders before 09:20. A 09:00 UTC freeze allows 20 minutes for trade execution.
- **Selection Algorithm**: For each target delivery hour $t$ on day $D$:
  $$\text{Cutoff Datetime} = \text{Delivery Date}(t) - 1\text{ day at }09:00\text{ UTC}$$
  The engine selects the forecast record with the latest `publishTime` satisfying $\text{publishTime} \le \text{Cutoff Datetime}$. Any forecast published after cutoff is strictly disqualified.
- **Lead Time Profile**: Under the 09:00 D-1 rule, lead times range from **15.0 hours** (for delivery at 00:00 on day D) to **38.0 hours** (for delivery at 23:00 on day D). Retrospective records ($\text{lead time} \le 0$) are filtered out.

### 3.2. Resolution Mismatch Handling
- `FUELHH` (Actuals) is published at **30-minute settlement periods** (48 periods/day).
- `WINDFOR` (Forecasts) is published at an **hourly cadence** (`:00` minutes).
- **Method A (Primary - Hourly Mean)**: The actual for hour $H$ (periods $2k-1$ and $2k$) is computed as:
  $$\text{Actual}_H = \frac{\text{Actual}_{2k-1} + \text{Actual}_{2k}}{2}$$
  Both half-hour periods must be present and non-null; otherwise the hour is omitted.
- **Method B (Check - Point Match)**: Uses the half-hourly outturn at `:00` without aggregation. Across January 2026, Method A and Method B produce nearly identical MAE (~2,142 MW vs ~2,149 MW), confirming that hourly aggregation does not introduce artificial distortion.

### 3.3. January Boundary Lookback Buffer
- `WINDFOR` forecasts have a lookahead horizon of up to ~66.5 hours.
- Forecasts for delivery on `2026-01-01 00:00 UTC` evaluated at `09:00 UTC on 2025-12-31` were generated from runs starting on `2025-12-30`.
- The backend automatically prepends a 4-day lookback buffer (`2025-12-28`), ensuring 100% of candidate forecasts for the start of January are captured.

### 3.4. Cache Architecture
- To prevent redundant load on Elexon BMRS and ensure high performance, raw stream responses are cached on disk in `data/cache/` with a 24-hour TTL.

---

## 4. System Architecture & Tech Stack

```
wind-forecast-dashboard/
├── backend/
│   ├── main.py                 # FastAPI application & REST endpoints
│   ├── models.py               # Pydantic v2 schemas for all requests/responses
│   ├── requirements.txt        # Backend dependencies
│   ├── Dockerfile              # Container definition for backend
│   ├── .dockerignore
│   ├── services/
│   │   ├── elexon.py           # Async HTTPX client for Elexon BMRS API
│   │   ├── forecast.py         # Cutoff filtering, resolution aggregation & matching
│   │   ├── metrics.py          # Vectorized accuracy calculations (MAE, RMSE, MAPE)
│   │   └── cache.py            # Disk-backed JSON cache with TTL
│   └── tests/
│       ├── test_elexon.py      # Elexon client unit tests
│       ├── test_forecast.py    # Cutoff rule & aggregation tests
│       ├── test_metrics.py     # Accuracy metrics verification tests
│       └── test_api.py         # FastAPI TestClient endpoint tests
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # Main application layout, tab switching & banner
│   │   ├── index.css           # Vanilla CSS design system & typography
│   │   ├── pages/
│   │   │   ├── OverviewTab.jsx         # Executive KPI cards & time series chart
│   │   │   ├── ForecastExplorerTab.jsx # Single interval revision history & audit
│   │   │   ├── AccuracyTab.jsx         # Daily error bar chart & Top 10 misses
│   │   │   └── MethodologyTab.jsx      # Math formulas & paginated raw table
│   │   └── services/
│   │       └── api.js          # REST API client
│   ├── package.json
│   ├── vite.config.js
│   ├── nginx.conf              # Production Nginx reverse proxy configuration
│   ├── Dockerfile              # Multi-stage container build for frontend
│   └── vercel.json             # Vercel SPA routing configuration
├── scripts/
│   └── explore_elexon.py       # API exploratory investigation script
├── data/
│   └── cache/                  # Gitignored JSON cache directory
├── docker-compose.yml          # Production multi-container orchestration
├── Procfile                    # Heroku web dyno entrypoint
├── heroku.yml                  # Heroku container registry definition
├── runtime.txt                 # Heroku Python runtime version
├── pytest.ini                  # Pytest configuration
└── README.md
```

- **Backend**: Python 3.12+, FastAPI, Uvicorn, Pandas, HTTPX, Pydantic v2, Pytest.
- **Frontend**: React 18, Vite, Recharts, Lucide React, Vanilla CSS.
- **Deployment**: Docker, Docker Compose, Nginx, Vercel, Heroku.

---

## 5. Dashboard Views

### View 1: Overview
- **Executive KPI Cards**: Avg Actual (11,577 MW), Avg Forecast (13,429 MW), MAE (2,142 MW), RMSE (2,611 MW), Mean Error (+1,851 MW), Matched Intervals ($N = 744$).
- **Interactive Controls**: Date range filter (restricted to January 2026) and Cutoff Time picker (e.g. `09:00`, `12:00`, `17:00`).
- **Time Series Line Chart**: Interactive comparison of selected forecast vs outturn with responsive tooltip and zoom.
- **Commercial Disclaimer Banner**: Persistent callout regarding portfolio shortfall vs forecast error.

### View 2: Forecast Explorer
- **Interval Selector**: Choose any delivery hour in January 2026.
- **Forecast Evolution**: Displays all historical forecasts published for that target hour, ordered chronologically.
- **Visual Audit**: Highlights the specific run locked in at 09:00 UTC D-1, with clear visual badges indicating whether subsequent runs were before or after gate closure.
- **Revision Step Chart**: Visualizes the trajectory of forecast revisions leading up to delivery.

### View 3: Accuracy Analysis
- **Daily Performance**: Grouped bar chart comparing daily MAE and RMSE across all 31 days.
- **Error Over Time**: Continuous time series of error ($F - A$), visualizing over-forecasting spikes vs under-forecasting troughs.
- **Top 10 Largest-Error Intervals**: Rank-ordered table of the 10 most severe forecast misses in January, detailing delivery time, publish time, actual, forecast, absolute error, and percentage error.

### View 4: Data & Methodology
- **Market Background & Rule Justification**: Detailed documentation of GB day-ahead auction timing.
- **Mathematical Formulations**: LaTeX-formatted formulas with exact MW units.
- **Raw API Schema Reference**: Table of fields from `FUELHH` and `WINDFOR`.
- **Paginated Settlement Table**: 20 records per page with search and pagination, showing start time, actual, forecast, error, absolute error, and publish time.

---

## 6. REST API Reference

All timestamps are formatted in ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`).

| Endpoint | Method | Query Parameters | Description |
| :--- | :--- | :--- | :--- |
| `/api/health` | `GET` | None | Service health status and version |
| `/api/comparison` | `GET` | `start`, `end`, `cutoff_time`, `cutoff_days_before` | Matched hourly comparison series ($F, A, \text{Error}, \text{PublishTime}$) |
| `/api/accuracy` | `GET` | `start`, `end`, `cutoff_time`, `cutoff_days_before` | Summary metrics (MAE, RMSE, ME, MAPE, WAPE, N) |
| `/api/daily-accuracy` | `GET` | `start`, `end`, `cutoff_time`, `cutoff_days_before` | Daily breakdown of MAE, RMSE, and Bias for charts |
| `/api/forecast-explorer` | `GET` | `target` (ISO datetime) | All forecast revisions for target hour and selected cutoff run |
| `/api/actuals` | `GET` | `start`, `end` | Aggregated actual generation series |
| `/api/forecasts` | `GET` | `start`, `end` | Raw forecast series |
| `/api/methodology` | `GET` | None | Full documentation of rules, formulas, and coverage |

---

## 7. Running Locally

### Prerequisites
- Python 3.11+
- Node.js 18+ and `npm`

### 7.1. Backend Setup
```bash
cd backend
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
The API documentation is available at `http://localhost:8000/docs`.

### 7.2. Frontend Setup
```bash
cd frontend
npm install

# Run Vite development server
npm run dev
```
The dashboard will open at `http://localhost:5173`.

### 7.3. Running Unit Tests
```bash
# From repository root
pytest
```
Expected output: **29 passed** unit tests covering Elexon client retries, cutoff rules, metrics, and API endpoints.

---

## 8. Docker & Container Deployment

Both services can be run simultaneously using Docker Compose:

```bash
# Build and run containers
docker compose up --build
```

- **Frontend**: Accessible at `http://localhost:3000`
- **Backend API**: Accessible at `http://localhost:8000`
- **API Documentation**: Accessible at `http://localhost:8000/docs`

To stop:
```bash
docker compose down
```

---

## 9. Cloud Deployment

### 9.1. Backend on Heroku
1. Create a Heroku application:
   ```bash
   heroku create your-wind-forecast-api
   ```
2. Configure buildpack and environment variables:
   ```bash
   heroku buildpacks:set heroku/python
   heroku config:set CORS_ORIGINS="https://your-frontend.vercel.app"
   ```
3. Deploy:
   ```bash
   git push heroku master
   ```
   *Alternatively, use `heroku.yml` with the Heroku Container Registry (`heroku stack:set container`).*

### 9.2. Frontend on Vercel
1. Install Vercel CLI or import the GitHub repository in the Vercel dashboard.
2. Set the root directory to `frontend`.
3. Set the build environment variable:
   - `VITE_API_URL`: `https://your-wind-forecast-api.herokuapp.com`
4. Deploy:
   ```bash
   cd frontend
   vercel --prod
   ```
   *The included `vercel.json` ensures client-side routing is handled without 404s.*

---

## 10. License & Confidentiality

Internal operational project developed for Day-Ahead Power Purchasing. Distributed under standard internal enterprise licensing.
