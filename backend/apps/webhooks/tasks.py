# apps/webhooks/tasks.py
"""
Celery tasks for async webhook delivery.
"""

import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=10,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
)
def deliver_webhook(self, delivery_id: str):
    """
    Deliver a single webhook.
    
    Uses Celery's built-in retry mechanism for failures.
    """
    from .models import WebhookDelivery
    from .services import execute_delivery
    
    try:
        delivery = WebhookDelivery.objects.select_related('endpoint').get(id=delivery_id)
    except WebhookDelivery.DoesNotExist:
        logger.error(f"Webhook delivery not found: {delivery_id}")
        return
    
    if delivery.status == 'success':
        logger.info(f"Webhook already delivered: {delivery_id}")
        return
    
    if not delivery.endpoint.is_active:
        logger.info(f"Webhook endpoint disabled, skipping: {delivery_id}")
        delivery.status = 'failed'
        delivery.error_message = 'Endpoint disabled'
        delivery.save()
        return
    
    success = execute_delivery(delivery)
    
    if not success and delivery.status == 'retrying':
        # Let Celery handle the retry
        raise self.retry(countdown=delivery.next_retry_at.timestamp() - timezone.now().timestamp())


@shared_task
def retry_failed_webhooks():
    """
    Retry webhooks that are scheduled for retry.
    
    Run this periodically (e.g., every minute) to process retries.
    """
    from .models import WebhookDelivery
    
    pending_retries = WebhookDelivery.objects.filter(
        status='retrying',
        next_retry_at__lte=timezone.now(),
    ).select_related('endpoint')[:100]  # Process in batches
    
    count = 0
    for delivery in pending_retries:
        if delivery.endpoint.is_active:
            deliver_webhook.delay(str(delivery.id))
            count += 1
    
    if count > 0:
        logger.info(f"Queued {count} webhook retries")
    
    return count


@shared_task
def cleanup_old_deliveries(days: int = 30):
    """
    Clean up old webhook delivery records.
    
    Keeps delivery records for the specified number of days.
    """
    from .models import WebhookDelivery
    
    cutoff = timezone.now() - timezone.timedelta(days=days)
    
    deleted, _ = WebhookDelivery.objects.filter(
        created_at__lt=cutoff,
        status__in=['success', 'failed'],
    ).delete()
    
    logger.info(f"Cleaned up {deleted} old webhook deliveries")
    return deleted
