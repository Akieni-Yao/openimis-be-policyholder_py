from datetime import datetime
import logging
import re

from django.forms import ValidationError

import graphene
from django.db.models import Q
import uuid

from dotenv import load_dotenv
import os

from core.constants import POLICYHOLDER_UPDATE_NT
from core.gql.gql_mutations.base_mutation import (
    BaseMutation,
    BaseHistoryModelUpdateMutationMixin,
)
from core.models import InteractiveUser
from core.notification_service import create_camu_notification
from payment.models import Payment, PaymentPenaltyAndSanction
from policyholder.apps import PolicyholderConfig
from policyholder.gql.gql_mutations.input_types import ExceptionReasonInputType
from policyholder.models import (
    ExceptionReason,
    PolicyHolder,
    PolicyHolderInsuree,
    PolicyHolderContributionPlan,
    PolicyHolderUser,
    PolicyHolderUserPending,
)
from policyholder.gql.gql_mutations import (
    PolicyHolderInsureeUpdateInputType,
    PolicyHolderContributionPlanUpdateInputType,
    PolicyHolderUserUpdateInputType,
    PolicyHolderUpdateInputType,
    PHApprovalInput,
)
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
from policyholder.portal_utils import (
    send_approved_or_rejected_email,
    new_forgot_password_email,
)

load_dotenv()

logger = logging.getLogger(__name__)

PORTAL_SUBSCRIBER_URL = os.getenv("PORTAL_SUBSCRIBER_URL", "")
PORTAL_FOSA_URL = os.getenv("PORTAL_FOSA_URL", "")
IMIS_URL = os.getenv("IMIS_URL", "")


class UpdateExceptionReasonMutation(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        input = graphene.Argument(ExceptionReasonInputType, required=True)

    @classmethod
    def mutate(cls, root, info, input):
        print(f"updateExceptionReasonMutation : input : {input}")

        try:
            scope = input.pop("scope")
            id = input.pop("id")
            if scope not in ["POLICY_HOLDER", "INSUREE"]:
                raise ValidationError(
                    "Invalid scope provided. Must be 'POLICY_HOLDER' or 'INSUREE'."
                )
            obj = ExceptionReason.objects.filter(id=id).first()
            if not obj:
                raise ValidationError("ExceptionReason with this ID does not exist.")

            obj.reason = input.get("reason")
            obj.period = input.get("period")
            obj.scope = scope
            obj.save()

            logger.info(f"ExceptionReason updated successfully: {obj.id}")

            return cls(success=True, message="Mutation successful!")
        except Exception as e:
            logger.error(f"Failed to create exception reason: {e}")
            return cls(success=False, message=str(e))


class UpdatePolicyHolderMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "PolicyHolderMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolder

    class Input(PolicyHolderUpdateInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)

        PermissionValidation.validate_perms(
            user, PolicyholderConfig.gql_mutation_update_policyholder_perms
        )

        PolicyHolderValidation.validate_update(user, **data)

        print("********************** UPDATE POLICY HOLDER VALIDATION")

        try:
            skip_erp_update = data.pop("skip_erp_update", False)

            print("********************** UPDATE POLICY HOLDER VALIDATION ERP")
            contributionPlan = PolicyHolderContributionPlan.objects.filter(
                policy_holder__id=data["id"], is_deleted=False
            ).first()

            if (
                contributionPlan is not None
                and contributionPlan.contribution_plan_bundle is not None
            ):
                cpId = contributionPlan.contribution_plan_bundle.id

                print("********************** UPDATE POLICY HOLDER VALIDATION ERP 2")

                if not skip_erp_update:
                    erp_create_update_policyholder(data["id"], cpId, user)
                else:
                    print(
                        "********************** UPDATE POLICY HOLDER VALIDATION ERP SKIPPED"
                    )

            print("********************** UPDATE POLICY HOLDER VALIDATION ERP SUCCESS")
        except Exception as e:
            print(f"********************** ERP UPDATE POLICIY HOLDER ERP ERROR {e}")


class UpdatePolicyHolderInsureeMutation(
    BaseHistoryModelUpdateMutationMixin, BaseMutation
):
    _mutation_class = "PolicyHolderInsureeMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderInsuree

    class Input(PolicyHolderInsureeUpdateInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(
            user, PolicyholderConfig.gql_mutation_update_policyholderinsuree_perms
        )


class UpdatePolicyHolderContributionPlanMutation(
    BaseHistoryModelUpdateMutationMixin, BaseMutation
):
    _mutation_class = "PolicyHolderContributionPlanMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderContributionPlan

    class Input(PolicyHolderContributionPlanUpdateInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(
            user,
            PolicyholderConfig.gql_mutation_update_policyholdercontributionplan_perms,
        )


class UpdatePolicyHolderUserMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "PolicyHolderUserMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderUser

    @classmethod
    def _mutate(cls, user, **data):
        if "client_mutation_id" in data:
            data.pop("client_mutation_id")
        if "client_mutation_label" in data:
            data.pop("client_mutation_label")
        updated_object = cls._model.objects.filter(id=data["id"]).first()
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
        PermissionValidation.validate_perms(
            user, PolicyholderConfig.gql_mutation_update_policyholderuser_perms
        )


class UpdatePolicyHolderInsureeDesignation(graphene.Mutation):
    class Arguments:
        policy_holder_code = graphene.String(required=True)
        insuree_id = graphene.String(required=True)
        designation = graphene.String(required=True)
        flag = graphene.Boolean(required=True)
        position_id = graphene.String(required=False)
        speciality_id = graphene.String(required=False)

    success = graphene.Boolean()
    message = graphene.String()

    def mutate(
        self,
        info,
        policy_holder_code,
        insuree_id,
        designation,
        flag,
        position_id=None,
        speciality_id=None,
    ):
        try:
            username = info.context.user.username
            policy_holder = PolicyHolder.objects.get(code=policy_holder_code)
            record = PolicyHolderInsuree.objects.get(
                policy_holder__id=policy_holder.id,
                insuree__id=insuree_id,
                is_deleted=False,
            )
            json_ext_data = record.json_ext
            if flag:
                json_ext_data["designation"] = designation
                json_ext_data["position_id"] = position_id
                json_ext_data["speciality_id"] = speciality_id

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
            user = info.context.user
            success = True
            message = None
            subject = None
            email_body = None

            ph_id = input.id
            request_number = input.request_number
            is_approved = input.is_approved
            is_rejected = input.is_rejected
            is_rework = input.is_rework

            ph_obj = PolicyHolder.objects.filter(
                id=ph_id, request_number=request_number
            ).first()

            if ph_obj:
                if is_approved:
                    json_ext_dict = ph_obj.json_ext.get("jsonExt")
                    activity_code = json_ext_dict.get("activityCode")
                    generated_number = generate_camu_registration_number(activity_code)
                    ph_obj.code = generated_number
                    ph_obj.is_approved = True
                    ph_obj.status = PH_STATUS_APPROVED

                    policyHolderUserPending = PolicyHolderUserPending.objects.filter(
                        policy_holder=ph_obj
                    ).first()

                    if policyHolderUserPending:
                        create_new_insuree(ph_obj, policyHolderUserPending.user, user)
                        policyHolderUserPending.delete()

                    ph_obj.save(username=username)

                    rename_folder_dms_and_openkm(
                        ph_obj.request_number, generated_number
                    )
                    message = "Policy Holder Request Successfully Approved."
                    email_body = f"Your Policy Holder Request {ph_obj.request_number} has been Successfully Approved."
                    subject = (
                        "CAMU, Your Policyholder Application request has been approved."
                    )

                    # ERP CREATE UPDATE POLICY HOLDER
                    print(
                        "********************** UPDATE POLICY HOLDER VALIDATION ERP 2"
                    )
                    contributionPlan = PolicyHolderContributionPlan.objects.filter(
                        policy_holder__id=ph_id, is_deleted=False
                    ).first()

                    if (
                        contributionPlan is not None
                        and contributionPlan.contribution_plan_bundle is not None
                    ):
                        cpId = contributionPlan.contribution_plan_bundle.id

                        print(
                            "********************** UPDATE POLICY HOLDER VALIDATION ERP 3"
                        )

                        erp_create_update_policyholder(ph_id, cpId, user)
                        print(
                            "********************** UPDATE POLICY HOLDER VALIDATION ERP 4"
                        )

                elif is_rejected:
                    ph_obj.is_rejected = True
                    ph_obj.status = PH_STATUS_REJECTED
                    ph_obj.rejected_reason = input.rejected_reason
                    # ph_obj.is_deleted = True
                    ph_obj.save(username=username)

                    # phu_obj = PolicyHolderUser.objects.filter(policy_holder=ph_obj).first()
                    # phu_obj.is_deleted = True
                    # phu_obj.save(username=username)
                    # InteractiveUser.objects.filter(id=phu_obj.user.i_user.id).update(validity_to=timezone.now())

                    message = "Policy Holder Request Rejected."
                    subject = (
                        "CAMU, Your Policyholder Application request has been rejected."
                    )
                    email_body = f"Your Policy Holder Request {ph_obj.request_number} has been Rejected. Reason: {ph_obj.rejected_reason}"
                elif is_rework:
                    ph_obj.is_rework = True
                    ph_obj.is_submit = False
                    ph_obj.status = PH_STATUS_REWORK
                    ph_obj.rework_option = input.rework_option
                    ph_obj.rework_comment = input.rework_comment
                    ph_obj.save(username=username)
                    message = "Policy Holder Request Sent for Rework."
                    subject = "CAMU, Your Policyholder Application need some rework."
                    email_body = f"Your Policy Holder Request {ph_obj.request_number} has been Sent for Rework. Reason: {ph_obj.rework_comment}"
                else:
                    success = False
                    message = "Policy Holder request action is not valid."

                if ph_obj.email and subject and email_body:
                    send_approved_or_rejected_email(
                        {
                            "last_name": ph_obj.contact_name.get("contactName"),
                            "email": ph_obj.email,
                        },
                        subject,
                        email_body,
                    )
                    # email_message = EmailMessage(subject, email_body, settings.EMAIL_HOST_USER, [ph_obj.email])
                    # email_message.send()
                    #

                try:
                    create_camu_notification(POLICYHOLDER_UPDATE_NT, ph_obj)
                    logger.info(
                        "Successfully created CAMU notification with POLICYHOLDER_CREATION_NT."
                    )
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


def create_new_insuree(policy_holder, user, infoUser):
    from contract.utils import map_enrolment_type_to_category
    from policyholder.views import generate_available_chf_id
    from insuree.models import Family, Insuree
    from insuree.dms_utils import create_openKm_folder_for_bulkupload
    from workflow.workflow_stage import insuree_add_to_workflow
    from insuree.abis_api import create_abis_insuree

    print(f"===> create_new_insuree: {policy_holder} {user.email} {infoUser.i_user_id}")

    i_user = InteractiveUser.objects.filter(email=user.email).first()
    
    audit_user_id = infoUser.i_user_id

    if not i_user:
        raise ValidationError("User not found.")

    ph_cpb = PolicyHolderContributionPlan.objects.filter(
        policy_holder=policy_holder, is_deleted=False
    ).first()
    cpb = ph_cpb.contribution_plan_bundle if ph_cpb else None
    enrolment_type = cpb.name if cpb else None

    family = None
    insuree_created = None
    village = policy_holder.locations
    dob = datetime.strptime("2007-03-03", "%Y-%m-%d")

    print(f"===> village: {village}")
    print(f"===> enrolment_type: {enrolment_type}")
    

    if village:
        family = Family.objects.create(
            head_insuree_id=1,  # dummy
            location=village,
            audit_user_id=audit_user_id,
            status="PRE_REGISTERED",
            address="",
            json_ext={"enrolmentType": map_enrolment_type_to_category(enrolment_type)},
        )

    print(f"===> family: {family}")

    if family:
        insuree_id = generate_available_chf_id(
            "M",
            village,
            dob,
            enrolment_type,
        )

        print(f"===> insuree_id: {insuree_id}")

        insuree_created = Insuree.objects.create(
            other_names=i_user.other_names,
            last_name=i_user.last_name,
            dob=dob,
            family=family,
            audit_user_id=audit_user_id,
            card_issued=False,
            chf_id=insuree_id,
            head=True,
            current_village=village,
            created_by=audit_user_id,
            modified_by=audit_user_id,
            marital="",
            email=i_user.email,
            phone=i_user.phone,
            json_ext={
                "insureeEnrolmentType": map_enrolment_type_to_category(enrolment_type),
            },
        )
        chf_id = insuree_id

        if not insuree_created:
            raise ValidationError("Insuree not created.")

        print(f"===> insuree_created: {insuree_created}")

        family = Family.objects.filter(id=family.id).first()
        family.head_insuree_id = insuree_created.id
        family.save()

        try:
            create_openKm_folder_for_bulkupload(infoUser, insuree_created)
        except Exception as e:
            logger.error(f"insuree bulk upload error for dms: {e}")

        try:
            insuree_add_to_workflow(
                infoUser, insuree_created.id, "INSUREE_ENROLLMENT", "Pre_Register"
            )
            create_abis_insuree(infoUser, insuree_created)

        except Exception as e:
            logger.error(f"insuree bulk upload error for abis or workflow : {e}")

        phi = PolicyHolderInsuree(
            insuree=insuree_created,
            policy_holder=policy_holder,
            contribution_plan_bundle=cpb,
            json_ext={},
            employer_number=None,
        )
        phi.save(username=infoUser.username)
        
        i_user.insuree = insuree_created
        i_user.save()

    print(f"===> created insuree: {chf_id}")


# @TODO not used anymore, the current field has been moved to payment module
# class UnlockPolicyHolderMutation(graphene.Mutation):
#     class Arguments:
#         policy_holder = graphene.String(required=True)
#         check_status = graphene.Boolean(required=False)

#     success = graphene.Boolean()
#     message = graphene.String()

#     def mutate(self, info, policy_holder, check_status=False):
#         try:
#             policyholder = PolicyHolder.objects.get(id=policy_holder)
#         except PolicyHolder.DoesNotExist:
#             return UnlockPolicyHolderMutation(
#                 success=False, message="Policyholder does not exist."
#             )

#         payments_with_penalties = (
#             Payment.objects.filter(
#                 contract__policy_holder=policy_holder,
#                 payments_penalty__isnull=False,  # Ensures there are penalties
#             )
#             .distinct()
#             .order_by("contract__date_valid_from")
#             # [:3]
#             # .order_by("-payment_date")[:3]
#             # status=Payment.STATUS_APPROVED,
#         )

#         if payments_with_penalties.count() == 0:
#             return UnlockPolicyHolderMutation(
#                 success=False, message="No penalties found for this policyholder."
#             )

#         all_payments_approved = True
#         all_penalities_approved_or_canceled_or_installment = True

#         for payment in payments_with_penalties:
#             if payment.status != Payment.STATUS_APPROVED:
#                 all_payments_approved = False

#             for penality in payment.payments_penalty.all():
#                 # check if payment is oustanding then check if there are similar to pick up the last one with the highest status
#                 if penality.status == PaymentPenaltyAndSanction.PENALTY_OUTSTANDING:
#                     payment_penalty_and_sanction = (
#                         PaymentPenaltyAndSanction.objects.filter(
#                             amount=penality.amount,
#                             date_valid_from=penality.date_valid_from,
#                             payment=payment,
#                             payment__contract__policy_holder=policy_holder,
#                         )
#                         .order_by("-status")
#                         .first()
#                     )

#                     print(
#                         f"=============== payment_penalty_and_sanction {payment_penalty_and_sanction.id} {payment_penalty_and_sanction.status}"
#                     )

#                     if payment_penalty_and_sanction:
#                         penality = payment_penalty_and_sanction

#                 if penality.status not in [
#                     PaymentPenaltyAndSanction.PENALTY_PAID,
#                     PaymentPenaltyAndSanction.PENALTY_APPROVED,
#                     PaymentPenaltyAndSanction.PENALTY_CANCELED,
#                     PaymentPenaltyAndSanction.INSTALLMENT_AGREEMENT_PENDING,
#                     PaymentPenaltyAndSanction.INSTALLMENT_APPROVED,
#                 ]:
#                     all_penalities_approved_or_canceled_or_installment = False

#         if (
#             all_payments_approved is False
#             or all_penalities_approved_or_canceled_or_installment is False
#         ):
#             return UnlockPolicyHolderMutation(
#                 success=False,
#                 message="Policyholder can not be unlocked. There are payments or penalities that are not approved.",
#             )

#         if check_status:
#             return UnlockPolicyHolderMutation(
#                 success=True, message="Policyholder can be unlocked."
#             )

#         username = info.context.user.username

#         policyholder.status = "Approved"
#         policyholder.save(username=username)

#         return UnlockPolicyHolderMutation(
#             success=True, message="Policyholder unlocked successfully."
#         )

# def old_mutate(self, info, policy_holder, check_status=False):
#     # Fetch the policyholder
#     try:
#         policyholder = PolicyHolder.objects.get(id=policy_holder)
#     except PolicyHolder.DoesNotExist:
#         return UnlockPolicyHolderMutation(
#             success=False, message="Policyholder does not exist."
#         )

#     # Query all payments associated with the policyholder's contracts
#     payments = Payment.objects.filter(Q(contract__policy_holder__id=policy_holder))

#     # Check if any payments exist for the policyholder
#     if not payments.exists():
#         return UnlockPolicyHolderMutation(
#             success=False, message="No payments found for this policyholder."
#         )

#     if payments.filter(~Q(status=1) & ~Q(status=5)).exists():
#         return UnlockPolicyHolderMutation(
#             success=False, message="Not all payments are fully paid."
#         )

#     # Check penalties of those payments: should have status 3 or 4, penalty_type 'Penalty', and is_approved=True
#     penalties = PaymentPenaltyAndSanction.objects.filter(
#         Q(payment__in=payments)
#         & ~Q(
#             status__in=[
#                 PaymentPenaltyAndSanction.PENALTY_APPROVED,
#                 PaymentPenaltyAndSanction.PENALTY_CANCELED,
#                 PaymentPenaltyAndSanction.INSTALLMENT_APPROVED,
#                 PaymentPenaltyAndSanction.INSTALLMENT_AGREEMENT_PENDING,
#             ]
#         )
#     )

#     # If penalties exist that are unresolved or not approved
#     if penalties.exists():
#         if not penalties.filter(is_approved=True).exists():
#             return UnlockPolicyHolderMutation(
#                 success=False, message="Penalties are not approved."
#             )
#         return UnlockPolicyHolderMutation(
#             success=False, message="Penalties are not fully resolved."
#         )

#     if check_status:
#         return UnlockPolicyHolderMutation(
#             success=True, message="Policyholder can be unlocked."
#         )

#     username = info.context.user.username

#     # If all payments are fully paid, penalties are resolved and approved, unlock the policyholder
#     policyholder.status = "Approved"
#     policyholder.save(username=username)

#     return UnlockPolicyHolderMutation(
#         success=True, message="Policyholder unlocked successfully."
#     )


class VerifyUserAndUpdatePasswordMutation(graphene.Mutation):
    class Arguments:
        user_id = graphene.String(required=True)
        token = graphene.String(required=True)
        password = graphene.String(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, user_id, token, password):
        try:
            i_user = InteractiveUser.objects.filter(
                uuid=user_id, password_reset_token=token
            ).first()

            if not i_user:
                print("===> user token expired")
                return VerifyUserAndUpdatePasswordMutation(
                    success=False, message="Invalid user or token"
                )

            print(f"========> VerifyUserAndUpdatePasswordMutation : i_user : {i_user}")
            i_user.is_verified = True
            i_user.set_password(password)
            i_user.password_reset_token = None
            i_user.save()
            print(f"========> VerifyUserAndUpdatePasswordMutation : i_user : {i_user}")

            return VerifyUserAndUpdatePasswordMutation(
                success=True, message="User verified and password updated successfully"
            )

        except Exception as e:
            return VerifyUserAndUpdatePasswordMutation(success=False, message=str(e))


class NewPasswordRequestMutation(graphene.Mutation):
    class Arguments:
        email = graphene.String(required=True)
        from_what_env = graphene.String(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, email, from_what_env):
        try:
            i_user = InteractiveUser.objects.filter(email=email).first()

            if not i_user:
                return NewPasswordRequestMutation(
                    success=False, message="Invalid email"
                )

            i_user.is_verified = True
            i_user.password_reset_token = uuid.uuid4().hex[:16].upper()
            i_user.save()

            verification_url = ""
            if from_what_env == "subscriber":
                verification_url = f"{PORTAL_SUBSCRIBER_URL}/portal/verify-user-and-update-password?token={i_user.password_reset_token}&user_id={i_user.uuid}&username={i_user.username}"
            elif from_what_env == "fosa":
                verification_url = f"{PORTAL_FOSA_URL}/fosa/verify-user-and-update-password?token={i_user.password_reset_token}&user_id={i_user.uuid}&username={i_user.username}"
            elif from_what_env == "imis":
                verification_url = f"{IMIS_URL}/front/verify-user-and-update-password?token={i_user.password_reset_token}&user_id={i_user.uuid}&username={i_user.username}"

            new_forgot_password_email(i_user, verification_url)

            return NewPasswordRequestMutation(
                success=True, message="Email sent successfully"
            )

        except Exception as e:
            return NewPasswordRequestMutation(success=False, message=str(e))
