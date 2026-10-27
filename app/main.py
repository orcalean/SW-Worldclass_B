from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes import router
from app.config import get_settings
from app.jobs import runner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    runner.recover_interrupted()
    yield


app = FastAPI(
    title="sw-world-class",
    version="0.1.0",
    description="SOP benchmark audit engine. Ingest any SOP into a canonical SOPDocument, evaluate it against "
                "OracLean SQDCME rubrics (L1/L2/L3) and return deterministic scores, gates and improvements.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"], allow_headers=["*"],
)
app.include_router(router)
