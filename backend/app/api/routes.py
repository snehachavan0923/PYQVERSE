from fastapi import APIRouter

router = APIRouter()


@router.get("/", tags=["root"])
def read_root() -> dict[str, str]:
    return {
        "message": "PYQVERSE API is running",
        "docs": "/docs",
        "health": "/health",
    }


@router.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
