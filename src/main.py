import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.shared.db import init_pool, close_pool
from src.modules.events.routes import router as events_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Application starting up...")
    init_pool()
    yield
    # Shutdown
    logger.info("Application shutting down...")
    close_pool()


app = FastAPI(title="NorthBridge Production Counter", version="1.0.0", lifespan=lifespan)

# Allow CORS for React/Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount module routers
app.include_router(events_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
