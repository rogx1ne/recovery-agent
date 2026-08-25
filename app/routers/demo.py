"""
routers/demo.py — Endpoints for triggering and monitoring live demo batches.

Endpoints:
  POST /api/v1/demo/run-batch       Trigger full 10-transaction demo batch in background
  GET  /api/v1/demo/status/{batch_id}  Poll completion progress for a batch
"""

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.models.transaction import Transaction, TransactionStatus
from app.services.demo_seed import (
    DEMO_BATCH_CASES,
    execute_full_demo_batch,
    generate_batch_id,
    get_demo_batch_live_status,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/demo", tags=["Demo"])

DbDep = Annotated[Session, Depends(get_db)]


def _run_demo_batch_worker(batch_id: str):
    """Background task worker: creates 10 txs, runs recovery, simulates webhooks."""
    db = SessionLocal()
    try:
        logger.info("Starting background demo batch execution for %s", batch_id)
        execute_full_demo_batch(db=db, batch_id=batch_id)
        logger.info("Completed background demo batch execution for %s", batch_id)
    except Exception as exc:
        logger.error("Background demo batch failed for %s: %s", batch_id, exc, exc_info=True)
    finally:
        db.close()


@router.post(
    "/run-batch",
    summary="Trigger full recovery demo batch",
    description=(
        "Kicks off an asynchronous 10-transaction demo run across all 5 failure categories, "
        "executes the recovery pipeline with real timing delays, and simulates webhook confirmations."
    ),
    status_code=status.HTTP_202_ACCEPTED,
)
def run_demo_batch(background_tasks: BackgroundTasks):
    batch_id = generate_batch_id()
    background_tasks.add_task(_run_demo_batch_worker, batch_id)
    return {
        "batch_id": batch_id,
        "status": "running",
        "total": len(DEMO_BATCH_CASES),
        "message": f"Demo batch {batch_id} initiated in background.",
    }


@router.get(
    "/status/{batch_id}",
    summary="Get demo batch execution status",
    description="Returns real-time execution progress, current active step, and timestamped log stream.",
)
def get_demo_status(batch_id: str, db: DbDep):
    return get_demo_batch_live_status(batch_id, db=db)
