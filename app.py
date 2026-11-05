"""HTTP server for a fine-tuned Laya checkpoint mounted on LAYA_MODEL_DIR.

Uses laya's own server (`laya.serve.create_app`: POST /v1/systemone, /v1/systemone/batch,
GET /health, bearer auth via LAYA_API_KEY) but with a Router that only knows the local
checkpoint. The stock `laya-serve` routes by language between the Hub checkpoints
(english / multilingual / typed-decisions) and would download them; here every one of those
names points at the same, single, already-built Agent, so nothing is fetched and the
weights are held in memory once.

Environment:
    LAYA_MODEL_DIR   checkpoint directory (model.safetensors + rl_agent_config.json)  /models/laya
    LAYA_MODEL_NAME  name the checkpoint is served under (client `model` field)      laya-local
    LAYA_DEVICE      cpu / cuda / auto                                                (auto)
    LAYA_THREADS     torch intra-op threads for CPU inference (<= physical cores)    (torch default)
    LAYA_API_KEY     required: clients must send `Authorization: Bearer <key>`        (none)
    LAYA_ALLOW_NO_AUTH  set to 1 to start without LAYA_API_KEY (local tests only)    0
    LAYA_HOST / LAYA_PORT / LAYA_LOG_LEVEL / LAYA_MAX_CONCURRENT / ...  as in laya.serve

Auth: the bearer check itself is laya's (`laya.serve.create_app` reads LAYA_API_KEY and compares
the `Authorization` header with `hmac.compare_digest`, 401 on mismatch, on every route; /health
answers only {"status": "ok"} to an unauthenticated caller). laya silently serves WITHOUT auth
when the variable is empty, so `check_auth_config` below refuses to start in that case.
"""
import logging
import os

import torch
import uvicorn

import laya
from laya.router import Router
from laya.serve import create_app

log = logging.getLogger("laya-local")

MODEL_DIR = os.environ.get("LAYA_MODEL_DIR", "/models/laya")
MODEL_NAME = os.environ.get("LAYA_MODEL_NAME", "laya-local").strip().lower()
# Every name the Router can route to on its own; all of them must land on our checkpoint.
BUILTIN_NAMES = ("english", "multilingual", "typed-decisions")


def _device():
    raw = (os.environ.get("LAYA_DEVICE") or "").strip().lower()
    return None if raw in ("", "auto") else raw


def _apply_threads():
    raw = (os.environ.get("LAYA_THREADS") or "").strip()
    if raw:
        torch.set_num_threads(max(1, int(raw)))


def check_auth_config():
    key = (os.environ.get("LAYA_API_KEY") or "").strip()
    allow_open = (os.environ.get("LAYA_ALLOW_NO_AUTH") or "").strip().lower() in ("1", "true", "yes")
    if key:
        if len(key) < 16:
            log.warning("LAYA_API_KEY is short (%d chars); use a long random value", len(key))
        os.environ["LAYA_API_KEY"] = key   # laya.serve reads it from here
        log.info("bearer auth enabled")
    elif allow_open:
        os.environ.pop("LAYA_API_KEY", None)
        log.warning("LAYA_ALLOW_NO_AUTH=1: serving WITHOUT authentication")
    else:
        raise SystemExit("LAYA_API_KEY is empty: refusing to start an unauthenticated server "
                         "(set LAYA_ALLOW_NO_AUTH=1 for local tests only)")


def build_router() -> Router:
    model_file = os.path.join(MODEL_DIR, "model.safetensors")
    if not os.path.isfile(model_file):
        raise SystemExit(f"no model.safetensors in {MODEL_DIR!r}: is the model volume mounted "
                         f"on {MODEL_DIR}? (LAYA_MODEL_DIR)")
    _apply_threads()
    device = _device()

    log.info("loading checkpoint %s (device=%s)", MODEL_DIR, device or "auto")
    agent = laya.Agent(MODEL_DIR, device=device)

    names = (MODEL_NAME,) + BUILTIN_NAMES
    # Re-point the built-ins to the local directory (a reload after an eviction stays local),
    # then hand them all the one Agent so no second copy is ever built.
    router = Router(models={n: MODEL_DIR for n in names}, device=device,
                    default=MODEL_NAME, max_loaded=len(names))
    for n in names:
        router.attach(n, agent)
    log.info("serving %s as %s (aliases: %s) on %s", MODEL_DIR, MODEL_NAME,
             ", ".join(BUILTIN_NAMES), getattr(agent, "device", "?"))
    return router


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    check_auth_config()
    app = create_app(build_router())
    uvicorn.run(
        app,
        host=os.environ.get("LAYA_HOST", "0.0.0.0"),
        port=int(os.environ.get("LAYA_PORT") or 8000),
        log_level=os.environ.get("LAYA_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
