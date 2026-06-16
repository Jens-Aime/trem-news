"""
History router — paginated access to persisted analysis records.

Endpoints
─────────
  GET /api/v1/history   Paginated AnalysisResult + event metadata (newest first)
"""

import math
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db import repository
from app.models import HistoryResponse

router = APIRouter(prefix="/history", tags=["history"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=HistoryResponse)
async def get_history(
    session: DbDep,
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> HistoryResponse:
    """Return paginated history of all AI analyses, newest first."""
    items, total = await repository.get_history(session, page=page, page_size=page_size)
    pages = max(1, math.ceil(total / page_size))
    return HistoryResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )
