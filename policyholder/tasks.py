from celery import shared_task
import logging
from policyholder.models import PolicyHolder, PolicyHolderContributionPlan
from policyholder.erp_intigration import erp_create_update_policyholder
from core.models import User
from policyholder.utils import Utils

logger = logging.getLogger(__name__)


@shared_task
def sync_policyholders_to_erp():
    user = User.objects.get(username="System")

    policyholders = Utils.get_policyholders_missing_erp()
    logger.info(f"Found {policyholders.count()} policyholders to sync.")

    for ph in policyholders:
        try:
            phcp = PolicyHolderContributionPlan.objects.filter(
                policy_holder=ph, is_deleted=False
            ).first()

            if not phcp:
                logger.warning(f"No Contribution Plan found for PolicyHolder ID: {ph.id}")
                continue
            result = erp_create_update_policyholder(ph.id, phcp.contribution_plan_bundle.id, user)

            if not result:
                logger.error(f"Failed to process PolicyHolder ID: {ph.id}. Continuing...")
        except Exception as e:
            logger.exception(f"Error processing PolicyHolder ID: {ph.id}. Skipping...")

    logger.info("Sync process completed.")