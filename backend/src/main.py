from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from src.config import Settings, get_settings
from src.api import transcribe


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

app.include_router(transcribe.router, prefix="/api", tags=["transcription"])

@app.get("/health")
async def health_check():
    return {"status": "ok"}
