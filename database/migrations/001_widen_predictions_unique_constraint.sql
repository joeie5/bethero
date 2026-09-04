-- Widen predictions' uniqueness to (sport, fixture_id, market, selection).
--
-- Why: Corners legitimately persists TWO rows for the same (sport,
-- fixture_id, market="Over_Under_Corners") — one for the "Over 7.5" leg,
-- one for the "Under 9.5" leg (CLAUDE.md §1.3: both lines are required,
-- evaluated independently, not a two-sided choice of one line).
--
-- The live constraint predictions_sport_fixture_id_market_key is only on
-- (sport, fixture_id, market), so the second Corners row always violates
-- it — confirmed live: a real predict_upcoming() batch generated 7 valid
-- predictions and persisted 0, because the Corners pair's duplicate key
-- aborted the whole insert (Postgres batch inserts are atomic).
--
-- `selection` already disambiguates the two Corners lines ("Over 7.5" vs
-- "Under 9.5"), so widening the constraint to include it is the minimal,
-- purely-broadening fix — it can't invalidate any row that was previously
-- valid under the narrower constraint.
--
-- No local Postgres / DDL access was available in the session that found
-- this bug (Supabase MCP disconnected, no DATABASE_URL in .env) — apply
-- this via the Supabase SQL editor before relying on live predictions
-- persisting for any market that shares Corners' multi-line shape.

ALTER TABLE predictions
    DROP CONSTRAINT IF EXISTS predictions_sport_fixture_id_market_key;

ALTER TABLE predictions
    ADD CONSTRAINT predictions_sport_fixture_id_market_selection_key
    UNIQUE (sport, fixture_id, market, selection);
