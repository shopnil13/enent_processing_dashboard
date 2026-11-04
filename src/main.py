import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
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

# Mount API module routers
app.include_router(events_router)
app.include_router(state_router)
app.include_router(ack_router)
app.include_router(mqtt_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}


# Serve built frontend if available
frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.exists() and (frontend_dist / "index.html").exists():
    logger.info(f"Serving frontend static build from {frontend_dist}")
    if (frontend_dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api"):
            return JSONResponse(status_code=404, content={"error": "Not found"})
        file_path = frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(frontend_dist / "index.html")
