from core.gql.gql_mutations import DeleteInputType
from core.gql.gql_mutations.base_mutation import BaseDeleteMutation, BaseHistoryModelDeleteMutationMixin
from policyholder.apps import PolicyholderConfig
from policyholder.models import PolicyHolder, PolicyHolderInsuree, PolicyHolderContributionPlan, PolicyHolderUser
from policyholder.validation.permission_validation import PermissionValidation
from policyholder.erp_intigration import erp_delete_policyholder


class DeletePolicyHolderMutation(BaseHistoryModelDeleteMutationMixin, BaseDeleteMutation):
    _mutation_class = "PolicyHolderMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolder

    class Input(DeleteInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(user, PolicyholderConfig.gql_mutation_delete_policyholder_perms)
        
        contributionPlan = PolicyHolderContributionPlan.objects.filter(
        policy_holder__id=data['uuid'], is_deleted=False).first()        
        
        if contributionPlan is not None and contributionPlan.contribution_plan_bundle is not None:
            cpId= contributionPlan.contribution_plan_bundle.id
            print(f"********************************** DELETE POLICIY HOLDER ERP BEGIN {cpId}")
            erp_delete_policyholder(data['uuid'], cpId, user)
            print("********************************** DELETE POLICIY HOLDER ERP END")


class DeletePolicyHolderInsureeMutation(BaseHistoryModelDeleteMutationMixin, BaseDeleteMutation):
    _mutation_class = "PolicyHolderInsureeMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderInsuree

    class Input(DeleteInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(user, PolicyholderConfig.gql_mutation_delete_policyholderinsuree_perms)


class DeletePolicyHolderContributionPlanMutation(BaseHistoryModelDeleteMutationMixin, BaseDeleteMutation):
    _mutation_class = "PolicyHolderContributionPlanMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderContributionPlan

    class Input(DeleteInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(user, PolicyholderConfig.gql_mutation_delete_policyholdercontributionplan_perms)


class DeletePolicyHolderUserMutation(BaseHistoryModelDeleteMutationMixin, BaseDeleteMutation):
    _mutation_class = "PolicyHolderUserMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderUser

    class Input(DeleteInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(user, PolicyholderConfig.gql_mutation_delete_policyholderuser_perms)
