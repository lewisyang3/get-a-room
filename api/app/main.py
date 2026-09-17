from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.availability import router as availability_router

from app.config import get_settings

settings = get_settings()

app = FastAPI(title="Get a Room API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(availability_router)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
