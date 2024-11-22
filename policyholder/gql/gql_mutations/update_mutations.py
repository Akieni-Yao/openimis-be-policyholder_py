import logging

import graphene
from django.db.models import Q

from core.constants import POLICYHOLDER_UPDATE_NT
from core.gql.gql_mutations.base_mutation import BaseMutation, BaseHistoryModelUpdateMutationMixin
from core.models import InteractiveUser
from core.notification_service import create_camu_notification
from payment.models import Payment, PaymentPenaltyAndSanction
from policyholder.apps import PolicyholderConfig
from policyholder.models import PolicyHolder, PolicyHolderInsuree, PolicyHolderContributionPlan, PolicyHolderUser
from policyholder.gql.gql_mutations import PolicyHolderInsureeUpdateInputType, \
    PolicyHolderContributionPlanUpdateInputType, PolicyHolderUserUpdateInputType, PolicyHolderUpdateInputType, \
    PHApprovalInput
from policyholder.validation import PolicyHolderValidation
from policyholder.validation.permission_validation import PermissionValidation
from policyholder.constants import *
from policyholder.services import generate_camu_registration_number
from policyholder.email_templates import *
from insuree.dms_utils import rename_folder_dms_and_openkm
from django.core.mail import EmailMessage
from django.conf import settings
from django.utils import timezone
from policyholder.erp_intigration import erp_create_update_policyholder

logger = logging.getLogger(__name__)


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
        
        contributionPlan = PolicyHolderContributionPlan.objects.filter(
        policy_holder__id=data['id'], is_deleted=False).first()        
        
        if contributionPlan is not None and contributionPlan.contribution_plan_bundle is not None:
            cpId= contributionPlan.contribution_plan_bundle.id
            print(f"********************** UPDATE POLICIY HOLDER ERP BEGIN {cpId}")
            erp_create_update_policyholder(data['id'], cpId, user)
            print("*********************** UPDATE POLICIY HOLDER ERP END")



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
        PermissionValidation.validate_perms(user,
                                            PolicyholderConfig.gql_mutation_update_policyholdercontributionplan_perms)


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

    def mutate(self, info, input):
        try:
            username = info.context.user.username
            success = True
            message = None
            subject = None
            email_body = None

            ph_id = input.id
            request_number = input.request_number
            is_approved = input.is_approved
            is_rejected = input.is_rejected
            is_rework = input.is_rework

            ph_obj = PolicyHolder.objects.filter(id=ph_id, request_number=request_number).first()

            if ph_obj:
                if is_approved:
                    json_ext_dict = ph_obj.json_ext.get("jsonExt")
                    activity_code = json_ext_dict.get("activityCode")
                    generated_number = generate_camu_registration_number(activity_code)
                    ph_obj.code = generated_number
                    ph_obj.is_approved = True
                    ph_obj.status = PH_STATUS_APPROVED
                    ph_obj.save(username=username)
                    rename_folder_dms_and_openkm(ph_obj.request_number, generated_number)
                    message = "Policy Holder Request Successfully Approved."
                elif is_rejected:
                    ph_obj.is_rejected = True
                    ph_obj.status = PH_STATUS_REJECTED
                    ph_obj.rejected_reason = input.rejected_reason
                    # ph_obj.is_deleted = True
                    ph_obj.save(username=username)

                    phu_obj = PolicyHolderUser.objects.filter(policy_holder=ph_obj).first()
                    # phu_obj.is_deleted = True
                    phu_obj.save(username=username)

                    InteractiveUser.objects.filter(id=phu_obj.user.i_user.id).update(validity_to=timezone.now())

                    message = "Policy Holder Request Rejected."
                    subject = "CAMU, Your Policyholder Application request has been rejected."
                    email_body = policyholder_reject.format(
                        request_number=ph_obj.request_number,
                        contact_name=ph_obj.contact_name.get("contactName"),
                        rejection_reason=ph_obj.rejected_reason
                    )
                elif is_rework:
                    ph_obj.is_rework = True
                    ph_obj.is_submit = False
                    ph_obj.status = PH_STATUS_REWORK
                    ph_obj.rework_option = input.rework_option
                    ph_obj.rework_comment = input.rework_comment
                    ph_obj.save(username=username)
                    message = "Policy Holder Request Sent for Rework."
                    subject = "CAMU, Your Policyholder Application need some rework."
                    email_body = policyholder_rework.format(
                        request_number=ph_obj.request_number,
                        contact_name=ph_obj.contact_name.get("contactName"),
                        rework_comment=ph_obj.rework_comment
                    )
                else:
                    success = False
                    message = "Policy Holder request action is not valid."

                if ph_obj.email and subject and email_body:
                    email_message = EmailMessage(subject, email_body, settings.EMAIL_HOST_USER, [ph_obj.email])
                    email_message.send()
            try:
                create_camu_notification(POLICYHOLDER_UPDATE_NT, ph_obj)
                logger.info("Successfully created CAMU notification with POLICYHOLDER_CREATION_NT.")
            except Exception as e:
                logger.error(f"Failed to create CAMU notification: {e}")
            else:
                success = False
                message = "Policy Holder Request not found"

            return PHApprovalMutation(success=success, message=message)
        except Exception as e:
            success = False
            message = str(e)
            return PHApprovalMutation(success=success, message=message)


class UnlockPolicyHolderMutation(graphene.Mutation):
    class Arguments:
        policy_holder = graphene.String(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, policy_holder):
        # Fetch the policyholder
        try:
            policyholder = PolicyHolder.objects.get(id=policy_holder)
        except PolicyHolder.DoesNotExist:
            return UnlockPolicyHolderMutation(success=False, message="Policyholder does not exist.")

        # Query all payments associated with the policyholder's contracts
        payments = Payment.objects.filter(
            Q(contract__policy_holder__id=policy_holder)
        )

        # Check if any payments exist for the policyholder
        if not payments.exists():
            return UnlockPolicyHolderMutation(success=False, message="No payments found for this policyholder.")

        if payments.filter(status__ne=5).exists():  # Check if any payment is not fully paid
            return UnlockPolicyHolderMutation(success=False, message="Not all payments are fully paid.")

        # Check penalties of those payments: should have status 3 or 4, penalty_type 'Penalty', and is_approved=True
        penalties = PaymentPenaltyAndSanction.objects.filter(
            Q(payment__in=payments) &
            ~Q(status__in=[3, 4])
        )

        # If penalties exist that are unresolved or not approved
        if penalties.exists():
            if not penalties.filter(is_approved=True).exists():
                return UnlockPolicyHolderMutation(success=False, message="Penalties are not approved.")
            return UnlockPolicyHolderMutation(success=False, message="Penalties are not fully resolved.")

        # If all payments are fully paid, penalties are resolved and approved, unlock the policyholder
        policyholder.status = 'Approved'
        policyholder.save()

        return UnlockPolicyHolderMutation(success=True, message="Policyholder unlocked successfully.")