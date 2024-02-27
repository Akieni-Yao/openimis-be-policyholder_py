from core.gql.gql_mutations import DeleteInputType
from core.gql.gql_mutations.base_mutation import BaseDeleteMutation, BaseHistoryModelDeleteMutationMixin
from policyholder.apps import PolicyholderConfig
from policyholder.models import PolicyHolder, PolicyHolderInsuree, PolicyHolderContributionPlan, PolicyHolderUser, PolicyHolderExcption
from policyholder.validation.permission_validation import PermissionValidation
import graphene
from core.schema import OpenIMISMutation
from policyholder.gql.gql_mutations import DeletePolicyHolderExcptionInputType

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


class DeletePolicyHolderExcptionMutation(graphene.Mutation):
    class Arguments:
        input_data = DeletePolicyHolderExcptionInputType(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    @classmethod
    def mutate(cls, root, info, input_data):
        policy_holder_exception_id = input_data.get('id')
        try:
            # Fetch the existing PolicyHolderExcption instance
            policy_holder_exception = PolicyHolderExcption.objects.get(id=policy_holder_exception_id)
            # Delete the instance
            policy_holder_exception.delete()
            return cls(success=True, message="Deleted successfully")

        except PolicyHolderExcption.DoesNotExist:
            return cls(success=False, message="PolicyHolderExcption not found.")

        except Exception as e:
            return cls(success=False, message=str(e))

