import random

from django.core.management.base import BaseCommand

from insuree.test_helpers import create_test_insuree

from policyholder.models import PolicyHolder, PolicyHolderInsuree

from policyholder.views import check_for_category_change_request

HEADER_INSUREE_ID = "insuree_id"

class Command(BaseCommand):
    help = "Commande pour détecter les incohérences de catégorie d'assuré et initier une demande de changement" 

    def handle(self, *args, **options):
        policy_holder_insurees = PolicyHolderInsuree.objects.filter(
            policy_holder__date_valid_to__isnull=True,
            is_deleted=False
        ).order_by('insuree', '-date_valid_from').distinct('insuree')
        for policy_holder_insuree in policy_holder_insurees:
            insuree = policy_holder_insuree.insuree
            cpb = policy_holder_insuree.contribution_plan_bundle
            if insuree and cpb:
                line = { HEADER_INSUREE_ID: HEADER_INSUREE_ID }
                check_for_category_change_request(
                    None,
                    { HEADER_INSUREE_ID: insuree.chf_id },
                    policy_holder_insuree.policy_holder,
                    cpb.name
                )
            
