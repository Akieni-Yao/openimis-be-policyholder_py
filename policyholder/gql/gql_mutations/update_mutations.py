import graphene
from core.gql.gql_mutations.base_mutation import BaseMutation, BaseHistoryModelUpdateMutationMixin
from core.models import InteractiveUser
from policyholder.apps import PolicyholderConfig
from policyholder.models import PolicyHolder, PolicyHolderInsuree, PolicyHolderContributionPlan, PolicyHolderUser
from policyholder.gql.gql_mutations import PolicyHolderInsureeUpdateInputType, \
    PolicyHolderContributionPlanUpdateInputType, PolicyHolderUserUpdateInputType, PolicyHolderUpdateInputType, PHApprovalInput
from policyholder.validation import PolicyHolderValidation
from policyholder.validation.permission_validation import PermissionValidation
from policyholder.constants import *


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


class PHApprovalMutation(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    
    class Arguments:
        input = graphene.Argument(PHApprovalInput)

    def mutate(self, info, **kwargs):
        try:
            success = True
            message = None
            
            ph_id = kwargs.get("id")
            request_number = kwargs.get("request_number")
            is_approved = kwargs.get("is_approved")
            is_rejected = kwargs.get("is_rejected")
            is_rework = kwargs.get("is_rework")
            
            ph_obj = PolicyHolder.objects.filter(id=ph_id, request_number=request_number).first()
            
            if is_approved and ph_obj:
                # TODO : Generate camu code of policy holder
                # ph_obj.code = "code"
                ph_obj.is_approved = True
                ph_obj.status = PH_STATUS_APPROVED
                ph_obj.save()
                message = "Policy Holder Request Successfully Approved."
            elif is_rejected and ph_obj:
                ph_obj.is_rejected = True
                ph_obj.rejected_reason = kwargs.get("rejected_reason")
                ph_obj.save()
                message = "Policy Holder Request Rejected."
                # TODO : Send rejection email
            elif is_rework and ph_obj:
                ph_obj.is_rework = True
                ph_obj.rework_option = kwargs.get("rework_option")
                ph_obj.rework_comment = kwargs.get("rework_comment")
                ph_obj.save()
                message = "Policy Holder Request Sent for Rework."
                # TODO : Send rework email
            elif ph_obj:
                success = False
                message = "Policy Holder request action is not valid."
            else:
                success = False
                message = "Policy Holder Request not found"
            return PHApprovalMutation(success=success, message=message)
        except Exception as e:
            success = False
            message = e
            return PHApprovalMutation(success=success, message=message)
