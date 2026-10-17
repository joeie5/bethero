# start_backend.ps1 — launches the Bet Hero API locally.
#
# MODEL_DIR is set here explicitly (not just relying on the permanent user
# env var from `setx`) because setx only takes effect in NEW shells/process
# trees started after it ran — a shell or IDE terminal already open when
# this was set won't see it until reopened. Models were moved to D: then
# back to C: after D: silently lost the files between sessions (2026-09-18,
# cause unclear) — app/ml/models/__init__.py already reads MODEL_DIR via
# os.getenv() with a fallback to the relative "models" dir, so this is the
# only wiring needed, no code changes.

$env:MODEL_DIR = "C:\bethero_models"

# api-football / api-sports.io free tier key — fixture_fetcher.py and
# routers/admin.py read this via bare os.getenv(), which does not see .env
# (pydantic-settings only loads .env into the Settings class), so it must
# be a real process env var here too.
$env:API_SPORTS_KEY = "4425c6faf96faad31706bdf167ded8c6"

# The Odds API — primary result-checking source (app/ingestion/
# odds_api_results.py), one call per league instead of per fixture.
$env:ODDS_API_KEY = "5f1a890725a8b04ca19a3f14ab549eac"

Set-Location $PSScriptRoot
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
