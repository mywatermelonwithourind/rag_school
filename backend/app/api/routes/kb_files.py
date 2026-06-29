"""Knowledge-base file management API."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query

from app.api.schemas import (
    KbFileDeleteResponse,
    KbFileDetailSchema,
    KbFileListResponse,
    KbFileSummarySchema,
)
from app.file_management.service import (
    KbFileConsistencyError,
    KbFileNotFoundError,
    delete_kb_file,
    get_kb_file,
    list_kb_files,
)

router = APIRouter(prefix="/kb/files", tags=["knowledge-base-files"])
logger = logging.getLogger(__name__)


@router.get("", response_model=KbFileListResponse)
async def list_files(
    kb_id: str = Query(default="kb_cs_college", min_length=1, max_length=64),
):
    try:
        items = await asyncio.to_thread(list_kb_files, kb_id)
    except Exception as exc:
        logger.exception("Failed to list knowledge-base files")
        raise HTTPException(status_code=503, detail=f"文件列表读取失败: {exc}") from exc
    return KbFileListResponse(
        total=len(items),
        items=[KbFileSummarySchema(**item) for item in items],
    )


@router.get("/{file_id}", response_model=KbFileDetailSchema)
async def get_file(
    file_id: str,
    include_children: bool = Query(default=False),
):
    try:
        item = await asyncio.to_thread(
            get_kb_file,
            file_id,
            include_children=include_children,
        )
    except KbFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="文件不存在") from exc
    except Exception as exc:
        logger.exception("Failed to read knowledge-base file")
        raise HTTPException(status_code=503, detail=f"文件读取失败: {exc}") from exc
    return KbFileDetailSchema(**item)


@router.delete("/{file_id}", response_model=KbFileDeleteResponse)
async def delete_file(file_id: str):
    try:
        result = await asyncio.to_thread(delete_kb_file, file_id)
    except KbFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="文件不存在") from exc
    except KbFileConsistencyError as exc:
        logger.exception("Knowledge-base file deletion was compensated or marked")
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to delete knowledge-base file")
        raise HTTPException(status_code=500, detail=f"出库失败: {exc}") from exc
    return KbFileDeleteResponse(**result)
