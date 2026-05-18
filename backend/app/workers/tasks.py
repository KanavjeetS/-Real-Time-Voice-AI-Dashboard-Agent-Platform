"""Background task handlers (run via scripts/run_worker.py)."""
import structlog

from app.workers.queue import JobType

log = structlog.get_logger()


async def handle_job(job: dict) -> None:
    job_type = job.get("type")
    payload = job.get("payload") or {}
    log.info("worker.job_start", job_id=job.get("id"), type=job_type)

    if job_type == JobType.POST_CALL_SUMMARY.value:
        await _post_call_summary(payload)
    elif job_type == JobType.LEAD_SCORE_SYNC.value:
        await _lead_score_sync(payload)
    elif job_type == JobType.SLACK_ALERT.value:
        await _slack_alert(payload)
    elif job_type == JobType.CRM_SYNC.value:
        await _crm_sync(payload)
    else:
        log.warning("worker.unknown_job", type=job_type)


async def _post_call_summary(payload: dict) -> None:
    from app.services.crm import CRMService
    await CRMService.generate_and_store_summary(
        call_db_id=payload.get("call_db_id"),
        call_sid=payload.get("call_sid"),
        language=payload.get("language", "en"),
    )


async def _lead_score_sync(payload: dict) -> None:
    from app.services.crm import CRMService
    await CRMService.update_lead_score(
        call_db_id=payload.get("call_db_id"),
        lead_score=payload.get("lead_score", 0),
        intent=payload.get("intent"),
    )


async def _slack_alert(payload: dict) -> None:
    from app.services.crm import CRMService

    class _Session:
        phone_number = payload.get("phone", "")
        call_sid = payload.get("call_sid", "")
        detected_language = payload.get("language", "en")

    await CRMService.send_slack_alert(_Session(), payload.get("transcript", ""), payload.get("intent", ""))


async def _crm_sync(payload: dict) -> None:
    log.info("worker.crm_sync", call_sid=payload.get("call_sid"))
