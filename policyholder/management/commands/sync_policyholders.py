from django.core.management.base import BaseCommand
from policyholder import tasks

class Command(BaseCommand):
    help = "Synchronize policyholders to ERP"

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting policyholders synchronization...")
        tasks.sync_policyholders_to_erp.delay()
        self.stdout.write("Policyholders synchronization has been started.")
