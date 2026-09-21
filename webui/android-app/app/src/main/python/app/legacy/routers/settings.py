"""Settings API endpoints - Android adapted."""
from fastapi import APIRouter
from ..config import get_settings, update_settings
from ..models import Settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def read_settings():
    """Get current application settings."""
    return get_settings()


@router.put("")
async def write_settings(updates: Settings):
    """Update application settings (partial update supported)."""
    # pydantic v1 uses .dict() instead of .model_dump()
    data = updates.dict(exclude_none=True)
    return update_settings(data)
