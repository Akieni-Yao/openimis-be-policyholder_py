import json
import logging

from graphene_django import DjangoObjectType

from core import ExtendedConnection
from core.gql.gql_mutations.base_mutation import BaseMutation, BaseHistoryModelCreateMutationMixin
from core.schema import OpenIMISMutation, update_or_create_user
from core.models import Role, User
from insuree.models import Family
from policyholder.apps import PolicyholderConfig
from policyholder.constants import *
from policyholder.dms_utils import create_policyholder_openkmfolder, send_mail_to_policyholder_with_pdf, \
    create_folder_for_policy_holder_exception, send_beneficiary_remove_notification, get_location_from_insuree, \
    create_phi_for_cat_change
from policyholder.gql import PolicyHolderExcptionType
from policyholder.models import PolicyHolder, PolicyHolderInsuree, PolicyHolderContributionPlan, PolicyHolderUser, \
    Insuree, PolicyHolderExcption, CategoryChange
from policyholder.gql.gql_mutations import PolicyHolderInputType, PolicyHolderInsureeInputType, \
    PolicyHolderContributionPlanInputType, PolicyHolderUserInputType, PolicyHolderExcptionInput, PHPortalUserCreateInput
from policyholder.portal_utils import send_verification_email
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

logger = logging.getLogger(__name__)


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
        PermissionValidation.validate_perms(user, PolicyholderConfig.gql_mutation_create_policyholder_perms)
        PolicyHolderValidation.validate_create(user, **data)

    @classmethod
    def _mutate(cls, user, **data):
        json_ext_dict = data["json_ext"]["jsonExt"]
        activitycode = json_ext_dict.get("activityCode")
        generated_number = cls.generate_camu_registration_number(activitycode)
        data["code"] = generated_number
        create_policyholder_openkmfolder(data)
        if "client_mutation_id" in data:
            client_mutation_id = data.pop('client_mutation_id')
        if "client_mutation_label" in data:
            data.pop('client_mutation_label')
        created_object = cls.create_object(user=user, object_data=data)
        # try:
        #     # if email having inside the policyholder then it is executed
        #     if isinstance(created_object, PolicyHolder):
        #         if created_object.email:
        #             send_mail_to_policyholder_with_pdf(created_object, 'registration_application')
        # except Exception as exc:
        #     logger.exception("failed to send message", str(exc))
        model_class = apps.get_model(cls._mutation_module, cls._mutation_class)
        if model_class and hasattr(model_class, "object_mutated") and client_mutation_id is not None:
            model_class.object_mutated(user, client_mutation_id=client_mutation_id,
                                       **{cls._mutation_module: created_object})

    @classmethod
    def generate_camu_registration_number(cls, code):
        congo_timezone = pytz.timezone('Africa/Kinshasa')
        # Get the current time in Congo Time
        congo_time = datetime.datetime.now(congo_timezone)
        series1 = "CAMU"  # Define the fixed components of the number
        series2 = str(code)  # You mentioned "construction" as the sector of activity
        series3 = congo_time.strftime("%H")  # Registration time (hour)
        series4 = congo_time.strftime("%m").zfill(2)  # Month of registration with leading zero
        series5 = congo_time.strftime("%d").zfill(2)  # Day of registration with leading zero
        series6 = congo_time.strftime("%y")  # Year of registration
        with connection.cursor() as cursor:
            cursor.execute("SELECT nextval('public.camu_code_seq')")
            sequence_value = cursor.fetchone()[0]
        series7 = str(sequence_value).zfill(3)  # Order of recording
        # Concatenate the series to generate the final number
        generated_number = f"{series1}{series2}{series3}{series4}{series5}{series6}{series7}"
        return generated_number


class CreatePolicyHolderInsureeMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_class = "PolicyHolderInsureeMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderInsuree

    class Input(PolicyHolderInsureeInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        insuree_id = data.get('insuree_id')
        policyholder_id = data.get('policy_holder_id')
        is_insuree = PolicyHolderInsuree.objects.filter(policy_holder__id=policyholder_id, insuree__id=insuree_id,
                                                        is_deleted=False).first()
        if is_insuree:
            raise ValidationError(message="Already Exists")
        employer_number = data.get('employer_number', '')
        income = data.get('json_ext', {}).get('calculation_rule', {}).get('income')
        is_cc_request = manuall_check_for_category_change_request(user, insuree_id, policyholder_id, income, employer_number)
        if is_cc_request:
            raise ValidationError(message="Change Request Created.")
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(user, PolicyholderConfig.gql_mutation_create_policyholderinsuree_perms)


class CreatePolicyHolderContributionPlanMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_class = "PolicyHolderContributionPlanMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderContributionPlan

    class Input(PolicyHolderContributionPlanInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(user,
                                            PolicyholderConfig.gql_mutation_create_policyholdercontributionplan_perms)


class CreatePolicyHolderUserMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_class = "PolicyHolderUserMutation"
    _mutation_module = "policyholder"
    _model = PolicyHolderUser

    @classmethod
    def _mutate(cls, user, **data):
        client_mutation_id = data.get("client_mutation_id")
        if "client_mutation_id" in data:
            data.pop('client_mutation_id')
        if "client_mutation_label" in data:
            data.pop('client_mutation_label')
        cls.create_policy_holder_user(user=user, object_data=data)

    @classmethod
    def create_policy_holder_user(cls, user, object_data):
        obj = cls._model(**object_data)
        obj.save(username=user.username)
        return obj

    class Input(PolicyHolderUserInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        PermissionValidation.validate_perms(user, PolicyholderConfig.gql_mutation_create_policyholderuser_perms)


class CreatePolicyHolderExcption(graphene.Mutation):
    policy_holder_excption = graphene.Field(PolicyHolderExcptionType)
    message = graphene.String()

    class Arguments:
        input_data = PolicyHolderExcptionInput(required=True)

    def mutate(self, info, input_data):
        try:
            user = info.context.user
            policy_holder = PolicyHolder.objects.filter(id=input_data['policy_holder_id']).first()
            if not policy_holder:
                return CreatePolicyHolderExcption(policy_holder_excption=None, errors=["Policy holder not found"])
            
            phcp = PolicyHolderContributionPlan.objects.filter(policy_holder=policy_holder, is_deleted=False).order_by('-date_created')
            if phcp:
                periodicity = phcp[0].contribution_plan_bundle.periodicity
                if periodicity != 1:
                    return CreatePolicyHolderExcption(
                        policy_holder_excption=None,
                        message="PolicyHolder's contribution plan periodicity should be 1."
                    )
            else:
                return CreatePolicyHolderExcption(
                        policy_holder_excption=None,
                        message="PolicyHolder's contribution plan not found."
                    )

            month = None
            contract_id = None
            from payment.models import Payment
            ph_payment = Payment.objects.filter(
                Q(received_amount__lt=F('expected_amount')) | Q(received_amount__isnull=True),
                contract__policy_holder__id=policy_holder.id, 
                contract__state=5, is_locked=False).order_by('-id')
            logging.info(f"CreatePolicyHolderExcption :  ph_payment : {ph_payment}")
            if ph_payment:
                contract_id = ph_payment[0].contract.id
                month = ph_payment[0].contract.date_valid_from.month
                month_dict = {1:'January',2:'February',3:'March',4:'April',5:'May',6:'June',7:'July',8:'August',9:'September',10:'October',11:'November',12:'December'}
                month = month_dict.get(month)
                logging.info(f"CreatePolicyHolderExcption :  ph_payment : contract_id : {contract_id}")
                logging.info(f"CreatePolicyHolderExcption :  ph_payment : month : {month}")
            else:
                return CreatePolicyHolderExcption(policy_holder_excption=None, message="Payment already done for all contracts.")

            current_time = datetime.datetime.now()
            today_date = current_time.date().strftime('%d-%m-%Y')
            ph_exc_code = f"{policy_holder.code}-({today_date})"
            policy_holder_excption = PolicyHolderExcption(
                code=ph_exc_code,
                policy_holder=policy_holder,
                status='PENDING',
                created_by=user.id,
                modified_by=user.id,
                created_time=current_time,
                modified_time=current_time,
                month=month,
                contract_id=contract_id,
                **input_data
            )
            policy_holder_excption.save()
            create_folder_for_policy_holder_exception(user, policy_holder, ph_exc_code)
            logging.info(f"PolicyHolderExcption created successfully: {policy_holder_excption.id}")
            return CreatePolicyHolderExcption(policy_holder_excption=policy_holder_excption, message=None)

        except Exception as e:
            logging.error(f"An error occurred: {str(e)}")
            error_message = f"An error occurred: {str(e)}"
            return CreatePolicyHolderExcption(policy_holder_excption=None, message=error_message)


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
            logger.info(f"Updating category change request status to: {status}")
            if cc.status == CC_APPROVED:
                logger.info("Category change request status is approved")
                insuree = cc.insuree
                new_category = cc.new_category
                logger.info(f"new_category: {new_category}")
                family_json_data = {"enrolmentType": new_category}
                logger.info(f"json_data: {family_json_data}")
                if cc.request_type in ['INDIVIDUAL_REQ', 'DEPENDENT_REQ']:
                    logger.info("Processing individual or dependent request")
                    location = get_location_from_insuree(insuree)
                    old_insuree_obj_id = insuree.save_history()
                    logger.info(f"old_insuree_obj_id: {old_insuree_obj_id}")
                    new_family = Family.objects.create(
                        head_insuree=insuree,
                        location=location,
                        audit_user_id=insuree.audit_user_id,
                        status=insuree.status,
                        json_ext=family_json_data
                    )
                    logger.info(f"new_family: {new_family}")
                    logger.info(f"new_family id: {new_family.id}")
                    insuree.family = new_family
                    insuree.head = True
                    insuree_status = STATUS_WAITING_FOR_BIOMETRIC
                    insuree.document_status = True
                    if insuree.biometrics_is_master:
                        insuree_status = STATUS_APPROVED
                    # elif not insuree.biometrics_status:
                    #     insuree_status = STATUS_WAITING_FOR_BIOMETRIC
                    insuree.status = insuree_status
                    logger.info(f"insuree_status: {insuree_status}")
                    insuree.json_ext['insureeEnrolmentType'] = new_category
                    insuree.save()
                    Family.objects.filter(id=new_family.id).update(status=insuree_status)
                    if cc.request_type == 'DEPENDENT_REQ':
                        send_beneficiary_remove_notification(old_insuree_obj_id)
                elif cc.request_type == 'SELF_HEAD_REQ':
                    logger.info("Processing self head request")
                    insuree.save_history()
                    insuree_status = STATUS_WAITING_FOR_BIOMETRIC
                    insuree.document_status = True
                    if insuree.biometrics_is_master:
                        insuree_status = STATUS_APPROVED
                    # elif not insuree.biometrics_status:
                    #     insuree_status = STATUS_WAITING_FOR_BIOMETRIC
                    insuree.status = insuree_status
                    logger.info(f"insuree_status: {insuree_status}")
                    insuree.json_ext['insureeEnrolmentType'] = new_category
                    insuree.save()
                    Family.objects.filter(id=insuree.family.id).update(status=insuree_status, json_ext=family_json_data)
            else:
                logger.info("Category change request status is not approved")
                if rejected_reason:
                    cc.rejected_reason = rejected_reason
            cc.save()
            logger.info("Category change request status updated")
            create_phi_for_cat_change(info.context.user, cc)
            return CategoryChangeStatusChange(
                success=True,
                message="Request status successfully updated!"
            )
        logger.warning("Category change request not found")
        return CategoryChangeStatusChange(
            success=False,
            message="Request not found!"
        )


class CreatePHPortalUserMutation(OpenIMISMutation):
    """
    Create a new policy holder portal user.
    """
    _mutation_module = "core"
    _mutation_class = "CreateUserMutation"

    class Input(PHPortalUserCreateInput, OpenIMISMutation.Input):
        pass

    @classmethod
    def async_mutate(cls, user, **data):
        try:
            # if type(user) is AnonymousUser or not user.id:
            #     raise ValidationError("mutation.authentication_required")
            if User.objects.filter(username=data['username']).exists():
                raise ValidationError("User with this user name already exists.")
            # if not user.has_perms(CoreConfig.gql_mutation_create_users_perms):
            #     raise PermissionDenied("unauthorized")
            from core.utils import TimeUtils
            data['validity_from'] = TimeUtils.now()
            data['audit_user_id'] = -1 #user.id_for_audit
            ph_portal_user_admin_role = Role.objects.filter(name=PH_ADMIN_ROLE).first()
            if not ph_portal_user_admin_role:
                raise ValidationError("Policy Holder Admin Role not exists.")
            data['roles'] = ["{}".format(ph_portal_user_admin_role.id)]
            
            ph_trade_name = data.pop("trade_name")
            ph_json_ext = data.pop("json_ext")
            
            core_user = update_or_create_user(data, user)
            # send_verification_email(core_user.i_user)
            return None
        except Exception as exc:
            return [
                {
                    'message': "core.mutation.failed_to_create_user",
                    'detail': str(exc)
                }]
