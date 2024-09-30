from django.urls import path

from policyholder import views, erp_intigration

urlpatterns = [
    path("imports/<policy_holder_code>/policyholderinsurees", views.import_phi),
    path("export/<policy_holder_code>/policyholderinsurees", views.export_phi),
    path("export/notdeclaredpolicyholder", views.not_declared_policy_holder),
    path('not-declared-ph/', views.not_declared_ph_rest),
    path('verify-email/<uidb64>/<token>/<e_timestamp>/', views.verify_email, name='verify_email'),
    path('portal-reset/<uidb64>/<token>/<e_timestamp>/', views.portal_reset),
    path('deactivate-not-submitted-request/', views.deactivate_not_submitted_request),
    path('custom-policyholder-policies-expire', views.custom_policyholder_policies_expire),
    path("tipl/get-declaration-details/<policy_holder_code>", views.get_declaration_details),
    path("tipl/paid-contract-payment", views.paid_contract_payment),

    path('create-existing-policyholder-in-erp/', erp_intigration.create_existing_policyholder_in_erp),
    path('create-existing-fosa-in-erp/', erp_intigration.create_existing_fosa_in_erp),

]
