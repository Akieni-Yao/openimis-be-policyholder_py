from django.apps import AppConfig

MODULE_NAME = "policyholder"

DEFAULT_CFG = {
    "gql_query_policyholder_perms": ["150101"],
    "gql_query_policyholder_admins_perms": [],
    "gql_query_policyholderinsuree_perms": ["150201"],
    "gql_query_policyholderinsuree_admins_perms": [],
    "gql_query_policyholderuser_perms": ["150301"],
    "gql_query_policyholderuser_admins_perms": [],
    "gql_query_policyholdercontributionplanbundle_perms": ["150401"],
    "gql_query_policyholdercontributionplanbundle_admins_perms": [],
    "gql_mutation_create_policyholder_perms": ["150102"],
    "gql_mutation_update_policyholder_perms": ["150103"],
    "gql_mutation_delete_policyholder_perms": ["150104"],
    "gql_mutation_create_policyholderinsuree_perms": ["150202"],
    "gql_mutation_update_policyholderinsuree_perms": ["150203"],
    "gql_mutation_delete_policyholderinsuree_perms": ["150204"],
    "gql_mutation_replace_policyholderinsuree_perms": ["150206"],
    "gql_mutation_create_policyholderuser_perms": ["150302"],
    "gql_mutation_update_policyholderuser_perms": ["150303"],
    "gql_mutation_delete_policyholderuser_perms": ["150304"],
    "gql_mutation_replace_policyholderuser_perms": ["150306"],
    "gql_mutation_create_policyholdercontributionplan_perms": ["150402"],
    "gql_mutation_update_policyholdercontributionplan_perms": ["150403"],
    "gql_mutation_delete_policyholdercontributionplan_perms": ["150404"],
    "gql_mutation_replace_policyholdercontributionplan_perms": ["150406"],
    # OFS-260: Support the policyholder portal perms on Policyholder
    "gql_query_policyholder_portal_perms": ["154001"],
    "gql_query_policyholderinsuree_portal_perms": ["154101"],
    "gql_query_policyholdercontributionplanbundle_portal_perms": ["154601"],
    "gql_query_policyholderuser_portal_perms": ["154401"],
    "gql_query_payment_portal_perms": ["154501"],
    "gql_query_insuree_policy_portal_perms": ["154901"],
    "gql_mutation_create_policyholderinsuree_portal_perms": ["154102"],
    "gql_mutation_update_policyholderinsuree_portal_perms": ["154103"],
    "gql_mutation_delete_policyholderinsuree_portal_perms": ["154104"],
    "gql_mutation_replace_policyholderinsuree_portal_perms": ["154106"],
    "gql_mutation_create_policyholderuser_portal_perms": ["154402"],
    "gql_mutation_update_policyholderuser_portal_perms": ["154403"],
    "gql_mutation_delete_policyholderuser_portal_perms": ["154404"],
    "gql_mutation_replace_policyholderuser_portal_perms": ["154406"],
    "policyholder_legal_form": [
        {
            "code": "1",
            "display": "Personal Company",
        },
        {
            "code": "2",
            "display": "Limited Risk Company",
        },
        {
            "code": "3",
            "display": "Association",
        },
        {
            "code": "4",
            "display": "Government",
        },
        {
            "code": "5",
            "display": "Union",
        },
    ],
    "policyholder_activity": [
        {
            "code": "1",
            "display": "Retail",
        },
        {
            "code": "2",
            "display": "Industry",
        },
        {
            "code": "3",
            "display": "Building",
        },
        {
            "code": "4",
            "display": "Sailing",
        },
        {
            "code": "5",
            "display": "Services",
        },
    ]
}


