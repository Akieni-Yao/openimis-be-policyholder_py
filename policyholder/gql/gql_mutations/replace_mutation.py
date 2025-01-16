import logging

from policyholder.apps import PolicyholderConfig
from policyholder.gql.gql_mutations import (
    PolicyHolderInsureeReplaceInputType,
    PolicyHolderContributionPlanReplaceInputType,
    PolicyHolderUserReplaceInputType,
)
from core.gql.gql_mutations.base_mutation import (
    BaseReplaceMutation,
    BaseHistoryModelReplaceMutationMixin,
)
from core.models import InteractiveUser
from policyholder.models import (
    PolicyHolder,
    PolicyHolderInsuree,
    PolicyHolderContributionPlan,
    PolicyHolderUser,
)
from policyholder.validation.permission_validation import PermissionValidation
from policyholder.erp_intigration import erp_create_update_policyholder

logger = logging.getLogger(__name__)


class ReplacePolicyHolderInsureeMutation(
    BaseHistoryModelReplaceMutationMixin, BaseReplaceMutation
):
    _mutation_class = "PolicyHolderInsureeMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderInsuree

    class Input(PolicyHolderInsureeReplaceInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(
            user, PolicyholderConfig.gql_mutation_replace_policyholderinsuree_perms
        )


class ReplacePolicyHolderContributionPlanMutation(
    BaseHistoryModelReplaceMutationMixin, BaseReplaceMutation
):
    _mutation_class = "PolicyHolderContributionPlanMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderContributionPlan

    class Input(PolicyHolderContributionPlanReplaceInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(
            user,
            PolicyholderConfig.gql_mutation_replace_policyholdercontributionplan_perms,
        )

    @classmethod
    def async_mutate(cls, user, **data):
        try:
            skipErpUpdate = data.pop("skip_erp_update", False)
            cls._validate_mutation(user, **data)
            mutation_result = cls._mutate(user, **data)
            logger.debug(
                f"===> ReplacePolicyHolderContributionPlanMutation : data : {data}"
            )
            logger.debug(
                f"===> ReplacePolicyHolderContributionPlanMutation : mutation_result : {mutation_result}"
            )
            try:
                if skipErpUpdate is False:
                    print("===================== replace erp policyholder")
                    erp_create_update_policyholder(
                        data["policy_holder_id"],
                        data["contribution_plan_bundle_id"],
                        user,
                    )
                    logger.info("ERP policyholder update/create was successful.")
                else:
                    logger.info(
                        "======================= ERP policyholder update/create was skipped."
                    )
            except Exception as e:
                logger.error(f"Failed to update/create ERP policyholder: {e}")
            return mutation_result
        except Exception as exc:
            return [
                {
                    "message": "Failed to process {} mutation".format(
                        cls._mutation_class
                    ),
                    "detail": str(exc),
                }
            ]


class ReplacePolicyHolderUserMutation(
    BaseHistoryModelReplaceMutationMixin, BaseReplaceMutation
):
    _mutation_class = "PolicyHolderUserMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderUser

    @classmethod
    def _mutate(cls, user, **data):
        if "client_mutation_id" in data:
            data.pop("client_mutation_id")
        if "client_mutation_label" in data:
            data.pop("client_mutation_label")
        object_to_replace = cls._model.objects.filter(id=data["uuid"]).first()
        if object_to_replace is None:
            cls._object_not_exist_exception(data["uuid"])
        else:
            object_to_replace.replace_object(data=data, username=user.username)

    class Input(PolicyHolderUserReplaceInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(
            user, PolicyholderConfig.gql_mutation_replace_policyholderuser_perms
        )
