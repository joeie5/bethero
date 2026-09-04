import os
import uvicorn
import asyncio
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import predictions, results, sports, users, admin
from app.config import settings
from apscheduler.schedulers.asyncio import AsyncIOScheduler

app = FastAPI(title="Sports Predictor API")
scheduler = AsyncIOScheduler()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.on_event("startup")
async def startup():
    try:
        from app.database import init_db
        await init_db()
        print("Database connected")
    except Exception as e:
        print(f"Database connection failed: {e}")
    try:
        from app.redis_client import init_redis
        await init_redis()
        print("Redis connected")
    except Exception as e:
        print(f"Redis connection failed: {e}")
    
    # Start Keep-Alive task
    asyncio.create_task(keep_alive_ping())

async def keep_alive_ping():
    """Ping self every 10 minutes to prevent sleep"""
    await asyncio.sleep(60)  # Wait 1 min after startup
    while True:
        try:
            base_url = os.getenv(
                "RENDER_EXTERNAL_URL",
                "https://sports-predictor-1-o34s.onrender.com"
            )
            async with httpx.AsyncClient() as client:
                await client.get(
                    f"{base_url}/health",
                    timeout=10
                )
            print("Keep-alive ping sent")
        except Exception as e:
            print(f"Keep-alive failed: {e}")
        
        await asyncio.sleep(600)  # Ping every 10 minutes

@app.on_event("startup")
async def start_scheduler():
    scheduler.add_job(
        daily_predictions,
        'cron',
        hour=7,
        minute=0
    )
    scheduler.add_job(
        resolve_results,
        'interval',
        hours=2,
    )
    scheduler.start()

async def daily_predictions():
    print("Running daily prediction generation...")
    import asyncio
    from app.database import get_supabase_admin
    from app.ingestion.fixture_fetcher import fetch_all_fixtures
    from app.ml.predictor import Predictor
    from app.ml.accumulator_builder import run_accumulator_job

    await fetch_all_fixtures()

    # Generate predictions for upcoming fixtures — nothing else in this job
    # actually creates prediction rows; without this, run_accumulator_job()
    # below has nothing to build tickets from and predictions stays empty.
    def _generate_predictions():
        client = get_supabase_admin()
        results = Predictor(client).predict_upcoming()
        print(f"Generated {len(results)} predictions")
    await asyncio.to_thread(_generate_predictions)

    await asyncio.to_thread(run_accumulator_job)
    print("Daily predictions complete")

async def resolve_results():
    print("Running result resolution...")
    import asyncio
    from app.ingestion.result_fetcher import ResultFetcher
    await asyncio.to_thread(ResultFetcher().run)
    print("Result resolution complete")

app.include_router(predictions.router)
app.include_router(results.router)
app.include_router(sports.router)
app.include_router(users.router)
app.include_router(admin.router)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
