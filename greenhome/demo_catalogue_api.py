"""Read-only router for the fixed fictional catalogue; parent registers it."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from greenhome.demo_catalogue import (
    CatalogueIntegrityError, PropertyType, RankingStatus, browse_catalogue,
)


def create_demo_catalogue_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/demo-catalogue")
    def demo_catalogue(
        q: Annotated[str, Query(max_length=100)] = "",
        property_type: PropertyType | None = None,
        status: RankingStatus | None = None,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=24)] = 12,
    ):
        try:
            return browse_catalogue(
                q=q, property_type=property_type, status=status, page=page, page_size=page_size,
            )
        except CatalogueIntegrityError:
            # Do not expose paths, hash contents or raw parse exceptions.
            raise HTTPException(status_code=503, detail={
                "code": "demo_catalogue_unavailable",
                "message": "The fictional catalogue is temporarily unavailable.",
            }) from None

    return router
