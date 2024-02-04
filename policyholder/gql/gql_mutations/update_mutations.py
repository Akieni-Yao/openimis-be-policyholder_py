import graphene
from core.gql.gql_mutations.base_mutation import BaseMutation, BaseHistoryModelUpdateMutationMixin
from core.models import InteractiveUser
from policyholder.apps import PolicyholderConfig
from policyholder.models import PolicyHolder, PolicyHolderInsuree, PolicyHolderContributionPlan, PolicyHolderUser
from policyholder.gql.gql_mutations import PolicyHolderInsureeUpdateInputType, \
    PolicyHolderContributionPlanUpdateInputType, PolicyHolderUserUpdateInputType, PolicyHolderUpdateInputType
from policyholder.validation import PolicyHolderValidation
from policyholder.validation.permission_validation import PermissionValidation


class UpdatePolicyHolderMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "PolicyHolderMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolder

    class Input(PolicyHolderUpdateInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(user, PolicyholderConfig.gql_mutation_update_policyholder_perms)
        PolicyHolderValidation.validate_update(user, **data)


class UpdatePolicyHolderInsureeMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "PolicyHolderInsureeMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderInsuree

    class Input(PolicyHolderInsureeUpdateInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(user, PolicyholderConfig.gql_mutation_update_policyholderinsuree_perms)


class UpdatePolicyHolderContributionPlanMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "PolicyHolderContributionPlanMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderContributionPlan

    class Input(PolicyHolderContributionPlanUpdateInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(user, PolicyholderConfig.gql_mutation_update_policyholdercontributionplan_perms)


class UpdatePolicyHolderUserMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "PolicyHolderUserMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderUser

    @classmethod
    def _mutate(cls, user, **data):
        if "client_mutation_id" in data:
            data.pop('client_mutation_id')
        if "client_mutation_label" in data:
            data.pop('client_mutation_label')
        updated_object = cls._model.objects.filter(id=data['id']).first()
        [setattr(updated_object, key, data[key]) for key in data]
        cls.update_policy_holder_user(user=user, object_to_update=updated_object)

    @classmethod
    def update_policy_holder_user(cls, user, object_to_update):
        object_to_update.save(username=user.username)
        return object_to_update

    class Input(PolicyHolderUserUpdateInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(user, PolicyholderConfig.gql_mutation_update_policyholderuser_perms)


class UpdatePolicyHolderInsureeDesignation(graphene.Mutation):
    class Arguments:
        policy_holder_code = graphene.String(required=True)
        insuree_id = graphene.String(required=True)
        designation = graphene.String(required=True)
        flag = graphene.Boolean(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, policy_holder_code, insuree_id, designation, flag):
        try:
            username = info.context.user.username
            policy_holder = PolicyHolder.objects.get(code=policy_holder_code)
            record = PolicyHolderInsuree.objects.get(
                policy_holder__id=policy_holder.id,
                insuree__id=insuree_id,
                is_deleted=False
            )
            json_ext_data = record.json_ext
            if flag:
                json_ext_data['designation'] = designation
                record.json_ext = json_ext_data
            else:
                record.json_ext = json_ext_data
            record.save(username=username)
            success = True
            message = f"Successfully updated designation in json_ext with value '{designation}'."
        except PolicyHolderInsuree.DoesNotExist:
            success = False
            message = "Record not found."
        return UpdatePolicyHolderInsureeDesignation(success=success, message=message)
