import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.shared.db import init_pool, close_pool
from src.modules.events.routes import router as events_router
from src.modules.state.routes import router as state_router
from src.modules.ack.routes import router as ack_router
from src.modules.mqtt.routes import router as mqtt_router
from src.modules.mqtt.worker import start_mqtt_worker, stop_mqtt_worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Application starting up...")
    init_pool()
    if os.getenv("ENABLE_MQTT", "true").lower() in ("true", "1", "yes"):
        try:
            start_mqtt_worker()
        except Exception as e:
            logger.warning(f"Could not connect MQTT worker on startup: {e}")
    yield
    # Shutdown
    logger.info("Application shutting down...")
    stop_mqtt_worker()
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
app.include_router(state_router)
app.include_router(ack_router)
app.include_router(mqtt_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
