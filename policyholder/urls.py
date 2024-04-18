from django.urls import path

from policyholder import views

urlpatterns = [
    path("imports/<policy_holder_code>/policyholderinsurees", views.import_phi),
    path("export/<policy_holder_code>/policyholderinsurees", views.export_phi),
    path("export/notdeclaredpolicyholder", views.not_declared_policy_holder),
    path('not-declared-ph/', views.not_declared_ph_rest),
    path('verify-email/<uidb64>/<token>/', views.verify_email, name='verify_email'),
]
