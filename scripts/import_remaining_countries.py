"""One-off: re-run the (now Div-fallback-fixed) football importer for every
Main-tier country still showing the corners/cards DB_GAP, one country at a
time so one failure doesn't block the rest."""
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

from pathlib import Path
from app.database import get_supabase_admin
from app.ingestion.football_importer import FootballImporter

COUNTRIES = [
    "belgium", "france", "germany", "greece", "italy",
    "netherlands", "portugal", "scotland", "spain", "turkey",
]

client = get_supabase_admin()
DATA_ROOT = Path("backtest_web/data/football")

for country in COUNTRIES:
    print(f"\n{'='*60}\n{country}\n{'='*60}", flush=True)
    try:
        imp = FootballImporter(data_dir=DATA_ROOT / country, supabase_admin=client)
        imp.run()
    except Exception as e:
        print(f"COUNTRY FAILED: {country}: {e}", flush=True)

print("\n=== ALL COUNTRIES DONE ===", flush=True)
