"""Opt-in fictional memory router. Never imports the main API or calls a provider."""
import asyncio
from copy import deepcopy
from datetime import date, datetime
from zoneinfo import ZoneInfo
import json
import os
import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model, field_validator

from greenhome import engine
from greenhome.security import ServiceBusy, enabled
from greenhome.service import CalculationService
from greenhome.workspace_store import (
    MAX_EVENTS, MAX_VERSION, TTL_SECONDS, WorkspaceError, WorkspaceStore,
    effective_home, invalid, iso_utc, new_token, token_hash,
)

COOKIE_NAME = "greenhome_workspace"
PUBLIC_COOKIE_NAME = "__Host-greenhome_workspace"
MAX_BODY_BYTES = 16 * 1024
BODY_TIMEOUT_SECONDS = 10
RetrofitId = Literal["loft_insulation", "double_glazing", "smart_controls", "heat_pump", "solar_pv"]
RetrofitList = Annotated[list[RetrofitId], Field(max_length=5)]
Version = Annotated[int, Field(ge=1, le=MAX_VERSION)]


class StrictInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class ConsentInput(StrictInput):
    consent: bool


class DeleteInput(StrictInput):
    confirm: bool


class Preferences(StrictInput):
    budget_gbp: Annotated[float, Field(ge=0, le=1_000_000_000)] | None
    deferred_retrofits: RetrofitList
    priority: Literal["energy", "carbon", "low_cost"]
    disruption: Literal["flexible", "minimal"]

    @field_validator("deferred_retrofits")
    @classmethod
    def unique_deferrals(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Duplicate retrofit IDs.")
        return value


class CustomerFields(StrictInput):
    version: Version
    preferences: Preferences
    selected_retrofits: RetrofitList
    review_status: Literal["new", "reviewing", "ready", "deferred"]
    baseline_confirmed_after_completion: bool = False

    @field_validator("selected_retrofits")
    @classmethod
    def unique_selection(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Duplicate retrofit IDs.")
        return value


class CompletionInput(StrictInput):
    version: Version
    kind: Literal["completed"]
    retrofit_id: RetrofitId
    completed_on: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$", max_length=10)]
    confirmed: bool


class CustomerPreferences(StrictInput):
    deferred_retrofits: RetrofitList
    priority: Literal["energy", "carbon", "low_cost"]
    disruption: Literal["flexible", "minimal"]

    @field_validator("deferred_retrofits")
    @classmethod
    def unique_deferrals(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Duplicate retrofit IDs.")
        return value


class SettingsInput(StrictInput):
    version: Version
    customer_preferences: CustomerPreferences
    portfolio_budget_gbp: Annotated[float, Field(ge=0, le=1_000_000_000)] | None
    legacy_completed_reserve_gbp: Annotated[float, Field(ge=0, le=1_000_000_000)] | None
    confirm_legacy_reserve: bool = False


class AddPropertyInput(StrictInput):
    customer_version: Version
    template_id: Literal["DEMO-01", "DEMO-02", "DEMO-03", "DEMO-04"]


class PropertyFields(CustomerFields):
    customer_version: Version


class PropertyCompletionInput(CompletionInput):
    customer_version: Version


def _validate_selection(home, selected):
    excluded = home.get("excluded_retrofits", [])
    if set(selected) & set(excluded):
        raise invalid("A deferred measure cannot be selected.")
    try:
        # Engine owns feasibility, package budget, savings, and signed results.
        engine.assess(deepcopy(home), list(selected))
    except ValueError:
        raise invalid("The home or selected package is invalid or infeasible. Reassess before saving.") from None


def create_workspace_router(home_model, ranker):
    """Build the standalone boundary; lead mounts it with app.include_router().

    The injected ranker is deliberately not called on persistence requests:
    ranking belongs to /api/rank-homes and no derived estimates are stored.
    Saved homes carry budget/exclusions ready for that injected ranking contract.
    """
    if not isinstance(home_model, type) or not issubclass(home_model, BaseModel) or not callable(ranker):
        raise TypeError("Provide a Pydantic home model and callable ranker.")
    store = WorkspaceStore.from_environment()
    # SQLite writes serialize by design. Queue once per worker instead of
    # occupying Starlette's shared pool with many threads waiting on one lock.
    mutations = CalculationService(workers=1 if store.sqlite else 4, capacity=128)
    public_mode = enabled("GREENHOME_PUBLIC_MODE")
    cookie_name = PUBLIC_COOKIE_NAME if public_mode else COOKIE_NAME
    cookie_path = "/" if public_mode else "/api/workspace"
    default_origins = ",".join(
        f"http://{host}:{port}" for host in ("localhost", "127.0.0.1")
        for port in (5173, 8000, 4173)
    )
    allowed_origins = frozenset(value.strip() for value in os.environ.get(
        "GREENHOME_ALLOWED_ORIGINS", "" if public_mode else default_origins
    ).split(",") if value.strip())
    if "*" in allowed_origins:
        raise ValueError("Workspace cookie access cannot allow wildcard origins.")
    # Existing DEMO identifiers survive migration; added homes receive opaque,
    # server-created PROP identifiers. Every save checks immutable identity too.
    WorkspaceHome = create_model(
        "WorkspaceHome", __base__=home_model,
        data_kind=(Literal["synthetic_demo"], ...),
        property_id=(Annotated[str, Field(pattern=r"^(DEMO-0[1-4]|PROP-[a-f0-9]{32})$", max_length=64)], ...),
        excluded_retrofits=(RetrofitList, Field(default_factory=list)),
    )
    CustomerUpdate = create_model("WorkspaceCustomerUpdate", __base__=CustomerFields, home=(WorkspaceHome, ...))
    PropertyUpdate = create_model("WorkspacePropertyUpdate", __base__=PropertyFields, home=(WorkspaceHome, ...))

    def clear_cookie(response):
        response.delete_cookie(cookie_name, path=cookie_path, secure=public_mode, httponly=True, samesite="strict")

    class WorkspaceRoute(APIRoute):
        def get_route_handler(self):
            handler = super().get_route_handler()

            async def guarded(request: Request):
                try:
                    if (public_mode and request.url.scheme != "https"
                            and request.scope.get("greenhome.authenticated_gateway") is not True):
                        raise WorkspaceError(403, "https_required", "Public workspace access requires HTTPS.")
                    if request.query_params:
                        raise invalid("Workspace endpoints do not accept query parameters.")
                    origin = request.headers.get("origin")
                    same_origin = f"{request.url.scheme}://{request.url.netloc}"
                    if origin and origin != same_origin and origin not in allowed_origins:
                        raise WorkspaceError(403, "origin_not_allowed", "This browser origin is not allowed.")
                    if request.headers.get("sec-fetch-site") == "cross-site":
                        raise WorkspaceError(403, "origin_not_allowed", "Cross-site workspace access is not allowed.")
                    if request.method == "POST":
                        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                            raise WorkspaceError(415, "json_required", "Use application/json.")
                        size, chunks = 0, []
                        async with asyncio.timeout(BODY_TIMEOUT_SECONDS):
                            async for chunk in request.stream():
                                size += len(chunk)
                                if size > MAX_BODY_BYTES:
                                    raise WorkspaceError(413, "body_too_large", "Workspace request exceeds 16 KiB.")
                                chunks.append(chunk)
                        request._body = b"".join(chunks)
                    response = await handler(request)
                except (RequestValidationError, ValidationError, json.JSONDecodeError, UnicodeDecodeError):
                    response = JSONResponse(
                        {"detail": {"code": "invalid_workspace_input", "message": "Invalid fictional workspace input."}},
                        status_code=422,
                    )
                except WorkspaceError as exc:
                    response = JSONResponse({"detail": {"code": exc.code, "message": exc.message}}, status_code=exc.status)
                    if exc.status == 401:
                        clear_cookie(response)
                except TimeoutError:
                    response = JSONResponse({"detail": {"code": "body_timeout", "message": "Workspace request timed out."}},
                                            status_code=408)
                except ServiceBusy:
                    response = JSONResponse(
                        {"detail": {"code": "workspace_busy", "message": "Saved workspace requests are busy. Please retry."}},
                        status_code=503,
                    )
                except Exception:
                    # No payload, token, SQL error, driver URL or traceback reaches the client/log.
                    response = JSONResponse(
                        {"detail": {"code": "workspace_unavailable", "message": "Workspace storage is temporarily unavailable."}},
                        status_code=503,
                    )
                response.headers["Cache-Control"] = "no-store"
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["Referrer-Policy"] = "no-referrer"
                return response

            return guarded

    router = APIRouter(prefix="/api/workspace", tags=["fictional workspace"], route_class=WorkspaceRoute)
    # Explicit maintenance/test hook; it is not exposed as an HTTP endpoint.
    router.workspace_store = store
    router.workspace_mutations = mutations

    def authenticated_cookie(request: Request):
        value = request.cookies.get(cookie_name)
        token_hash(value)  # Format validation only; every store operation also authorizes.
        return value

    Token = Annotated[str, Depends(authenticated_cookie)]

    @router.get("")
    def get_workspace(token: Token):
        return store.get(token)

    @router.get("/session")
    def session_workspace(request: Request):
        """Normal anonymous bootstrap is not a failed private-record request."""
        token = request.cookies.get(cookie_name)
        if not token:
            return None
        try:
            return store.get(token)
        except WorkspaceError as exc:
            if exc.status != 401:
                raise
            response = JSONResponse(None)
            clear_cookie(response)
            return response

    def fictional_seeds():
        seeds = []
        for home in engine.demo_homes():
            validated = WorkspaceHome.model_validate(home).model_dump(exclude_unset=True)
            validated["excluded_retrofits"] = []
            if engine.validate_home(validated):
                raise ValueError("Invalid fictional seed.")
            seeds.append({
                "home": validated,
                "preferences": {"budget_gbp": home.get("budget_gbp"), "deferred_retrofits": [],
                                "priority": "energy", "disruption": "flexible"},
                "selected_retrofits": [], "review_status": "new",
                "baseline_status": "current", "events": [],
            })
        return seeds

    @router.post("")
    async def create_workspace(body: ConsentInput, request: Request):
        if body.consent is not True:
            raise invalid("Explicit consent to fictional demonstration persistence is required.")
        existing = request.cookies.get(cookie_name)
        if existing:
            try:
                return await mutations.run(store.get, existing)
            except WorkspaceError as exc:
                if exc.status != 401:
                    raise
        seeds = fictional_seeds()
        token = new_token()
        data = await mutations.run(store.create, token, seeds)
        response = JSONResponse(data)
        response.set_cookie(cookie_name, token, max_age=TTL_SECONDS, httponly=True, secure=public_mode,
                            samesite="strict", path=cookie_path)
        return response

    @router.get("/export")
    def export_workspace(token: Token):
        return JSONResponse(store.get(token), headers={
            "Content-Disposition": 'attachment; filename="greenhome-fictional-workspace.json"',
        })

    @router.post("/delete")
    async def delete_workspace(body: DeleteInput, token: Token):
        if body.confirm is not True:
            raise invalid("Explicit deletion confirmation is required.")
        await mutations.run(store.delete, token)
        response = JSONResponse({"deleted": True})
        clear_cookie(response)
        return response

    @router.get("/customers/{customer_id}")
    def get_customer(customer_id: str, token: Token):
        workspace = store.get(token)
        if not any(customer["id"] == customer_id for customer in workspace["customers"]):
            raise WorkspaceError(404, "customer_not_found", "Fictional customer not found.")
        return workspace

    @router.get("/customers/{customer_id}/properties/{property_id}")
    def get_property(customer_id: str, property_id: str, token: Token):
        workspace = store.get(token)
        if not any(customer["id"] == customer_id and
                   any(prop["id"] == property_id for prop in customer["properties"])
                   for customer in workspace["customers"]):
            raise WorkspaceError(404, "property_not_found", "Fictional property not found.")
        return workspace

    @router.post("/customers/{customer_id}/properties")
    async def add_property(customer_id: str, body: AddPropertyInput, token: Token):
        seed = next(state for state in fictional_seeds() if state["home"]["property_id"] == body.template_id)
        return await mutations.run(store.add_property, token, customer_id, body.customer_version, seed)

    @router.post("/customers/{customer_id}/settings")
    async def update_settings(customer_id: str, body: SettingsInput, token: Token):
        def change(current):
            reserve = body.legacy_completed_reserve_gbp
            old = current["legacy_completed_reserve_gbp"]
            if reserve is None and (old is not None or body.confirm_legacy_reserve):
                raise invalid("A confirmed legacy reserve cannot be changed to unknown.")
            if reserve != old and body.confirm_legacy_reserve is not True:
                raise invalid("Explicitly confirm the aggregate legacy planning reserve, including an intentional zero.")
            return {
                "customer_preferences": body.customer_preferences.model_dump(),
                "portfolio_budget_gbp": body.portfolio_budget_gbp,
                "legacy_completed_reserve_gbp": reserve,
            }
        return await mutations.run(store.settings, token, customer_id, body.version, change)

    def property_change(body):
        def change(current, settings):
            home = body.home.model_dump(exclude_unset=True)
            if home["property_id"] != current["home"]["property_id"]:
                raise invalid("The fictional property reference cannot be changed.")
            preferences = body.preferences.model_dump()
            excluded = home.get("excluded_retrofits", [])
            if len(excluded) != len(set(excluded)):
                raise invalid("Duplicate retrofit IDs.")
            # Preferences are authoritative; a stale HomeInput projection cannot override them.
            home["budget_gbp"] = preferences["budget_gbp"]
            home["excluded_retrofits"] = list(preferences["deferred_retrofits"])
            from greenhome.workspace_migration import completed_features_valid
            if set(body.selected_retrofits) & {item["retrofit_id"] for item in current["events"]}:
                raise invalid("A completed measure cannot be selected again.")
            if not completed_features_valid(home, current["events"]):
                raise invalid("A recorded installed feature cannot be removed or downgraded in this release.")
            baseline_status = current["baseline_status"]
            known_fuels = home.get("electricity_kwh") is not None and home.get("gas_kwh") is not None
            if baseline_status == "needs_update":
                if known_fuels:
                    if not body.baseline_confirmed_after_completion:
                        raise invalid("Explicitly confirm both fuel figures are the replacement post-completion baseline.")
                    baseline_status = "current"
                elif body.baseline_confirmed_after_completion:
                    raise invalid("Both fuel figures are required to confirm a replacement baseline.")
            updated = {
                "home": home, "preferences": preferences,
                "selected_retrofits": list(body.selected_retrofits), "review_status": body.review_status,
                "baseline_status": baseline_status, "events": current["events"],
            }
            _validate_selection(effective_home(updated, settings), body.selected_retrofits)
            return updated
        return change

    @router.post("/customers/{customer_id}")
    async def update_customer(customer_id: str, body: CustomerUpdate, token: Token):
        return await mutations.run(store.legacy_property, token, customer_id, body.version, property_change(body))

    @router.post("/customers/{customer_id}/properties/{property_id}")
    async def update_property(customer_id: str, property_id: str, body: PropertyUpdate, token: Token):
        return await mutations.run(store.mutate_property, token, customer_id, property_id,
                                   body.customer_version, body.version, property_change(body))

    def completion_change(body):
        def change(current, settings):
            if body.confirmed is not True:
                raise invalid("Explicit completion confirmation is required.")
            try:
                completed_on = date.fromisoformat(body.completed_on)
            except ValueError:
                raise invalid("Use a valid completion date in YYYY-MM-DD format.") from None
            if completed_on > datetime.fromtimestamp(store.now(), ZoneInfo("Europe/London")).date():
                raise invalid("Completion cannot be recorded in the future.")
            if len(current["events"]) >= MAX_EVENTS:
                raise WorkspaceError(409, "history_limit", "This customer's completion history is full.")
            rid = body.retrofit_id
            if rid not in current["selected_retrofits"]:
                raise invalid("Only a saved, engine-validated selected measure can be completed.")
            if any(item["retrofit_id"] == rid for item in current["events"]):
                raise invalid("This measure already has a completion record.")
            # Subsequent members of an already-validated package may be recorded
            # while fuels are unknown. Never infer a replacement bill to reassess.
            if current["baseline_status"] != "needs_update":
                _validate_selection(effective_home(current, settings), current["selected_retrofits"])
            features = {
                "loft_insulation": ("insulation", "good"),
                "double_glazing": ("glazing", "double"),
                "smart_controls": ("smart_controls", True),
                "solar_pv": ("solar_kwp", 3.0),
                "heat_pump": ("heating", "heat_pump"),
            }
            key, value = features[rid]
            current["home"][key] = value
            current["home"]["electricity_kwh"] = None
            current["home"]["gas_kwh"] = None
            current["baseline_status"] = "needs_update"
            current["selected_retrofits"].remove(rid)
            current["events"].append({
                "id": secrets.token_hex(16), "kind": "completed", "retrofit_id": rid,
                "completed_on": completed_on.isoformat(), "created_at": iso_utc(store.now()),
                "planning_cost_upper_gbp": engine.RETROFITS[rid]["cost_gbp"][1],
            })
            return current
        return change

    @router.post("/customers/{customer_id}/events")
    async def complete_retrofit(customer_id: str, body: CompletionInput, token: Token):
        return await mutations.run(store.legacy_property, token, customer_id, body.version, completion_change(body))

    @router.post("/customers/{customer_id}/properties/{property_id}/events")
    async def complete_property_retrofit(customer_id: str, property_id: str,
                                        body: PropertyCompletionInput, token: Token):
        return await mutations.run(store.mutate_property, token, customer_id, property_id,
                                   body.customer_version, body.version, completion_change(body))

    return router
