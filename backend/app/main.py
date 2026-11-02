from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
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


@app.exception_handler(RequestValidationError)
async def safe_validation_error(_request: Request, error: RequestValidationError):
    # Pydantic errors can carry the submitted input. Return field locations and
    # static messages only so password/token-like values are never echoed.
    safe_errors = [
        {
            "loc": item.get("loc", []),
            "msg": item.get("msg", "Invalid request value"),
            "type": item.get("type", "value_error"),
        }
        for item in error.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": safe_errors})

@app.get("/health")
def health():
    return {"status": "ok", "environment": settings.environment}
