from django.forms import ValidationError
from core.gql.gql_mutations import DeleteInputType
from core.gql.gql_mutations.base_mutation import (
    BaseDeleteMutation,
    BaseHistoryModelDeleteMutationMixin,
)
import graphene
from policyholder.apps import PolicyholderConfig
from policyholder.models import (
    ExceptionReason,
    PolicyHolder,
    PolicyHolderInsuree,
    PolicyHolderContributionPlan,
    PolicyHolderUser,
)
from policyholder.validation.permission_validation import PermissionValidation
from policyholder.erp_intigration import erp_delete_policyholder


class DeleteExceptionReasonMutation(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        id = graphene.Int(required=True)

    @classmethod
    def mutate(cls, root, info, id):
        print(f"deleteExceptionReasonMutation : input : {id}")

        try:

            obj = ExceptionReason.objects.filter(id=id).first()
            if not obj:
                raise ValidationError("ExceptionReason with this ID does not exist.")

            obj.delete()

            print(f"ExceptionReason deleted successfully: {id}")

            return cls(success=True, message="Mutation successful!")
        except Exception as e:
            print(f"Failed to delete exception reason: {e}")
            return cls(success=False, message=str(e))


class DeletePolicyHolderMutation(
    BaseHistoryModelDeleteMutationMixin, BaseDeleteMutation
):
    _mutation_class = "PolicyHolderMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolder

    class Input(DeleteInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(
            user, PolicyholderConfig.gql_mutation_delete_policyholder_perms
        )

        contributionPlan = PolicyHolderContributionPlan.objects.filter(
            policy_holder__id=data["uuid"], is_deleted=False
        ).first()

        if (
            contributionPlan is not None
            and contributionPlan.contribution_plan_bundle is not None
        ):
            cpId = contributionPlan.contribution_plan_bundle.id
            print(
                f"********************************** DELETE POLICIY HOLDER ERP BEGIN {cpId}"
            )
            erp_delete_policyholder(data["uuid"], cpId, user)
            print("********************************** DELETE POLICIY HOLDER ERP END")


class DeletePolicyHolderInsureeMutation(
    BaseHistoryModelDeleteMutationMixin, BaseDeleteMutation
):
    _mutation_class = "PolicyHolderInsureeMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderInsuree

    class Input(DeleteInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(
            user, PolicyholderConfig.gql_mutation_delete_policyholderinsuree_perms
        )


class DeletePolicyHolderContributionPlanMutation(
    BaseHistoryModelDeleteMutationMixin, BaseDeleteMutation
):
    _mutation_class = "PolicyHolderContributionPlanMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderContributionPlan

    class Input(DeleteInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(
            user,
            PolicyholderConfig.gql_mutation_delete_policyholdercontributionplan_perms,
        )


class DeletePolicyHolderUserMutation(
    BaseHistoryModelDeleteMutationMixin, BaseDeleteMutation
):
    _mutation_class = "PolicyHolderUserMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderUser

    class Input(DeleteInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        # @TODO enable permissions after finding what is the necessary permissions
        # PermissionValidation.validate_perms(user, PolicyholderConfig.gql_mutation_delete_policyholderuser_perms)
