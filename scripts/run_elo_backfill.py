"""One-off: recompute Elo ratings for all football matches and backfill
them into the live team_form_cache table (this is what
app.ml.feature_engineer._get_cached_elo() actually reads from)."""
import time
from app.database import get_supabase_admin
from app.ml.elo_calculator import EloCalculator

client = get_supabase_admin()
calc = EloCalculator(client, "football")

t0 = time.time()
matches = calc._load_matches()
print(f"[1/3] Loaded {len(matches)} matches in {time.time()-t0:.1f}s")

t0 = time.time()
for i, match in enumerate(matches):
    calc._process_match(match)
    if (i + 1) % 50_000 == 0:
        print(f"  processed {i+1}/{len(matches)} matches ({time.time()-t0:.1f}s elapsed)")
print(f"[2/3] Processed all matches, {len(calc._snapshots)} raw snapshots, in {time.time()-t0:.1f}s")
print(f"      Teams tracked: {len(calc._states)}")

t0 = time.time()
calc._flush_snapshots()
print(f"[3/3] Flushed to team_form_cache in {time.time()-t0:.1f}s")

print("\nTop 10 current ratings:")
print(calc.current_ratings().head(10).to_string(index=False))
