from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import api
from app.core.config import settings

app = FastAPI(title="Flora-Bot Crop Care API", version="1.0.0", description="API and persistence layer for real Flora-Bot hardware and inference data.")
frontend_origins = settings.cors_origins
if settings.environment == "development":
    frontend_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    max_age=600,
)
app.include_router(api)

@app.get("/health")
def health():
    return {"status": "ok", "environment": settings.environment}
