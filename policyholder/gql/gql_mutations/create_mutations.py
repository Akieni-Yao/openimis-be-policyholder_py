import logging

from graphene_django import DjangoObjectType

from core import ExtendedConnection
from core.gql.gql_mutations.base_mutation import BaseMutation, BaseHistoryModelCreateMutationMixin
from policyholder.apps import PolicyholderConfig
from policyholder.dms_utils import create_policyholder_openkmfolder, send_mail_to_policyholder_with_pdf, \
    create_folder_for_policy_holder_exception
from policyholder.gql import PolicyHolderExcptionType
from policyholder.models import PolicyHolder, PolicyHolderInsuree, PolicyHolderContributionPlan, PolicyHolderUser, \
    Insuree, PolicyHolderExcption
from policyholder.gql.gql_mutations import PolicyHolderInputType, PolicyHolderInsureeInputType, \
    PolicyHolderContributionPlanInputType, PolicyHolderUserInputType, PolicyHolderExcptionInput
from policyholder.validation import PolicyHolderValidation
from policyholder.validation.permission_validation import PermissionValidation
from django.core.exceptions import ValidationError
import datetime
import graphene
import pytz
import base64
from django.db import connection
from django.apps import apps

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
            phcp = PolicyHolderContributionPlan.objects.filter(policy_holder=policy_holder, is_deleted=False).first()
            if phcp:
                periodicity = phcp.contribution_plan_bundle.periodicity
                if periodicity != 1:
                    return CreatePolicyHolderExcption(
                        policy_holder_excption=None,
                        message="PolicyHolder's contribution plan periodicity should be 1"
                    )

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
