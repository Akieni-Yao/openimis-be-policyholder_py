from core.gql.gql_mutations import DeleteInputType
from core.gql.gql_mutations.base_mutation import BaseDeleteMutation, BaseHistoryModelDeleteMutationMixin
from policyholder.apps import PolicyholderConfig
from policyholder.models import PolicyHolder, PolicyHolderInsuree, PolicyHolderContributionPlan, PolicyHolderUser, PolicyHolderExcption
from policyholder.validation.permission_validation import PermissionValidation
import graphene
from core.schema import OpenIMISMutation


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

class DeletePolicyHolderExcptionMutation(OpenIMISMutation):
    _mutation_class = "PolicyHolderExcptionMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderExcption

    # class Input(DeleteInputType):
    #     pass
    success = graphene.Boolean()
    message = graphene.String()

    class Input(OpenIMISMutation.Input):
        id = graphene.List(graphene.String,required=True)

    @classmethod
    def async_mutate(cls, user, **data):
        errors = []
        for policy_holder_exception_id in data["id"]:
            print("policy_holder_exception_id:",policy_holder_exception_id)
            policy_holder_exception = PolicyHolderExcption.objects \
                .filter(id=policy_holder_exception_id) \
                .first()
            if policy_holder_exception is None:
                errors.append({
                    'title': policy_holder_exception_id,
                    'list': [{'message': _("policyholder.mutation.failed_to_delete_policy_holder_exception") % {'id': policy_holder_exception_id}}]
                })
                continue
            try:
                policy_holder_exception.delete()
            except Exception as exc:
                errors.append({
                    'title': policy_holder_exception_id,
                    'list': [{'message': _("policyholder.mutation.failed_to_delete_policy_holder_exception"), 'detail': str(exc)}]
                })
        if len(errors) == 1:
            errors = errors[0]['list']
        return errors   