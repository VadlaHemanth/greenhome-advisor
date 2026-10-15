"""Opt-in local staging workload; never points at a public service or real AI."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered)-1, int((len(ordered)-1)*fraction))] if ordered else None


async def workload(base, users, rounds, diverse=False, properties_per_customer=1):
    async with httpx.AsyncClient(timeout=60) as client:
        homes = (await client.get(base+"/api/demo-homes")).json()
        await client.post(base+"/api/assess", json={"home": homes[0], "selected_retrofits":[]})
    records = []
    ownership = []
    isolation_checks = []
    start = asyncio.Event()

    async def visit(number):
        # Real loopback source addresses, not spoofed forwarding headers, model
        # distinct network clients while retaining the actual rate limiter.
        transport = httpx.AsyncHTTPTransport(local_address=f"127.0.1.{number+1}")
        async with httpx.AsyncClient(base_url=base, transport=transport, timeout=90) as client:
            await start.wait()
            home = deepcopy(homes[0])
            home.update(property_id=f"LOAD-{number:03}", electricity_kwh=2400.+number*17,
                        gas_kwh=6000.+number*39)
            if diverse:
                # A second workload avoids treating same-cohort cache hits as
                # proof of latency for unfamiliar property feature combinations.
                home.update(
                    property_type=["Detached","Semi detached","Mid terrace","End terrace","Bungalow","Flat"][number%6],
                    age_band=number%4+1,
                    region=f"E1200000{number%9+1}",
                    floor_area_m2=float(35+(number*19)%260),
                    epc_rating=["A","B","C","D","E","F","G"][number%7],
                )
            calls = [
                ("/api/assess", {"home":home,"selected_retrofits":["loft_insulation"]}),
                ("/api/compare", {"home":home,"package_a":["loft_insulation"],"package_b":["smart_controls"]}),
                ("/api/decision-check", {"home":home}),
                ("/api/what-if", {"home":home,"selected_retrofits":[],"question":"Explain my score","use_gemini":False}),
                ("/api/rank-homes", {"homes":[home]}),
            ]
            async def request(path, body, category=None):
                began = time.perf_counter()
                try:
                    response = await client.post(path,json=body)
                    duration = time.perf_counter()-began
                    code = None
                    if response.status_code != 200:
                        try:code=response.json().get("detail",{}).get("code")
                        except (ValueError,AttributeError):pass
                    records.append({"user":number,"path":category or path,"status":response.status_code,"seconds":duration,"code":code})
                    return response
                except httpx.HTTPError:
                    records.append({"user":number,"path":category or path,"status":0,"seconds":time.perf_counter()-began})
                    return None
            saved = await request("/api/workspace", {"consent":True})
            if saved is not None and saved.status_code == 200:
                ownership.append(saved.json()["id"])
                state = saved.json()
                for _ in range(properties_per_customer - 1):
                    customer = state["customers"][0]
                    added = await request(
                        f"/api/workspace/customers/{customer['id']}/properties",
                        {"customer_version":customer["version"],"template_id":"DEMO-01"},
                        "/api/workspace/property-add",
                    )
                    if added is None or added.status_code != 200:
                        break
                    state = added.json()
            for round_id in range(rounds):
                path, body = calls[(number+round_id)%len(calls)]
                response = await request(path,body)
                if response is not None and response.status_code==200 and path=="/api/assess":
                    assert response.json()["home"]["property_id"] == home["property_id"], "Cross-request result mix-up"
            response = await client.get("/api/workspace")
            records.append({"user":number,"path":"/api/workspace/read","status":response.status_code,"seconds":response.elapsed.total_seconds()})
            if saved is not None and saved.status_code==200:
                matched = response.status_code==200 and response.json().get("id")==saved.json()["id"]
                isolation_checks.append({
                    "user":number,"read_status":response.status_code,"matched":matched,
                    "actual_cross_owner_response":response.status_code==200 and not matched,
                    "requested_property_count_matched":matched and len(response.json()["customers"][0]["properties"])==properties_per_customer,
                })
                removed = await request("/api/workspace/delete",{"confirm":True})
    tasks = [asyncio.create_task(visit(i)) for i in range(users)]
    began = time.perf_counter()
    start.set()
    await asyncio.gather(*tasks)
    duration = time.perf_counter()-began
    grouped = defaultdict(list)
    for record in records:
        grouped[record["path"]].append(record)
    summaries = {}
    for path, group in grouped.items():
        successful = [r["seconds"] for r in group if r["status"]==200]
        summaries[path] = {
            "requests":len(group), "status_counts":dict(Counter(r["status"] for r in group)),
            "error_codes":dict(Counter(r.get("code") for r in group if r["status"]!=200)),
            "success_p50_seconds":percentile(successful,.5),
            "success_p95_seconds":percentile(successful,.95),
            "success_max_seconds":max(successful) if successful else None,
        }
    return {
        "users":users, "rounds_per_user":rounds, "elapsed_seconds":duration,
        "properties_per_first_customer":properties_per_customer,
        "requests_recorded":len(records),
        "unexpected_error_fraction":sum(r["status"] not in (200,429,503) for r in records)/len(records),
        "overload_responses":sum(r["status"] in (429,503) for r in records),
        "all_requests_successful":all(r["status"]==200 for r in records),
        "unique_private_workspaces":len(set(ownership)),
        "workspace_isolation":len(ownership)==users and len(set(ownership))==users and all(r["matched"] and r["requested_property_count_matched"] for r in isolation_checks),
        "workspace_read_checks":isolation_checks,
        "endpoints":summaries,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=100)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--diverse", action="store_true")
    parser.add_argument("--properties-per-customer", type=int, default=1, choices=(1,2,4))
    parser.add_argument("--out", default="reports/load_test_100.json")
    args = parser.parse_args()
    if not 1<=args.users<=200 or not 1<=args.rounds<=10 or not 1<=args.workers<=4:
        raise SystemExit("This local workload is bounded to 200 clients, ten rounds and four workers.")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1",0)); port=probe.getsockname()[1]
    work = ROOT/"work/load-tests"
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as directory:
        env = os.environ.copy()
        env.update({
            "GREENHOME_LLM_PROVIDER":"gemini", "GREENHOME_LIVE_LLM":"false",
            "XKIRO_API_KEY":"",
            "GEMINI_API_KEY":"", "GEMINI_KEY":"", "GREENHOME_LIVE_GEMINI":"false",
            "GREENHOME_PUBLIC_MODE":"false", "GREENHOME_GATEWAY_TOKEN":"",
            "GREENHOME_ALLOWED_HOSTS":"127.0.0.1,localhost",
            "GREENHOME_ALLOWED_ORIGINS":f"http://127.0.0.1:{port}",
            "GREENHOME_WORKSPACE_DATABASE_URL":f"sqlite:///{directory}/workspaces.sqlite3",
            "GREENHOME_PROVIDER_BUDGET_PATH":f"{directory}/provider.sqlite3",
            "GREENHOME_CALC_WORKERS":"4","GREENHOME_CALC_CAPACITY":"128",
            "GREENHOME_EXPLAIN_WORKERS":"4","GREENHOME_EXPLAIN_CAPACITY":"128",
        })
        with open(work/"server.log","w") as log:
            process = subprocess.Popen([
                str(ROOT/".venv/bin/python"),"-m","uvicorn","greenhome.api:app",
                "--host","127.0.0.1","--port",str(port),"--workers",str(args.workers),
                "--no-access-log","--no-proxy-headers","--limit-concurrency","256",
            ],cwd=ROOT,env=env,stdout=log,stderr=log)
            try:
                base=f"http://127.0.0.1:{port}"
                for _ in range(100):
                    try:
                        response=httpx.get(base+"/api/health",timeout=1)
                        if response.status_code==200:
                            assert not response.json()["gemini_configured"]
                            break
                    except httpx.HTTPError: pass
                    time.sleep(.1)
                else: raise RuntimeError("Local staging did not become ready.")
                result=asyncio.run(workload(base,args.users,args.rounds,args.diverse,args.properties_per_customer))
                result.update({
                    "tested_at_utc":datetime.now(timezone.utc).isoformat(),
                    "server_workers":args.workers,
                    "cohort_mix":"100 varying type/age/region/area/EPC combinations" if args.diverse else "same structural cohort, different metered consumption",
                    "provider":"disabled; actual deterministic local fallback, zero provider calls",
                    "scope":"Local loopback HTTP burst/workflow with real trained inference and SQLite; not a sustained SLA, cloud test, physical users or unlimited capacity.",
                    "database":"SQLite shared across local server workers",
                })
                (ROOT/args.out).write_text(json.dumps(result,indent=2)+"\n")
                print(json.dumps(result,indent=2))
            finally:
                process.terminate()
                try:process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait()
    return 0


if __name__=="__main__":
    raise SystemExit(main())
