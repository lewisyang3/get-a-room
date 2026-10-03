from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.availability import router as availability_router
from app.api.schemas.health import HealthResponse

from app.config import get_settings

settings = get_settings()

DESCRIPTION = """
Finds UC Berkeley classrooms with no scheduled class, so students can use them
to study.

- **Scheduled use only.** Availability comes from the term's class schedule.
  It doesn't track who is actually in a room, guarantee a room is unlocked, or
  know about academic holidays and breaks.
- **Times are local to the term.** Every time is a clock time in the term's
  timezone (`America/Los_Angeles` by default), so daylight saving time doesn't
  shift results.
- **07:00-22:00, to the minute.** Availability covers 07:00 to 22:00; seconds
  in a search are ignored.
- **Errors** are `{"detail": ...}`: a message for a 404, and for a 422 a list of
  `{type, loc, msg, input}` where `loc` names the parameter at fault.
"""

app = FastAPI(
    title="Get a Room API",
    version="0.1.0",
    description=DESCRIPTION,
    openapi_tags=[
        {"name": "availability", "description": "Search for available rooms."},
        {"name": "operations", "description": "Service health."},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(availability_router)


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Check the API is up",
    tags=["operations"],
)
def health() -> HealthResponse:
    """Reports that the API process is serving requests. It doesn't check the
    database."""
    return HealthResponse(status="ok")