class PolicyholderConfig(AppConfig):
    name = MODULE_NAME

    gql_query_policyholder_perms = []
    gql_query_policyholder_admins_perms = []
    gql_query_policyholderinsuree_perms = []
    gql_query_policyholderinsuree_admins_perms = []
    gql_query_policyholderuser_perms = []
    gql_query_policyholderuser_admins_perms = []
    gql_query_policyholdercontributionplanbundle_perms = []
    gql_query_policyholdercontributionplanbundle_admins_perms = []
    gql_mutation_create_policyholder_perms = []
    gql_mutation_update_policyholder_perms = []
    gql_mutation_delete_policyholder_perms = []
    gql_mutation_create_policyholderinsuree_perms = []
    gql_mutation_update_policyholderinsuree_perms = []
    gql_mutation_delete_policyholderinsuree_perms = []
    gql_mutation_replace_policyholderinsuree_perms = []
    gql_mutation_create_policyholderuser_perms = []
    gql_mutation_update_policyholderuser_perms = []
    gql_mutation_delete_policyholderuser_perms = []
    gql_mutation_replace_policyholderuser_perms = []
    gql_mutation_create_policyholdercontributionplan_perms = []
    gql_mutation_update_policyholdercontributionplan_perms = []
    gql_mutation_delete_policyholdercontributionplan_perms = []
    gql_mutation_replace_policyholdercontributionplan_perms = []
    # OFS-260: Support the policyholder portal perms on Policyholder
    gql_query_policyholder_portal_perms = []
    gql_query_policyholderinsuree_portal_perms = []
    gql_query_policyholdercontributionplanbundle_portal_perms = []
    gql_query_policyholderuser_portal_perms = []
    gql_query_payment_portal_perms = []
    gql_query_insuree_policy_portal_perms = []
    gql_mutation_create_policyholderinsuree_portal_perms = []
    gql_mutation_update_policyholderinsuree_portal_perms = []
    gql_mutation_delete_policyholderinsuree_portal_perms = []
    gql_mutation_replace_policyholderinsuree_portal_perms = []
    gql_mutation_create_policyholderuser_portal_perms = []
    gql_mutation_update_policyholderuser_portal_perms = []
    gql_mutation_delete_policyholderuser_portal_perms = []
    gql_mutation_replace_policyholderuser_portal_perms = []

    policyholder_legal_form = []
    policyholder_activity = []

    def _configure_permissions(self, cfg):
        PolicyholderConfig.gql_query_policyholder_perms = cfg[
            "gql_query_policyholder_perms"]
        PolicyholderConfig.gql_query_policyholder_admins_perms = cfg[
            "gql_query_policyholder_admins_perms"]
        PolicyholderConfig.gql_query_policyholderinsuree_perms = cfg[
            "gql_query_policyholderinsuree_perms"]
        PolicyholderConfig.gql_query_policyholderinsuree_admins_perms = cfg[
            "gql_query_policyholderinsuree_admins_perms"]
        PolicyholderConfig.gql_query_policyholderuser_perms = cfg[
            "gql_query_policyholderuser_perms"]
        PolicyholderConfig.gql_query_policyholderuser_admins_perms = cfg[
            "gql_query_policyholderuser_admins_perms"]
        PolicyholderConfig.gql_query_policyholdercontributionplanbundle_perms = cfg[
            "gql_query_policyholdercontributionplanbundle_perms"]
        PolicyholderConfig.gql_query_policyholdercontributionplanbundle_admins_perms = cfg[
            "gql_query_policyholdercontributionplanbundle_admins_perms"]
        PolicyholderConfig.gql_mutation_create_policyholder_perms = cfg[
            "gql_mutation_create_policyholder_perms"]
        PolicyholderConfig.gql_mutation_update_policyholder_perms = cfg[
            "gql_mutation_update_policyholder_perms"]
        PolicyholderConfig.gql_mutation_delete_policyholder_perms = cfg[
            "gql_mutation_delete_policyholder_perms"]
        PolicyholderConfig.gql_mutation_create_policyholderinsuree_perms = cfg[
            "gql_mutation_create_policyholderinsuree_perms"]
        PolicyholderConfig.gql_mutation_update_policyholderinsuree_perms = cfg[
            "gql_mutation_update_policyholderinsuree_perms"]
        PolicyholderConfig.gql_mutation_delete_policyholderinsuree_perms = cfg[
            "gql_mutation_delete_policyholderinsuree_perms"]
        PolicyholderConfig.gql_mutation_replace_policyholderinsuree_perms = cfg[
            "gql_mutation_replace_policyholderinsuree_perms"]
        PolicyholderConfig.gql_mutation_create_policyholderuser_perms = cfg[
            "gql_mutation_create_policyholderuser_perms"]
        PolicyholderConfig.gql_mutation_update_policyholderuser_perms = cfg[
            "gql_mutation_update_policyholderuser_perms"]
        PolicyholderConfig.gql_mutation_delete_policyholderuser_perms = cfg[
            "gql_mutation_delete_policyholderuser_perms"]
        PolicyholderConfig.gql_mutation_replace_policyholderuser_perms = cfg[
            "gql_mutation_replace_policyholderuser_perms"]
        PolicyholderConfig.gql_mutation_create_policyholdercontributionplan_perms = cfg[
            "gql_mutation_create_policyholdercontributionplan_perms"]
        PolicyholderConfig.gql_mutation_update_policyholdercontributionplan_perms = cfg[
            "gql_mutation_update_policyholdercontributionplan_perms"]
        PolicyholderConfig.gql_mutation_delete_policyholdercontributionplan_perms = cfg[
            "gql_mutation_delete_policyholdercontributionplan_perms"]
        PolicyholderConfig.gql_mutation_replace_policyholdercontributionplan_perms = cfg[
            "gql_mutation_replace_policyholdercontributionplan_perms"]
        # OFS-260: Support the policyholder portal perms on Policyholder
        PolicyholderConfig.gql_query_policyholder_portal_perms = cfg[
            "gql_query_policyholder_portal_perms"]
        PolicyholderConfig.gql_query_policyholderinsuree_portal_perms = cfg[
            "gql_query_policyholderinsuree_portal_perms"]
        PolicyholderConfig.gql_query_policyholdercontributionplanbundle_portal_perms = cfg[
            "gql_query_policyholdercontributionplanbundle_portal_perms"]
        PolicyholderConfig.gql_query_policyholderuser_portal_perms = cfg[
            "gql_query_policyholderuser_portal_perms"]
        PolicyholderConfig.gql_query_payment_portal_perms = cfg[
            "gql_query_payment_portal_perms"]
        PolicyholderConfig.gql_query_insuree_policy_portal_perms = cfg[
            "gql_query_insuree_policy_portal_perms"]
        PolicyholderConfig.gql_mutation_create_policyholderinsuree_portal_perms = cfg[
            "gql_mutation_create_policyholderinsuree_portal_perms"]
        PolicyholderConfig.gql_mutation_update_policyholderinsuree_portal_perms = cfg[
            "gql_mutation_update_policyholderinsuree_portal_perms"]
        PolicyholderConfig.gql_mutation_delete_policyholderinsuree_portal_perms = cfg[
            "gql_mutation_delete_policyholderinsuree_portal_perms"]
        PolicyholderConfig.gql_mutation_replace_policyholderinsuree_portal_perms = cfg[
            "gql_mutation_replace_policyholderinsuree_portal_perms"]
        PolicyholderConfig.gql_mutation_create_policyholderuser_portal_perms = cfg[
            "gql_mutation_create_policyholderuser_portal_perms"]
        PolicyholderConfig.gql_mutation_update_policyholderuser_portal_perms = cfg[
            "gql_mutation_update_policyholderuser_portal_perms"]
        PolicyholderConfig.gql_mutation_delete_policyholderuser_portal_perms = cfg[
            "gql_mutation_delete_policyholderuser_portal_perms"]
        PolicyholderConfig.gql_mutation_replace_policyholderuser_portal_perms = cfg[
            "gql_mutation_replace_policyholderuser_portal_perms"]

    def _configure_coding(self, cfg):
        PolicyholderConfig.policyholder_legal_form = cfg["policyholder_legal_form"]
        PolicyholderConfig.policyholder_activity = cfg["policyholder_activity"]

    def ready(self):
        from core.models import ModuleConfiguration
        cfg = ModuleConfiguration.get_or_default(MODULE_NAME, DEFAULT_CFG)
        self._configure_permissions(cfg)
        self._configure_coding(cfg)
