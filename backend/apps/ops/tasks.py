import logging

from celery import shared_task

from .models import OpsReplayRun
from .replay import execute_replay_run
from .services import (
    cleanup_ops_data,
    evaluate_incidents,
    run_maintenance_scheduler,
    run_synthetic_probes,
    sweep_internal_failure_events,
)

logger = logging.getLogger(__name__)


@shared_task
def ops_run_synthetic_probes():
    result = run_synthetic_probes()
    logger.info("ops_run_synthetic_probes result=%s", result)
    return result


@shared_task
def ops_sweep_internal_failures():
    result = sweep_internal_failure_events()
    logger.info("ops_sweep_internal_failures result=%s", result)
    return result


@shared_task
def ops_evaluate_incidents():
    result = evaluate_incidents()
    logger.info("ops_evaluate_incidents result=%s", result)
    return result


@shared_task
def ops_run_maintenance_scheduler():
    result = run_maintenance_scheduler()
    logger.info("ops_run_maintenance_scheduler result=%s", result)
    return result


@shared_task
def ops_cleanup_data():
    result = cleanup_ops_data()
    logger.info("ops_cleanup_data result=%s", result)
    return result


@shared_task
def ops_execute_replay_run(run_id: str):
    run = OpsReplayRun.objects.filter(id=run_id).select_related("tenant", "actor").first()
    if not run:
        logger.warning("ops_execute_replay_run missing run id=%s", run_id)
        return {"ok": False, "error": "run_not_found"}
    run = execute_replay_run(run)
    return {"ok": True, "run_id": str(run.id), "status": run.status}
