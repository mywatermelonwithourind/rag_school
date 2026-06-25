"""健康检查 — api 组"""

from fastapi import APIRouter

from app.api.schemas import HealthResponse
from app.core.database import ping_mysql

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    mysql_ok = ping_mysql()
    return HealthResponse(
        status="ok" if mysql_ok else "degraded",
        mysql=mysql_ok,
        milvus=False,  # TODO(api/retrieval): Milvus ping
    )
