from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import get_settings
from src.api.v1 import transcribe, debug, auth, meetings, admin

settings = get_settings()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["authentication"])
app.include_router(transcribe.router, prefix="/api/v1/transcribe", tags=["transcription"])
app.include_router(meetings.router, prefix="/api/v1/meetings", tags=["meetings"])
app.include_router(debug.router, prefix="/api/v1/debug", tags=["debug"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])

@app.get("/health")
async def health_check():
    return {"status": "ok"}