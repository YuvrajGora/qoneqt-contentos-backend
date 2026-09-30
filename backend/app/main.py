from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.routes import health, generation
from app.core.config import settings
from app.services.image_generator import TEMP_ASSETS_DIR

app = FastAPI(title="Content Pipeline API", version="1.0.0")

# Configure CORS allowed origins
allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

if settings.frontend_origin:
    for origin in settings.frontend_origin.split(","):
        origin = origin.strip()
        if origin and origin not in allowed_origins:
            allowed_origins.append(origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure assets dir exists so StaticFiles doesn't crash on startup
TEMP_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=str(TEMP_ASSETS_DIR)), name="assets")

app.include_router(health.router)
app.include_router(generation.router, prefix=settings.api_prefix)
if settings.api_prefix:
    app.include_router(generation.router)
if settings.api_prefix != "/api":
    app.include_router(generation.router, prefix="/api")

