# GridWise

GridWise is a FastAPI service for 24-hour campus energy scheduling. It interprets operator notes, validates supported directives, and minimizes grid electricity cost with PuLP.

## Current status

The local pipeline uses Ollama for operator-note interpretation, deterministic guardrails, and PuLP optimization:

1. Pydantic validates the request.
2. `directives.py` converts supported public note patterns into structured directives.
3. `validator.py` applies deterministic directive guardrails and replays the final plan.
4. `optimizer.py` solves the schedule with PuLP/CBC.
5. `main.py` exposes the HTTP API.

## Local Ollama model

Install Ollama for Windows from https://ollama.com/download/windows, then download the model once:

```powershell
ollama pull llama3.2:3b
ollama list
```

Ollama serves at `http://localhost:11434`. Optional configuration:

```powershell
$env:OLLAMA_URL="http://localhost:11434"
$env:OLLAMA_MODEL="llama3.2:3b"
$env:OLLAMA_TIMEOUT_SECONDS="5"
```

The adapter sends `operator_notes` to Ollama, validates its JSON response with `validator.py`, and only then sends directives to PuLP. If Ollama is unavailable, the deterministic parser is used as a local development fallback.

The adapter caches up to 256 repeated note-and-capacity interpretations and falls back after the configured Ollama timeout. The fallback keeps the API responsive when the local model is unavailable; deploy with a reachable model because the challenge requires a language-capable model in the interpretation path.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run

```powershell
.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Ollama normally runs automatically after installation. If needed, start it in a separate terminal with `ollama serve` before calling `/optimize-energy`.

## Endpoints

Health check:

```powershell
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

The main endpoint is `POST /optimize-energy` and accepts `scenario_id`, 1-3 `operator_notes`, 24 hourly records, and a battery object as defined by `models.py`.

## Public sample test

Run the deterministic public-case test suite:

```powershell
.venv\Scripts\python.exe -m unittest test_public_samples.py -v
```

For a live API check, start Ollama and the API, then POST any `input` object from `BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json` to `http://127.0.0.1:8000/optimize-energy`.

PowerShell sample request using the first public case:

```powershell
$sample = (Get-Content .\BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json -Raw | ConvertFrom-Json).cases[0].input
$sample | ConvertTo-Json -Depth 10 | curl.exe -X POST http://127.0.0.1:8000/optimize-energy -H "Content-Type: application/json" --data-binary @-
```

## Docker

Build and run the service:

```powershell
docker build -t gridwise:local .
docker run --rm -p 8000:8000 gridwise:local
```

The container exposes port `8000` and binds to `0.0.0.0`. Ollama remains a separate service; configure `OLLAMA_URL` and `OLLAMA_MODEL` when the container must reach a model service.

## Dependencies

- FastAPI and Uvicorn for the HTTP service
- Pydantic for request validation
- PuLP with its CBC solver for linear optimization

No API keys or secrets are required. Never commit model credentials or `.env` files.

## Known limitations

- Ollama must be installed and running for the mandatory LLM path; deterministic parsing is only a development fallback.
- Public sample cases should be used to verify interpretation, directive application, replay validity, and recalculated totals before deployment.
- A public deployment and pullable registry image still need to be created for final submission.
