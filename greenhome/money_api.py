"""Injectable money router; deliberately never imports greenhome.api."""

from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, create_model

from greenhome.money import MoneyPlanResponse, TariffInput, money_plan
from greenhome.security import ServiceBusy
from greenhome.service import CalculationService


def _error(code: str, message: str, *, status: int = 422) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": {"code": code, "message": message}})


class MoneyRoute(APIRoute):
    """Sanitize validation without requiring parent-specific error handlers."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request: Request):
            try:
                response = await handler(request)
            except RequestValidationError:
                response = _error("invalid_money_input", "Missing, unsupported, out-of-range or invalid money input.")
            except ServiceBusy:
                response = _error(
                    "service_busy", "Calculations are busy. Please try again shortly.", status=503,
                )
            response.headers["Cache-Control"] = "no-store"
            return response

        return guarded


def make_money_router(
    HomeInput: type[BaseModel], *, run_calculation: Callable[..., Awaitable[dict]] | None = None,
) -> APIRouter:
    """Inject the parent's ``calculations.run`` to share bounded CPU admission.

    Reuse the injected API's exact home model and its existing bounded Package
    annotation rather than importing api.py or copying its RetrofitId literals.
    Without an injected runner, own a one-worker/eight-job CalculationService
    and close it with the router lifespan. Injected services remain parent-owned.
    """
    if (not isinstance(HomeInput, type) or not issubclass(HomeInput, BaseModel)
            or "excluded_retrofits" not in HomeInput.model_fields
            or not callable(getattr(HomeInput, "engine_home", None))):
        raise TypeError("Provide the existing HomeInput model with its package field and engine_home method.")
    package = HomeInput.model_fields["excluded_retrofits"].rebuild_annotation()
    MoneyPlanInput = create_model(
        "MoneyPlanInput",
        __config__=ConfigDict(strict=True, extra="forbid", allow_inf_nan=False),
        home=(HomeInput, ...), selected_retrofits=(package, ...), tariffs=(TariffInput, ...),
    )
    standalone = None
    if run_calculation is None:
        standalone = CalculationService(workers=1, capacity=8)
        run_calculation = standalone.run

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            if standalone is not None:
                standalone.close()

    router = APIRouter(route_class=MoneyRoute, lifespan=lifespan)

    @router.post("/api/money-plan", response_model=MoneyPlanResponse)
    async def plan(body: MoneyPlanInput):
        try:
            return await run_calculation(
                money_plan, body.home.engine_home(), body.selected_retrofits, body.tariffs,
            )
        except ValueError:
            return _error(
                "invalid_scenario",
                "The home or package is invalid or infeasible. Check missing fields, permissions and budget.",
            )

    return router
