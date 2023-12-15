from django.urls import path

from policyholder import views

urlpatterns = [
    path("imports/<policy_holder_code>/policyholderinsurees", views.import_phi),
    path("export/<policy_holder_code>/policyholderinsurees", views.export_phi),
]
