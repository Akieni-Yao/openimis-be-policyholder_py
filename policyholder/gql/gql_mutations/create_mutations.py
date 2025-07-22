import json
import logging
import uuid

from graphene_django import DjangoObjectType

from core import ExtendedConnection
from core.constants import POLICYHOLDER_CREATION_NT
from core.gql.gql_mutations.base_mutation import (
    BaseMutation,
    BaseHistoryModelCreateMutationMixin,
)
from core.notification_service import create_camu_notification
from core.schema import OpenIMISMutation, update_or_create_user
from core.models import Role, User, InteractiveUser
from insuree.models import Family
from policyholder.apps import PolicyholderConfig
from policyholder.constants import *
from policyholder.dms_utils import (
    create_policyholder_openkmfolder,
    send_mail_to_policyholder_with_pdf,
    create_folder_for_policy_holder_exception,
    send_beneficiary_remove_notification,
    get_location_from_insuree,
    create_phi_for_cat_change,
    change_insuree_doc_status,
    validate_enrolment_type,
    manual_validate_enrolment_type,
)
from policyholder.gql import PolicyHolderExcptionType
from policyholder.gql.gql_mutations.input_types import ExceptionReasonInputType
from policyholder.models import (
    ExceptionReason,
    PolicyHolder,
    PolicyHolderInsuree,
    PolicyHolderContributionPlan,
    PolicyHolderUser,
    Insuree,
    PolicyHolderExcption,
    CategoryChange,
)
from policyholder.gql.gql_mutations import (
    PolicyHolderInputType,
    PolicyHolderInsureeInputType,
    PolicyHolderContributionPlanInputType,
    PolicyHolderUserInputType,
    PolicyHolderExcptionInput,
    PHPortalUserCreateInput,
)
from policyholder.portal_utils import (
    send_verification_email,
    send_verification_and_new_password_email,
)
from policyholder.validation import PolicyHolderValidation
from policyholder.validation.permission_validation import PermissionValidation
from django.core.exceptions import ValidationError
import datetime
import graphene
import pytz
import base64
from django.db import connection
from django.db.models import Q, F
from django.apps import apps

from policyholder.views import manuall_check_for_category_change_request
from workflow.constants import *
from policyholder.erp_intigration import erp_create_update_policyholder
from insuree.models import Insuree
from product.models import Product
from contribution_plan.models import (
    ContributionPlanBundle,
    ContributionPlanBundleDetails,
    ContributionPlan,
)
from contract.models import InsureeWaitingPeriod

logger = logging.getLogger(__name__)


def get_and_set_waiting_period_for_insuree(insuree_id, policyholder_id):
    try:
        logger.info("============get_and_set_waiting_period_for_insuree=============")

        policy_holder_contribution_plan = PolicyHolderContributionPlan.objects.filter(
            policy_holder_id=policyholder_id,
            is_deleted=False,
            date_valid_to__isnull=True,
        ).first()
        logger.info(
            f"policy_holder_contribution_plan: {policy_holder_contribution_plan}"
        )

        contribution_plan_bundle = (
            policy_holder_contribution_plan.contribution_plan_bundle
        )

        logger.info(f"contribution_plan_bundle: {contribution_plan_bundle}")

        contributionPlanBundleDetails = ContributionPlanBundleDetails.objects.filter(
            contribution_plan_bundle=contribution_plan_bundle
        ).first()

        logger.info(f"contributionPlanBundleDetails: {contributionPlanBundleDetails}")

        contribution_plan = ContributionPlan.objects.filter(
            id=contributionPlanBundleDetails.contribution_plan.id
        ).first()

        logger.info(f"contribution_plan: {contribution_plan}")

        # benefit_plan equal product

        product = Product.objects.filter(
            id=contribution_plan.benefit_plan.id, validity_to=None, legacy_id=None
        ).first()

        logger.info(f"product: {product}")
        logger.info(f"product.policy_waiting_period: {product.policy_waiting_period}")

        insuree = Insuree.objects.filter(id=insuree_id).first()

        logger.info(f"insuree: {insuree}")

        if policy_holder_contribution_plan:
            insuree_waiting_period = InsureeWaitingPeriod.objects.filter(
                insuree=insuree,
                policy_holder_contribution_plan=policy_holder_contribution_plan,
            ).first()
            if not insuree_waiting_period:
                InsureeWaitingPeriod.objects.create(
                    insuree=insuree,
                    policy_holder_contribution_plan=policy_holder_contribution_plan,
                    waiting_period=product.policy_waiting_period,
                    contribution_periodicity=contribution_plan.periodicity,
                )
    except Exception as e:
        logger.error(f"Failed to get waiting period: {e}")


class CreatePolicyHolderMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_class = "PolicyHolderMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolder

    class Input(PolicyHolderInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        # if PolicyHolderServices.check_unique_code_policy_holder(code=data['code']):
        #     raise ValidationError(_("mutation.ph_code_duplicated"))
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(
            user, PolicyholderConfig.gql_mutation_create_policyholder_perms
        )
        PolicyHolderValidation.validate_create(user, **data)

    @classmethod
    def _mutate(cls, user, **data):
        json_ext_dict = data["json_ext"]["jsonExt"]
        activitycode = json_ext_dict.get("activityCode")
        generated_number = cls.generate_camu_registration_number(activitycode)

        data["is_review"] = True
        data["is_submit"] = True
        data["is_approved"] = True
        data["status"] = PH_STATUS_APPROVED
        data["code"] = generated_number
        create_policyholder_openkmfolder(data)

        if "client_mutation_id" in data:
            client_mutation_id = data.pop("client_mutation_id")
        if "client_mutation_label" in data:
            data.pop("client_mutation_label")
        try:
            create_camu_notification(POLICYHOLDER_CREATION_NT, data)
            logger.info("Sent Notification.")
        except Exception as e:
            logger.error(f"Failed to call send notification: {e}")
        created_object = cls.create_object(user=user, object_data=data)
        # try:
        #     # if email having inside the policyholder then it is executed
        #     if isinstance(created_object, PolicyHolder):
        #         if created_object.email:
        #             send_mail_to_policyholder_with_pdf(created_object, 'registration_application')
        # except Exception as exc:
        #     logger.exception("failed to send message", str(exc))
        try:
            create_camu_notification(POLICYHOLDER_CREATION_NT, created_object)
            logger.info(
                "Successfully created CAMU notification with POLICYHOLDER_CREATION_NT."
            )
        except Exception as e:
            logger.error(f"Failed to create CAMU notification: {e}")
        model_class = apps.get_model(cls._mutation_module, cls._mutation_class)
        if (
            model_class
            and hasattr(model_class, "object_mutated")
            and client_mutation_id is not None
        ):
            model_class.object_mutated(
                user,
                client_mutation_id=client_mutation_id,
                **{cls._mutation_module: created_object},
            )

    @classmethod
    def generate_camu_registration_number(cls, code):
        congo_timezone = pytz.timezone("Africa/Kinshasa")
        # Get the current time in Congo Time
        congo_time = datetime.datetime.now(congo_timezone)
        series1 = "CAMU"  # Define the fixed components of the number
        series2 = str(code)  # You mentioned "construction" as the sector of activity
        series3 = congo_time.strftime("%H")  # Registration time (hour)
        series4 = congo_time.strftime("%m").zfill(
            2
        )  # Month of registration with leading zero
        series5 = congo_time.strftime("%d").zfill(
            2
        )  # Day of registration with leading zero
        series6 = congo_time.strftime("%y")  # Year of registration
        with connection.cursor() as cursor:
            cursor.execute("SELECT nextval('public.camu_code_seq')")
            sequence_value = cursor.fetchone()[0]
        series7 = str(sequence_value).zfill(3)  # Order of recording
        # Concatenate the series to generate the final number
        generated_number = (
            f"{series1}{series2}{series3}{series4}{series5}{series6}{series7}"
        )
        return generated_number


class CreatePolicyHolderInsureeMutation(
    BaseHistoryModelCreateMutationMixin, BaseMutation
):
    _mutation_class = "PolicyHolderInsureeMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderInsuree

    class Input(PolicyHolderInsureeInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        logger.info(f"-------------CreatePolicyHolderInsureeMutation : data : {data}")
        insuree_id = data.get("insuree_id")
        contribution_plan_bundle_id = data.get("contribution_plan_bundle_id")
        policyholder_id = data.get("policy_holder_id")
        is_insuree = PolicyHolderInsuree.objects.filter(
            policy_holder__id=policyholder_id,
            insuree__id=insuree_id,
            is_deleted=False,
            date_valid_to__isnull=True,
        ).first()
        insurees = Insuree.objects.filter(id=insuree_id).first()
        products = ContributionPlanBundle.objects.filter(
            id=contribution_plan_bundle_id, code="PSC5"
        ).first()

        if is_insuree:
            raise ValidationError(message="Already Exists")

        if products is None and insurees.age() < 18:
            raise ValidationError(
                message="A principal insuree should have minimum 18 years old"
            )

        if products is not None and insurees.age() < 16:
            raise ValidationError(message="Student should have minimum 16 years old")

        employer_number = data.get("employer_number", "")
        income = data.get("json_ext", {}).get("calculation_rule", {}).get("income")
        is_valid_enrolment = manual_validate_enrolment_type(insuree_id, policyholder_id)
        if not is_valid_enrolment:
            raise ValidationError(message="Enrolment Type - 'Students' !")
        manuall_check_for_category_change_request(
            user, insuree_id, policyholder_id, income, employer_number
        )
        # Get the waiting period for the insuree
        get_and_set_waiting_period_for_insuree(insuree_id, policyholder_id)

        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(
            user, PolicyholderConfig.gql_mutation_create_policyholderinsuree_perms
        )


class CreatePolicyHolderContributionPlanMutation(
    BaseHistoryModelCreateMutationMixin, BaseMutation
):
    _mutation_class = "PolicyHolderContributionPlanMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderContributionPlan

    class Input(PolicyHolderContributionPlanInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        print(f"===> CreatePolicyHolderContributionPlanMutation : data : {data}")
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(
            user,
            PolicyholderConfig.gql_mutation_create_policyholdercontributionplan_perms,
        )

    @classmethod
    def async_mutate(cls, user, **data):
        try:
            skipErpUpdate = data.pop("skip_erp_update", False)
            cls._validate_mutation(user, **data)
            mutation_result = cls._mutate(user, **data)
            logger.debug(
                f"===> CreatePolicyHolderContributionPlanMutation : data : {data}"
            )
            logger.debug(
                f"===> CreatePolicyHolderContributionPlanMutation : mutation_result : {mutation_result}"
            )
            try:
                if skipErpUpdate is False:
                    print("===================== create erp policyholder")
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


def add_core_user_portal_permission(ph_user):
    logger.info("Updating is_portal_user for user: %s", ph_user.user)
    core_user = User.objects.filter(id=ph_user.user.id).first()
    core_user.is_portal_user = True
    core_user.save()
    add_i_user_permission(core_user)
    logger.info("is_portal_user updated for user: %s", core_user)


def add_i_user_permission(core_user):
    i_user = InteractiveUser.objects.filter(id=core_user.i_user.id).first()
    logger.info("i_user user: %s", i_user)
    i_user.is_verified = True
    i_user.save()


class CreatePolicyHolderUserMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_class = "PolicyHolderUserMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderUser

    @classmethod
    def _mutate(cls, user, **data):
        client_mutation_id = data.get("client_mutation_id")
        if "client_mutation_id" in data:
            data.pop("client_mutation_id")
        if "client_mutation_label" in data:
            data.pop("client_mutation_label")
        ph_user = cls.create_policy_holder_user(user=user, object_data=data)
        logger.info("Successfully ph_user created.")
        if ph_user:
            add_core_user_portal_permission(ph_user)

    @classmethod
    def create_policy_holder_user(cls, user, object_data):
        obj = cls._model(**object_data)
        obj.save(username=user.username)

        # send email with password reset
        token = uuid.uuid4().hex[:8].upper()
        core_user = User.objects.filter(id=object_data.get("user_id")).first()
        i_user = InteractiveUser.objects.filter(id=core_user.i_user.id).first()
        i_user.password_reset_token = token
        i_user.save()

        send_verification_and_new_password_email(i_user, token, core_user.username)

        return obj

    class Input(PolicyHolderUserInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        # @TODO enable permissions after finding what is the necessary permissions
        # PermissionValidation.validate_perms(
        #     user, PolicyholderConfig.gql_mutation_create_policyholderuser_perms
        # )


class CreatePolicyHolderExcption(graphene.Mutation):
    policy_holder_excption = graphene.Field(PolicyHolderExcptionType)
    message = graphene.String()

    class Arguments:
        input_data = PolicyHolderExcptionInput(required=True)

    def mutate(self, info, input_data):
        try:
            user = info.context.user
            reason = ExceptionReason.objects.filter(
                id=input_data.pop("reason_id")
            ).first()
            print(f"CreatePolicyHolderExcption : reason : {reason}")
            if not reason:
                return CreatePolicyHolderExcption(
                    policy_holder_excption=None, errors=["Reason not found"]
                )
            policy_holder = PolicyHolder.objects.filter(
                id=input_data["policy_holder_id"]
            ).first()
            print(f"CreatePolicyHolderExcption : policy_holder : {policy_holder}")
            if not policy_holder:
                return CreatePolicyHolderExcption(
                    policy_holder_excption=None, errors=["Policy holder not found"]
                )

            phcp = PolicyHolderContributionPlan.objects.filter(
                policy_holder=policy_holder, is_deleted=False
            ).order_by("-date_created")
            print(f"CreatePolicyHolderExcption : phcp : {phcp}")
            
            if not phcp:
                return CreatePolicyHolderExcption(
                    policy_holder_excption=None,
                    message="PolicyHolder's contribution plan not found.",
                )
            # if phcp:
            #     periodicity = phcp[0].contribution_plan_bundle.periodicity
            #     if periodicity != 1:
            #         return CreatePolicyHolderExcption(
            #             policy_holder_excption=None,
            #             message="PolicyHolder's contribution plan periodicity should be 1.",
            #         )
            # else:
            #     return CreatePolicyHolderExcption(
            #         policy_holder_excption=None,
            #         message="PolicyHolder's contribution plan not found.",
            #     )
                
            print(f"CreatePolicyHolderExcption : policy_holder 2: {policy_holder}")

            month = None
            contract_id = None
            from payment.models import Payment

            ph_payment = Payment.objects.filter(
                Q(received_amount__lt=F("expected_amount"))
                | Q(received_amount__isnull=True),
                contract__policy_holder__id=policy_holder.id,
                contract__state=5,
                is_locked=False,
            ).order_by("-id")
            logging.info(f"CreatePolicyHolderExcption :  ph_payment : {ph_payment}")
            if ph_payment:
                contract_id = ph_payment[0].contract.id
                month = ph_payment[0].contract.date_valid_from.month
                month_dict = {
                    1: "January",
                    2: "February",
                    3: "March",
                    4: "April",
                    5: "May",
                    6: "June",
                    7: "July",
                    8: "August",
                    9: "September",
                    10: "October",
                    11: "November",
                    12: "December",
                }
                month = month_dict.get(month)
                logging.info(
                    f"CreatePolicyHolderExcption :  ph_payment : contract_id : {contract_id}"
                )
                logging.info(
                    f"CreatePolicyHolderExcption :  ph_payment : month : {month}"
                )
            else:
                return CreatePolicyHolderExcption(
                    policy_holder_excption=None,
                    message="Payment already done for all contracts.",
                )

            current_time = datetime.datetime.now()
            # today_date = current_time.date().strftime("%d-%m-%Y")
            today_date = current_time.strftime("%d%m%y%H%M%S")
            ph_exc_code = f"PE{policy_holder.code}{today_date}"
            policy_holder_excption = PolicyHolderExcption(
                code=ph_exc_code,
                policy_holder=policy_holder,
                status="PENDING",
                created_by=user.id,
                modified_by=user.id,
                created_time=current_time,
                modified_time=current_time,
                month=month,
                contract_id=contract_id,
                reason=reason,
                **input_data,
            )
            policy_holder_excption.save()
            create_folder_for_policy_holder_exception(user, policy_holder, ph_exc_code)
            logging.info(
                f"PolicyHolderExcption created successfully: {policy_holder_excption.id}"
            )
            return CreatePolicyHolderExcption(
                policy_holder_excption=policy_holder_excption, message=None
            )

        except Exception as e:
            logging.error(f"An error occurred: {str(e)}")
            error_message = f"An error occurred: {str(e)}"
            return CreatePolicyHolderExcption(
                policy_holder_excption=None, message=error_message
            )


class CategoryChangeInput(graphene.InputObjectType):
    id = graphene.Int(required=False)
    code = graphene.String(required=False)
    status = graphene.String(required=True)
    request_type = graphene.String(required=False)
    rejected_reason = graphene.String(required=False)


class CategoryChangeStatusChange(graphene.Mutation):
    class Arguments:
        input = graphene.Argument(CategoryChangeInput)

    success = graphene.Boolean()
    message = graphene.String()

    @classmethod
    def mutate(cls, root, info, input):
        cc_id = input.get("id")
        code = input.get("code")
        status = input.get("status")
        rejected_reason = input.get("rejected_reason")
        cc = None
        if code:
            cc = CategoryChange.objects.filter(code=code).first()
            logger.info(f"Category change request found by code: {code}")
        elif cc_id:
            cc = CategoryChange.objects.filter(id=cc_id).first()
            logger.info(f"Category change request found by ID: {cc_id}")
        if cc:
            cc.status = status
            insuree = cc.insuree
            logger.info(f"Updating category change request status to: {status}")
            if cc.status == CC_APPROVED:
                logger.info("Category change request status is approved")
                new_category = cc.new_category
                logger.info(f"new_category: {new_category}")
                family_json_data = {"enrolmentType": new_category}
                logger.info(f"json_data: {family_json_data}")
                if cc.request_type in ["INDIVIDUAL_REQ", "DEPENDENT_REQ"]:
                    logger.info("Processing individual or dependent request")
                    location = get_location_from_insuree(insuree)
                    old_insuree_obj_id = insuree.save_history()
                    logger.info(f"old_insuree_obj_id: {old_insuree_obj_id}")
                    new_family = Family.objects.create(
                        head_insuree=insuree,
                        location=location,
                        audit_user_id=insuree.audit_user_id,
                        status=insuree.status,
                        json_ext=family_json_data,
                    )
                    logger.info(f"new_family: {new_family}")
                    logger.info(f"new_family id: {new_family.id}")
                    insuree.family = new_family
                    insuree.head = True
                    insuree_status = insuree.status

                    if (
                        insuree_status == STATUS_PRE_REGISTERED
                        and not insuree.biometrics_status
                    ):
                        insuree_status = STATUS_WAITING_FOR_BIOMETRIC

                    if insuree_status == STATUS_WAITING_FOR_DOCUMENT:
                        insuree_status = STATUS_WAITING_FOR_APPROVAL

                    # insuree.document_status = True
                    # if insuree.biometrics_is_master:
                    #     insuree_status = STATUS_APPROVED
                    # elif not insuree.biometrics_status:
                    #     insuree_status = STATUS_WAITING_FOR_BIOMETRIC

                    insuree.status = insuree_status
                    logger.info(f"insuree_status: {insuree_status}")
                    insuree.json_ext["insureeEnrolmentType"] = new_category
                    insuree.save()
                    Family.objects.filter(id=new_family.id).update(
                        status=insuree_status
                    )
                    if cc.request_type == "DEPENDENT_REQ":
                        send_beneficiary_remove_notification(old_insuree_obj_id)
                elif cc.request_type == "SELF_HEAD_REQ":
                    logger.info("Processing self head request")
                    insuree.save_history()
                    insuree_status = insuree.status
                    insuree.document_status = True

                    if (
                        insuree_status == STATUS_PRE_REGISTERED
                        and not insuree.biometrics_status
                    ):
                        insuree_status = STATUS_WAITING_FOR_BIOMETRIC

                    if insuree_status == STATUS_WAITING_FOR_DOCUMENT:
                        insuree_status = STATUS_WAITING_FOR_APPROVAL

                    # elif not insuree.biometrics_status:
                    #     insuree_status = STATUS_WAITING_FOR_BIOMETRIC
                    insuree.status = insuree_status
                    logger.info(f"insuree_status: {insuree_status}")
                    insuree.json_ext["insureeEnrolmentType"] = new_category
                    insuree.save()
                    Family.objects.filter(id=insuree.family.id).update(
                        status=insuree_status, json_ext=family_json_data
                    )
            else:
                logger.info("Category change request status is not approved")
                if rejected_reason:
                    cc.rejected_reason = rejected_reason
            cc.save()
            logger.info("Category change request status updated")
            create_phi_for_cat_change(info.context.user, cc)
            return CategoryChangeStatusChange(
                success=True, message="Request status successfully updated!"
            )
        logger.warning("Category change request not found")
        return CategoryChangeStatusChange(success=False, message="Request not found!")


class CreatePHPortalUserMutation(graphene.Mutation):
    """
    Create a new policy holder portal user.
    """

    # _mutation_module = "core"
    # _mutation_class = "CreateUserMutation"
    success = graphene.Boolean()
    message = graphene.String()

    # class Input(PHPortalUserCreateInput):
    #     pass
    class Arguments:
        input = graphene.Argument(PHPortalUserCreateInput)

    @classmethod
    def mutate(cls, root, info, input):
        try:
            user = info.context.user
            # if type(user) is AnonymousUser or not user.id:
            #     raise ValidationError("mutation.authentication_required")
            if User.objects.filter(username=input["username"]).exists():
                raise ValidationError("User with this user name already exists.")
            # if not user.has_perms(CoreConfig.gql_mutation_create_users_perms):
            #     raise PermissionDenied("unauthorized")
            from core.utils import TimeUtils

            input["validity_from"] = TimeUtils.now()
            input["audit_user_id"] = -1  # user.id_for_audit
            ph_portal_user_admin_role = Role.objects.filter(name=PH_ADMIN_ROLE).first()
            if not ph_portal_user_admin_role:
                raise ValidationError("Policy Holder Admin Role not exists.")
            input["roles"] = ["{}".format(ph_portal_user_admin_role.id)]

            ph_trade_name = input.pop("trade_name")
            ph_json_ext = input.pop("json_ext")

            core_user = update_or_create_user(input, user)
            core_user.is_portal_user = True
            core_user.save()
            logger.info(f"CreatePHPortalUserMutation : core_user : {core_user}")

            ph_obj = PolicyHolder()
            ph_obj.trade_name = ph_trade_name
            ph_obj.json_ext = ph_json_ext
            ph_obj.form_ph_portal = True
            ph_obj.request_number = uuid.uuid4().hex[:8].upper()
            ph_obj.status = PH_STATUS_CREATED
            ph_obj.save(username=core_user.username)
            logger.info(f"CreatePHPortalUserMutation : ph_obj : {ph_obj}")
            create_policyholder_openkmfolder({"request_number": ph_obj.request_number})
            try:
                create_camu_notification(POLICYHOLDER_CREATION_NT, ph_obj)
                logger.info(
                    "Successfully created CAMU notification with POLICYHOLDER_CREATION_NT."
                )
            except Exception as e:
                logger.error(f"Failed to create CAMU notification: {e}")
            phu_obj = PolicyHolderUser()
            phu_obj.user = core_user
            phu_obj.policy_holder = ph_obj
            phu_obj.save(username=core_user.username)
            logger.info(f"CreatePHPortalUserMutation : phu_obj : {phu_obj}")

            send_verification_email(core_user.i_user)

            return CreatePHPortalUserMutation(success=True, message="Successful!")
        except Exception as exc:
            return CreatePHPortalUserMutation(success=False, message=str(exc))


class CreateExceptionReasonMutation(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        input = graphene.Argument(ExceptionReasonInputType, required=True)

    @classmethod
    def mutate(cls, root, info, input):
        print(f"CreateExceptionReasonMutation : input : {input}")

        try:
            scope = input.pop("scope")
            if scope not in ["POLICY_HOLDER", "INSUREE"]:
                raise ValidationError(
                    "Invalid scope provided. Must be 'POLICY_HOLDER' or 'INSUREE'."
                )
            obj = ExceptionReason.objects.create(
                reason=input.get("reason"),
                period=input.get("period"),
                scope=scope,
            )
            logger.info(f"ExceptionReason created successfully: {obj.id}")

            return cls(success=True, message="Mutation successful!")
        except Exception as e:
            logger.error(f"Failed to create exception reason: {e}")
            return cls(success=False, message=str(e))
