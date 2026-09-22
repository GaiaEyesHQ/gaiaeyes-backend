"""Outbound-worker draft interface. No preparation or publication endpoint."""
import json

from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import get_pool
from app.db import earthscope_writer as queue
from app.security.earthscope_writer import require_draft_worker
from services.earthscope_writer_contract import DraftError, MAX_BODY_BYTES, WORKER_CONTRACT, require

router = APIRouter(prefix="/v1/earthscope/writer", tags=["earthscope-draft-worker"])


async def body(request):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        require(len(data) <= MAX_BODY_BYTES, "invalid_request")
    try:
        def pairs(items):
            value = {}
            for k, v in items:
                require(k not in value, "invalid_request")
                value[k] = v
            return value
        def invalid_constant(value):
            raise ValueError("invalid JSON number")
        value = json.loads(data, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise DraftError("invalid_request") from exc
    require(isinstance(value, dict), "invalid_request")
    return value


async def dispatch(request, worker_id, operation):
    try:
        value = await body(request)
        if operation == "claim":
            require(set(value) == {"schema_version", "worker_contract", "claim_request_id"}, "invalid_request")
            require(value["schema_version"] == "1.0" and value["worker_contract"] == WORKER_CONTRACT, "invalid_request")
        else:
            require(set(value) == {"outcome", "outcome_sha256"}, "invalid_request")
        pool = await get_pool()
        # Commit, including deliberate expiry, before sending an ack/error.
        async with pool.connection(timeout=5) as conn:
            await conn.execute("set local role gaia_earthscope_writer_backend")
            await conn.execute("set local statement_timeout='8s'")
            await conn.execute("set local lock_timeout='3s'")
            try:
                if operation == "claim":
                    result = await queue.claim_next(conn, worker_id, value["claim_request_id"])
                else:
                    result = await queue.return_outcome(conn, worker_id, value["outcome"], value["outcome_sha256"])
            except DraftError:
                await conn.commit()
                raise
            await conn.commit()
        return result
    except DraftError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code}) from None
    except Exception:
        raise HTTPException(status_code=503, detail={"code": "storage_unavailable"}) from None


@router.post("/claim-next")
async def claim_next(request: Request, worker_id=Depends(require_draft_worker)):
    return await dispatch(request, worker_id, "claim")


@router.post("/return-outcome")
async def return_outcome(request: Request, worker_id=Depends(require_draft_worker)):
    return await dispatch(request, worker_id, "return")
