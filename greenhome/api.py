"""Local-only JSON boundary. No UI imports, credentials in payloads, or request state."""
from __future__ import annotations

from copy import deepcopy
import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
import json
import math
import os
import re
import secrets
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from greenhome import engine, explain
from greenhome.security import AuthenticatedGatewayContext, PilotBoundary, ServiceBusy, enabled
from greenhome.service import CalculationService, integer_setting
from greenhome.providers import configured_provider, xkiro_transport

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models"
METRICS_PATH = ROOT / "reports" / "training_metrics.json"
MAX_BODY_BYTES = 64 * 1024
BODY_READ_TIMEOUT_SECONDS = 10.0
LOCAL_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

RetrofitId = Literal[
    "loft_insulation", "double_glazing", "smart_controls", "heat_pump", "solar_pv"
]
Package = Annotated[list[RetrofitId], Field(max_length=5)]
Energy = Annotated[float, Field(ge=0, le=10_000_000, allow_inf_nan=False)]
Fraction = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class StrictInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class HomeInput(StrictInput):
    property_id: Annotated[
        str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    ] | None = None
    property_type: Literal[
        "Detached", "Semi detached", "Mid terrace", "End terrace", "Bungalow", "Flat"
    ] | None = None
    age_band: Annotated[int, Field(ge=1, le=5)] | None = None
    region: Literal[
        "E12000001", "E12000002", "E12000003", "E12000004", "E12000005",
        "E12000006", "E12000007", "E12000008", "E12000009", "W92000004",
    ] | None = None
    floor_area_m2: Annotated[
        float, Field(ge=0.01, le=100_000, allow_inf_nan=False)
    ] | None = None
    epc_rating: Literal["A", "A/B", "B", "C", "D", "E", "F", "G"] | None = None
    electricity_kwh: Energy | None = None
    gas_kwh: Energy | None = None
    heating: Literal["gas_boiler", "heat_pump", "electric_resistance", "unknown"] | None = None
    insulation: Literal["poor", "partial", "good", "unknown"] | None = None
    glazing: Literal["single", "double", "triple", "unknown"] | None = None
    solar_kwp: Annotated[float, Field(ge=0, le=10_000, allow_inf_nan=False)] | None = None
    smart_controls: bool | None = None
    roof_access: bool | None = None
    listed_building: bool | None = None
    consent_confirmed: bool | None = None
    heat_pump_ready: bool | None = None
    current_value_gbp: Annotated[
        float, Field(gt=0, le=1_000_000_000_000, allow_inf_nan=False)
    ] | None = None
    budget_gbp: Annotated[
        float, Field(ge=0, le=1_000_000_000, allow_inf_nan=False)
    ] | None = None
    data_kind: Literal["synthetic_demo", "user_entered"] | None = None
    excluded_retrofits: Package = Field(default_factory=list)

    @field_validator("excluded_retrofits")
    @classmethod
    def unique_exclusions(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Deferred improvements must be unique.")
        return value
    # Omitted assumptions are left to the engine, which discloses their defaults.
    # Explicit null assumptions are rejected, matching engine.validate_home.
    space_heat_fraction: Fraction = engine.DEFAULT_ASSUMPTIONS["space_heat_fraction"]
    boiler_efficiency: Annotated[
        float, Field(gt=0, le=1, allow_inf_nan=False)
    ] = engine.DEFAULT_ASSUMPTIONS["boiler_efficiency"]
    heat_pump_spf: Annotated[
        float, Field(ge=1, le=6, allow_inf_nan=False)
    ] = engine.DEFAULT_ASSUMPTIONS["heat_pump_spf"]
    solar_yield_kwh_per_kwp: Annotated[
        float, Field(gt=0, le=2000, allow_inf_nan=False)
    ] = engine.DEFAULT_ASSUMPTIONS["solar_yield_kwh_per_kwp"]
    solar_self_consumption_fraction: Fraction = engine.DEFAULT_ASSUMPTIONS[
        "solar_self_consumption_fraction"
    ]

    @field_validator(
        "floor_area_m2", "electricity_kwh", "gas_kwh", "solar_kwp",
        "current_value_gbp", "budget_gbp", "space_heat_fraction", "boiler_efficiency",
        "heat_pump_spf", "solar_yield_kwh_per_kwp", "solar_self_consumption_fraction",
        mode="before",
    )
    @classmethod
    def finite_json_number(cls, value):
        if value is None:
            return value
        if type(value) not in (int, float):
            raise ValueError("A finite JSON number is required.")
        try:
            finite = math.isfinite(value)
        except (OverflowError, ValueError):
            finite = False
        if not finite:
            raise ValueError("A finite JSON number is required.")
        return value

    def engine_home(self) -> dict:
        # Do not drop explicit nulls, or turn omitted permissions into False.
        return self.model_dump(exclude_unset=True)


class AssessInput(StrictInput):
    home: HomeInput
    selected_retrofits: Package | None = None


class DecisionInput(StrictInput):
    home: HomeInput


class RankInput(StrictInput):
    homes: Annotated[list[HomeInput], Field(min_length=1, max_length=100)]

    @field_validator("homes")
    @classmethod
    def unique_properties(cls, value):
        ids = [home.property_id for home in value]
        if any(item is None for item in ids) or len(set(ids)) != len(ids):
            raise ValueError("Ranking requires distinct property identifiers.")
        return value


class EnergyInputs(StrictInput):
    csv_text: Annotated[str, Field(min_length=1, max_length=16384)]
    end_month: Annotated[str, Field(pattern=r"^\d{4}-\d{2}$")]


class CompareInput(StrictInput):
    home: HomeInput
    package_a: Package | None
    package_b: Package | None


class WhatIfInput(StrictInput):
    home: HomeInput
    selected_retrofits: Package | None = None
    question: Annotated[str, Field(min_length=1, max_length=explain.MAX_QUESTION_LENGTH)]
    use_gemini: bool = False

    @field_validator("question")
    @classmethod
    def nonblank_question(cls, value):
        if not value.strip():
            raise ValueError("A question is required.")
        return value


class InvalidScenario(Exception):
    """Domain rejection; never include the original exception or user input."""


def _assess(home: dict, selected: list[str] | None) -> dict:
    try:
        return engine.assess(deepcopy(home), deepcopy(selected))
    except ValueError:
        raise InvalidScenario() from None


class ExplanationEngine:
    """Preserve explain's calculation flow while mapping infeasibility to HTTP 422."""

    @staticmethod
    def validate_home(home):
        return engine.validate_home(home)

    @staticmethod
    def assess(home, selected):
        return _assess(home, selected)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": {"code": code, "message": message}})


class RequestBoundary:
    """Buffer at most 64 KiB before any JSON parsing, including chunked bodies."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False
        limit = 256 * 1024 if scope.get("path") == "/api/rank-homes" else MAX_BODY_BYTES

        async def safe_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                path = scope.get("path", "")
                cache_policy = b"no-store"
                if path.startswith("/assets/"):
                    hashed = re.search(r"-[A-Za-z0-9_-]{8,}\.(?:js|css|woff2?)$", path)
                    cache_policy = b"public, max-age=31536000, immutable" if hashed else b"public, max-age=3600"
                message = {
                    **message,
                    "headers": [
                        *message.get("headers", []),
                        (b"cache-control", cache_policy),
                        (b"x-content-type-options", b"nosniff"),
                    ],
                }
            await send(message)

        try:
            for key, value in scope.get("headers", []):
                if key.lower() == b"content-length":
                    try:
                        length = int(value)
                    except (ValueError, OverflowError):
                        await _error(400, "invalid_length", "Invalid content length.")(
                            scope, receive, safe_send
                        )
                        return
                    if length < 0:
                        await _error(400, "invalid_length", "Invalid content length.")(
                            scope, receive, safe_send
                        )
                        return
                    if length > limit:
                        await _error(413, "body_too_large", "Request body exceeds this endpoint's limit.")(
                            scope, receive, safe_send
                        )
                        return
            chunks, size = [], 0
            body_deadline = asyncio.get_running_loop().time() + BODY_READ_TIMEOUT_SECONDS
            while True:
                try:
                    remaining = max(0.001, body_deadline - asyncio.get_running_loop().time())
                    message = await asyncio.wait_for(receive(), timeout=remaining)
                except asyncio.TimeoutError:
                    await _error(408, "body_timeout", "Request body was not received in time.")(
                        scope, receive, safe_send
                    )
                    return
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > limit:
                    await _error(413, "body_too_large", "Request body exceeds this endpoint's limit.")(
                        scope, receive, safe_send
                    )
                    return
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            body, delivered = b"".join(chunks), False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            await self.app(scope, replay, safe_send)
        except Exception:
            # Catch inside ServerErrorMiddleware: do not re-raise secret-bearing
            # exceptions to Uvicorn's traceback logger. JSON endpoints do not stream.
            if not started:
                await _error(500, "internal_error", "An unexpected server error occurred.")(
                    scope, receive, safe_send
                )


def _gemini_key() -> str:
    return os.environ.get("GEMINI_KEY", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()


def _numeric_fields(data, names) -> dict:
    if not isinstance(data, dict):
        return {}
    output = {}
    for name in names:
        value = data.get(name)
        if type(value) in (int, float):
            try:
                if math.isfinite(value):
                    output[name] = value
            except (ValueError, OverflowError):
                pass
    return output


def _mapping(value) -> dict:
    return value if isinstance(value, dict) else {}


def aggregate_metrics() -> dict:
    """Explicit projection only: never return rows, paths, logs or arbitrary text."""
    try:
        with METRICS_PATH.open("rb") as handle:
            raw = handle.read(256 * 1024 + 1)
        if len(raw) > 256 * 1024:
            raise ValueError()
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError()
    except (OSError, ValueError, RecursionError):
        return {"status": "unavailable", "metrics": None}
    energy = {}
    targets = _mapping(_mapping(data.get("energy")).get("targets"))
    for fuel in ("electricity", "gas"):
        target = _mapping(targets.get(fuel))
        if not target:
            continue
        energy[fuel] = {}
        for split in ("validation", "test"):
            source = _mapping(target.get(split))
            energy[fuel][split] = {
                name: _numeric_fields(source.get(name), ("mae", "rmse", "n"))
                for name in ("model", "dummy_median")
            }
            energy[fuel][split].update(
                _numeric_fields(source, ("mae_improvement_percent_vs_dummy",))
            )
    source = _mapping(data.get("synthetic_value"))
    value = _numeric_fields(source, ("nominal_interval_coverage",))
    for split in ("validation", "test"):
        summary = _mapping(source.get(split))
        if not summary:
            continue
        value[split] = _numeric_fields(summary, (
            "coverage_p10_p90_all_scenarios", "coverage_p10_p90_active_scenarios",
            "property_all_scenarios_covered_fraction",
            "mean_interval_width_percentage_points", "active_mean_interval_width_percentage_points",
            "no_op_rows", "active_rows",
        ))
        for name in ("p50_percent", "dummy_median_percent", "p50_gbp"):
            value[split][name] = _numeric_fields(summary.get(name), ("mae", "rmse", "n"))
        value[split]["pinball_loss"] = _numeric_fields(
            summary.get("pinball_loss"), ("p10", "p50", "p90")
        )
    return {
        "status": "available",
        "metrics": {"energy": energy, "synthetic_value": value},
        "note": "Energy metrics are cohort benchmarks. Value metrics evaluate synthetic references only, not market accuracy.",
    }


def create_app(*, load_environment: bool = True) -> FastAPI:
    if load_environment:
        load_dotenv(ROOT / ".env", override=False, verbose=False)
    public_mode = enabled("GREENHOME_PUBLIC_MODE")
    provider_settings = configured_provider()
    live_enabled = provider_settings.live_enabled
    gateway_token = os.environ.get("GREENHOME_GATEWAY_TOKEN", "")
    if public_mode and live_enabled and len(gateway_token) < 32:
        raise RuntimeError("Public Gemini requires a configured authenticated gateway token.")
    origins = [s.strip() for s in os.environ.get("GREENHOME_ALLOWED_ORIGINS", ",".join(LOCAL_ORIGINS + ["http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:4173", "http://127.0.0.1:4173"])).split(",") if s.strip()]
    hosts = [s.strip() for s in os.environ.get("GREENHOME_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if s.strip()]
    if "*" in origins or "*" in hosts:
        raise RuntimeError("Explicit allowed origins and hosts are required.")
    calculations = CalculationService(
        integer_setting("GREENHOME_CALC_WORKERS", 4, 1, 32),
        integer_setting("GREENHOME_CALC_CAPACITY", 128, 32, 1024),
    )
    # Long provider waits have a separate pool and cannot starve scoring jobs.
    explanations = CalculationService(
        integer_setting("GREENHOME_EXPLAIN_WORKERS", 4, 1, 16),
        integer_setting("GREENHOME_EXPLAIN_CAPACITY", 32, 16, 256),
    )
    from greenhome.readiness import Readiness
    readiness = Readiness()

    @asynccontextmanager
    async def lifespan(_app):
        try:
            await asyncio.to_thread(workspace_router.workspace_store.warm)
            if enabled("GREENHOME_WARM_MODELS", True):
                ready = await asyncio.to_thread(readiness.check)
                if ready["status"] != "ready":
                    raise RuntimeError("Required release assets or local inference are not ready.")
            yield
        finally:
            calculations.close()
            explanations.close()
            workspace_router.workspace_mutations.close()
            workspace_router.workspace_store.close()

    application = FastAPI(
        title="Green Home JSON API", version="1.0.0",
        docs_url=None, redoc_url=None, openapi_url=None if public_mode else "/openapi.json", debug=False,
        lifespan=lifespan,
    )
    application.add_middleware(RequestBoundary)
    application.add_middleware(AuthenticatedGatewayContext, token=gateway_token, active=public_mode)
    application.add_middleware(PilotBoundary, allowed_origins=origins)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    application.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)

    @application.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError):
        known = {
            "body", *HomeInput.model_fields, *AssessInput.model_fields,
            *CompareInput.model_fields, *WhatIfInput.model_fields, *RankInput.model_fields,
            *EnergyInputs.model_fields,
        }
        # Unknown field NAMES can themselves contain secrets. Do not echo those
        # either, nor Pydantic's input/ctx/body/message representations.
        detail = [{
            "loc": [part if type(part) is int or part in known else "<unknown>"
                    for part in error.get("loc", ())],
            "type": error.get("type", "value_error"),
            "msg": "Missing, unsupported, out-of-range or invalid input.",
        } for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": detail})

    @application.exception_handler(InvalidScenario)
    async def invalid_scenario(request: Request, exc: InvalidScenario):
        return _error(
            422, "invalid_scenario",
            "The home or package is invalid or infeasible. Check missing fields, permissions and budget.",
        )

    @application.exception_handler(ServiceBusy)
    async def service_busy(request: Request, exc: ServiceBusy):
        return _error(503, "service_busy", "Calculations are busy. Please try again shortly.")

    @application.get("/api/health")
    def health():
        current = configured_provider()
        return {
            "status": "ok",
            "models": {
                "energy_benchmark": (MODEL_DIR / "energy_benchmark.joblib").is_file(),
                "synthetic_value": (MODEL_DIR / "synthetic_value.joblib").is_file(),
            },
            # Backward-compatible field name; new clients use explicit provider metadata.
            "gemini_configured": bool(current.key) and live_enabled,
            **{**current.public(), "llm_configured": bool(current.key) and live_enabled},
        }

    @application.get("/api/demo-homes")
    def demo_homes():
        return deepcopy(engine.demo_homes())

    @application.get("/api/readiness")
    def ready():
        result = readiness.check()
        return JSONResponse(result, status_code=200 if result["status"] == "ready" else 503)

    @application.get("/api/release")
    def release():
        from greenhome.release_metadata import release_metadata
        # The shared request boundary supplies the API's no-store policy.
        return release_metadata(os.environ)

    @application.get("/api/catalogue")
    def catalogue():
        return [
            {"id": rid, "name": item["name"], "cost_gbp": list(item["cost_gbp"]),
             "order": item["order"]}
            for rid, item in engine.RETROFITS.items()
        ]

    @application.get("/api/metrics")
    def metrics():
        return aggregate_metrics()

    @application.post("/api/assess")
    async def assess(payload: AssessInput):
        return await calculations.run(_assess, payload.home.engine_home(), payload.selected_retrofits)

    @application.post("/api/compare")
    async def compare(payload: CompareInput):
        def calculate():
            return {
                "package_a": _assess(payload.home.engine_home(), payload.package_a),
                "package_b": _assess(payload.home.engine_home(), payload.package_b),
            }
        return await calculations.run(calculate)

    @application.post("/api/what-if")
    async def what_if(payload: WhatIfInput, request: Request):
        if public_mode and payload.use_gemini and live_enabled:
            provided = request.headers.get("X-GreenHome-Gateway", "")
            if not secrets.compare_digest(provided, gateway_token):
                return _error(403, "authentication_required", "Authenticated access is required for live AI.")
        transport = None
        use_gemini = payload.use_gemini and live_enabled
        current = configured_provider()
        if use_gemini and current.key:
            transport = xkiro_transport(current.key, current.model) if current.name == "xkiro" else explain._sdk_transport(current.key, current.model)
        reply = await explanations.run(
            explain.answer_question,
            payload.question, payload.home.engine_home(), payload.selected_retrofits,
            engine=ExplanationEngine(), transport=transport, use_gemini=use_gemini,
            interpret_with_gemini=False,
            provider=current.name, model_name=current.model,
        )
        # Clarifications may return before any provider transport is used.
        reply.provider, reply.model = current.name, current.model
        return asdict(reply)

    @application.post("/api/energy-inputs")
    async def energy_inputs(payload: EnergyInputs):
        from greenhome.energy_inputs import annualise_csv
        try:
            return await calculations.run(annualise_csv, payload.csv_text, payload.end_month)
        except ValueError:
            return _error(422, "invalid_energy_input", "Check the CSV headers, completed months and non-negative kWh values. Duplicate months and formula cells are not accepted.")

    @application.post("/api/decision-check")
    async def decision_check(payload: DecisionInput):
        from greenhome.decision import decision_check as calculate_decision
        try:
            return await calculations.run(calculate_decision, payload.home.engine_home())
        except ValueError:
            raise InvalidScenario() from None

    @application.post("/api/rank-homes")
    async def rank_homes(payload: RankInput):
        from greenhome.ranking import rank_homes as rank
        try:
            return await calculations.run(rank, [home.engine_home() for home in payload.homes])
        except ValueError:
            raise InvalidScenario() from None

    # Imported here so model and persistence modules never depend on api.py.
    from greenhome.workspace_api import create_workspace_router
    from greenhome.ranking import rank_homes as rank
    workspace_router = create_workspace_router(HomeInput, rank)
    application.include_router(workspace_router)
    from greenhome.money_api import make_money_router
    application.include_router(make_money_router(HomeInput, run_calculation=calculations.run))

    # Only the compiled frontend directory is exposed; never serve the repository.
    built = ROOT / "frontend" / "dist"
    if (built / "index.html").is_file():
        if (built / "assets").is_dir():
            application.mount("/assets", StaticFiles(directory=built / "assets"), name="frontend-assets")

        @application.get("/", include_in_schema=False)
        def frontend():
            return FileResponse(built / "index.html")

    return application


app = create_app()
