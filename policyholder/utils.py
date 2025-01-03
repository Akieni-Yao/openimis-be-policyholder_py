from celery import shared_task
from django.db.models import Q
import logging
from policyholder.models import PolicyHolder, PolicyHolderContributionPlan

logger = logging.getLogger(__name__)


class Utils:

    @staticmethod
    def get_policyholders_missing_erp():
        return PolicyHolder.objects.filter(
            Q(erp_partner_id__isnull=True) | Q(erp_partner_access_id__isnull=True),
            is_deleted=False
        )