
import json
import logging
import pytz
import datetime

from django.core.serializers.json import DjangoJSONEncoder
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.contrib.auth.models import AnonymousUser
from django.core import serializers
from django.forms.models import model_to_dict
from django.http import JsonResponse

from core.notification_service import base64_encode
from policyholder.apps import PolicyholderConfig
from policyholder.models import PolicyHolder as PolicyHolderModel, PolicyHolderUser as PolicyHolderUserModel, \
    PolicyHolderContributionPlan as PolicyHolderContributionPlanModel, PolicyHolderInsuree as PolicyHolderInsureeModel
from policyholder.validation import PolicyHolderValidation
from policyholder.constants import *
from policy.models import Policy
from insuree.models import Insuree, InsureePolicy, Family
from payment.models import PaymentDetail, Payment
from contract.models import ContractDetails, ContractContributionPlanDetails, Contract
from django.db import connection
from policyholder.erp_intigration import erp_create_update_policyholder

logger = logging.getLogger("openimis." + __name__)


def activate_policy_of_insuree(ccpds):
    logger.debug("====  activate_policy_of_insuree  ====  start  ====")
    from core import datetime, datetimedelta
    if ccpds:
        logger.debug(f"====  activate_policy_of_insuree  ====  ccpds  ====  {ccpds}")
        for ccpd in ccpds:
            logger.debug(f"====  activate_policy_of_insuree  ====  ccpd  ====  {ccpd}")
            insuree = ccpd.contract_details.insuree
            pi = InsureePolicy.objects.create(
                **{
                    "insuree": insuree,
                    "policy": ccpd.policy,
                    "enrollment_date": ccpd.date_valid_from,
                    "start_date": ccpd.date_valid_from,
                    "effective_date": ccpd.date_valid_from,
                    "expiry_date": ccpd.date_valid_to + datetimedelta(
                        ccpd.contribution_plan.get_contribution_length()
                    ),
                    "audit_user_id": -1,
                }
            )
            logger.debug(f"====  activate_policy_of_insuree  ====  Policy.STATUS_ACTIVE  ====  {Policy.STATUS_ACTIVE}")
            ccpd.policy.status = Policy.STATUS_ACTIVE
            ccpd.policy.save()
            logger.debug(f"====  activate_policy_of_insuree  ====  ccpd.policy  ====  {ccpd.policy}")
            logger.debug(f"====  activate_policy_of_insuree  ====  ccpd.policy.status  ====  {ccpd.policy.status}")
    logger.debug("====  activate_policy_of_insuree  ====  end  ====")
    return True


def check_payment_done_by_policyholder(insuree_id):
    logger.debug("====  check_payment_done_by_policyholder  ====  start  ====")
    insuree = Insuree.objects.filter(id=insuree_id).first()
    # if insuree.is_payment_done and not insuree.is_rights and insuree.document_status and insuree.biometrics_is_master:
    # insuree_policies = PolicyHolderInsureeModel.objects.filter(insuree_id=insuree.id).all()
    # for inpo in insuree_policies:
    if insuree.head:
        logger.debug(f"====  check_payment_done_by_policyholder  ====  insuree.head  ====  {insuree.head}")
        insuree_policies = PolicyHolderInsureeModel.objects.filter(insuree_id=insuree.id, is_deleted=False).first()
        if insuree_policies:
            if insuree_policies.is_payment_done_by_policy_holder and insuree_policies.is_rights_enable_for_insuree:
                return True
            elif insuree_policies.is_payment_done_by_policy_holder:
                contribution_plan_bundle_ids = []
                # for ip in insuree_policies:
                if insuree_policies.contribution_plan_bundle.is_deleted == False:
                    contribution_plan_bundle_ids.append(insuree_policies.contribution_plan_bundle.id)
                logger.debug(
                    f"====  check_payment_done_by_policyholder  ====  contribution_plan_bundle_ids  ====  {contribution_plan_bundle_ids}")

                contract_details = None
                contract_details_ids = []
                if len(contribution_plan_bundle_ids) > 0:
                    contract_details = ContractDetails.objects.filter(
                        contribution_plan_bundle__id__in=contribution_plan_bundle_ids, insuree_id=insuree_id,
                        is_deleted=False).all()
                    if contract_details:
                        for cd in contract_details:
                            contract_details_ids.append(cd.uuid)
                logger.debug(
                    f"====  check_payment_done_by_policyholder  ====  contract_details_ids  ====  {contract_details_ids}")

                contract_contribution_plan_details = None
                premium_ids = []
                if len(contract_details_ids) > 0:
                    contract_contribution_plan_details = ContractContributionPlanDetails.objects.filter(
                        contract_details__id__in=contract_details_ids, is_deleted=False).all()
                    if contract_contribution_plan_details:
                        for ccpd in contract_contribution_plan_details:
                            if ccpd.contribution.legacy_id == None:
                                premium_ids.append(ccpd.contribution.id)
                logger.debug(
                    f"====  check_payment_done_by_policyholder  ====  contract_contribution_plan_details  ====  {contract_contribution_plan_details}")
                logger.debug(f"====  check_payment_done_by_policyholder  ====  premium_ids  ====  {premium_ids}")

                if contract_contribution_plan_details and insuree_policies.is_payment_done_by_policy_holder:
                    logger.debug(
                        f"====  check_payment_done_by_policyholder  ====  insuree_policies.is_payment_done_by_policy_holder  ====  {insuree_policies.is_payment_done_by_policy_holder}")
                    if insuree.status == "APPROVED" and insuree.document_status and insuree.biometrics_is_master:
                        logger.debug(
                            f"====  check_payment_done_by_policyholder  ====  insuree.status  ====  {insuree.status}")
                        logger.debug(
                            f"====  check_payment_done_by_policyholder  ====  insuree.document_status  ====  {insuree.document_status}")
                        logger.debug(
                            f"====  check_payment_done_by_policyholder  ====  insuree.biometrics_is_master  ====  {insuree.biometrics_is_master}")
                        PolicyHolderInsureeModel.objects.filter(id=insuree_policies.id).update(
                            is_rights_enable_for_insuree=True)
                        Insuree.objects.filter(id=insuree_id).update(status="ACTIVE")
                        if insuree.head:
                            Family.objects.filter(id=insuree.family.id).update(status="ACTIVE")
                            family_members = Insuree.objects.filter(family_id=insuree.family.id, legacy_id=None).all()
                            for member in family_members:
                                if member.status == 'APPROVED':
                                    Insuree.objects.filter(id=member.id).update(status="ACTIVE")
                        activate_policy_of_insuree(contract_contribution_plan_details)
                        insuree = Insuree.objects.filter(id=insuree_id).first()
                        family = Family.objects.filter(id=insuree.family.id).first()
                        logger.debug(
                            f"====  check_payment_done_by_policyholder  ====  insuree.status  ====  {insuree.status}")
                        logger.debug(
                            f"====  check_payment_done_by_policyholder  ====  family.status  ====  {family.status}")
    else:
        family_members = Insuree.objects.filter(family_id=insuree.family.id, legacy_id=None).all()
        for member in family_members:
            if member.head and member.status == 'ACTIVE':
                Insuree.objects.filter(id=insuree.id).update(status="ACTIVE")
                break

    logger.debug("====  check_payment_done_by_policyholder  ====  end  ====")
    return True


def check_authentication(function):
    def wrapper(self, *args, **kwargs):
        if type(self.user) is AnonymousUser or not self.user.id:
            return {
                "success": False,
                "message": "Authentication required",
                "detail": "PermissionDenied",
            }
        else:
            result = function(self, *args, **kwargs)
            return result

    return wrapper


class PolicyHolder(object):

    def __init__(self, user):
        self.user = user

    @check_authentication
    def get_by_id(self, by_policy_holder):
        try:
            ph = PolicyHolderModel.objects.get(id=by_policy_holder.id)
            uuid_string = str(ph.id)
            dict_representation = model_to_dict(ph)
            dict_representation["id"], dict_representation["uuid"] = (str(uuid_string), str(uuid_string))
        except Exception as exc:
            return _output_exception(model_name="PolicyHolder", method="get", exception=exc)
        return _output_result_success(dict_representation=dict_representation)

    @check_authentication
    def create(self, policy_holder):
        try:
            PolicyHolderValidation.validate_create(self.user, **policy_holder)
            phm = PolicyHolderModel(**policy_holder)
            phm.save(username=self.user.username)
            uuid_string = str(phm.id)
            dict_representation = model_to_dict(phm)
            dict_representation["id"], dict_representation["uuid"] = (str(uuid_string), str(uuid_string))
        except Exception as exc:
            return _output_exception(model_name="PolicyHolder", method="create", exception=exc)
        return _output_result_success(dict_representation=dict_representation)

    @staticmethod
    def check_unique_code_policy_holder(code):
        if PolicyHolderModel.objects.filter(code=code, is_deleted=False).exists():
            return [{"message": "Policy holder code %s already exists" % code}]
        return []

    @check_authentication
    def update(self, policy_holder):
        try:
            PolicyHolderValidation.validate_update(self.user, **policy_holder)
            updated_phm = PolicyHolderModel.objects.filter(id=policy_holder['id']).first()
            [setattr(updated_phm, key, policy_holder[key]) for key in policy_holder]
            updated_phm.save(username=self.user.username)
            if updated_phm.is_submit and not updated_phm.is_approved:
                updated_phm.status = PH_STATUS_PENDING
                updated_phm.save(username=self.user.username)
            uuid_string = str(updated_phm.id)
            dict_representation = model_to_dict(updated_phm)
            dict_representation["id"], dict_representation["uuid"] = (str(uuid_string), str(uuid_string))
        except Exception as exc:
            return _output_exception(model_name="PolicyHolder", method="update", exception=exc)
        return _output_result_success(dict_representation=dict_representation)

    @check_authentication
    def delete(self, policy_holder):
        try:
            phm_to_delete = PolicyHolderModel.objects.filter(id=policy_holder['id']).first()
            phm_to_delete.delete(username=self.user.username)
            return {
                "success": True,
                "message": "Ok",
                "detail": "",
            }
        except Exception as exc:
            return _output_exception(model_name="PolicyHolder", method="delete", exception=exc)


class PolicyHolderInsuree(object):

    def __init__(self, user):
        self.user = user

    @check_authentication
    def get_by_id(self, by_policy_holder_insuree):
        try:
            phi = PolicyHolderInsureeModel.objects.get(id=by_policy_holder_insuree.id)
            uuid_string = str(phi.id)
            dict_representation = model_to_dict(phi)
            dict_representation["id"], dict_representation["uuid"] = (str(uuid_string), str(uuid_string))
        except Exception as exc:
            return _output_exception(model_name="PolicyHolderInsuree", method="get", exception=exc)
        return _output_result_success(dict_representation=dict_representation)

    @check_authentication
    def create(self, policy_holder_insuree):
        try:
            phim = PolicyHolderInsureeModel(**policy_holder_insuree)
            phim.save(username=self.user.username)
            uuid_string = str(phim.id)
            dict_representation = model_to_dict(phim)
            dict_representation["id"], dict_representation["uuid"] = (str(uuid_string), str(uuid_string))
        except Exception as exc:
            return _output_exception(model_name="PolicyHolderInsuree", method="create", exception=exc)
        return _output_result_success(dict_representation=dict_representation)

    @check_authentication
    def update(self, policy_holder_insuree):
        try:
            updated_phim = PolicyHolderInsureeModel.objects.filter(id=policy_holder_insuree['id']).first()
            [setattr(updated_phim, key, policy_holder_insuree[key]) for key in policy_holder_insuree]
            updated_phim.save(username=self.user.username)
            uuid_string = str(updated_phim.id)
            dict_representation = model_to_dict(updated_phim)
            dict_representation["id"], dict_representation["uuid"] = (str(uuid_string), str(uuid_string))
        except Exception as exc:
            return _output_exception(model_name="PolicyHolderInsuree", method="update", exception=exc)
        return _output_result_success(dict_representation=dict_representation)

    @check_authentication
    def delete(self, policy_holder_insuree):
        try:
            phim_to_delete = PolicyHolderInsureeModel.objects.filter(id=policy_holder_insuree['id']).first()
            phim_to_delete.delete(username=self.user.username)
            return {
                "success": True,
                "message": "Ok",
                "detail": "",
            }
        except Exception as exc:
            return _output_exception(model_name="PolicyHolderInsuree", method="delete", exception=exc)

    @check_authentication
    def replace_policy_holder_insuree(self, policy_holder_insuree):
        try:
            phim_to_replace = PolicyHolderInsureeModel.objects.filter(id=policy_holder_insuree['uuid']).first()
            phim_to_replace.replace_object(data=policy_holder_insuree, username=self.user.username)
            uuid_string = str(phim_to_replace.id)
            dict_representation = model_to_dict(phim_to_replace)
            dict_representation["id"], dict_representation["uuid"] = (str(uuid_string), str(uuid_string))
        except Exception as exc:
            return _output_exception(model_name="PolicyHolderInsuree", method="replace", exception=exc)
        return {
            "success": True,
            "message": "Ok",
            "detail": "",
            "old_object": json.loads(json.dumps(dict_representation, cls=DjangoJSONEncoder)),
            "uuid_new_object": str(phim_to_replace.replacement_uuid),
        }


class PolicyHolderContributionPlan(object):

    def __init__(self, user):
        self.user = user

    @check_authentication
    def get_by_id(self, by_policy_holder_contribution_plan):
        try:
            phcp = PolicyHolderContributionPlanModel.objects.get(id=by_policy_holder_contribution_plan.id)
            uuid_string = str(phcp.id)
            dict_representation = model_to_dict(phcp)
            dict_representation["id"], dict_representation["uuid"] = (str(uuid_string), str(uuid_string))
        except Exception as exc:
            return _output_exception(model_name="PolicyHolderContributionPlan", method="get", exception=exc)
        return _output_result_success(dict_representation=dict_representation)

    # @check_authentication
    def create(self, policy_holder_contribution_plan):
        try:
            logger.info("======== PolicyHolderContributionPlan : create : start ========")
            phcp = PolicyHolderContributionPlanModel(**policy_holder_contribution_plan)
            phcp.save(username=self.user.username)
            # TODO: call erp integration and pass this object
            # print("========>  phcp  :  ", phcp)
            # erp_create_update_policyholder(phcp)
            uuid_string = str(phcp.id)
            dict_representation = model_to_dict(phcp)
            dict_representation["id"], dict_representation["uuid"] = (str(uuid_string), str(uuid_string))
        except Exception as exc:
            return _output_exception(model_name="PolicyHolderContributionPlan", method="create", exception=exc)
        return _output_result_success(dict_representation=dict_representation)

    # @check_authentication
    def update(self, policy_holder_contribution_plan):
        try:
            updated_phcp = PolicyHolderContributionPlanModel.objects.filter(
                id=policy_holder_contribution_plan['id']).first()
            [setattr(updated_phcp, key, policy_holder_contribution_plan[key]) for key in
             policy_holder_contribution_plan]
            updated_phcp.save(username=self.user.username)
            uuid_string = str(updated_phcp.id)
            dict_representation = model_to_dict(updated_phcp)
            dict_representation["id"], dict_representation["uuid"] = (str(uuid_string), str(uuid_string))
        except Exception as exc:
            return _output_exception(model_name="PolicyHolderContributionPlan", method="update", exception=exc)
        return _output_result_success(dict_representation=dict_representation)

    @check_authentication
    def delete(self, policy_holder_contribution_plan):
        try:
            phcp_to_delete = PolicyHolderContributionPlanModel.objects.filter(
                id=policy_holder_contribution_plan['id']).first()
            phcp_to_delete.delete(username=self.user.username)
            return {
                "success": True,
                "message": "Ok",
                "detail": "",
            }
        except Exception as exc:
            return _output_exception(model_name="PolicyHolderContributionPlan", method="delete", exception=exc)

    # @check_authentication
    def replace_policy_holder_contribution_plan_bundle(self, policy_holder_contribution_plan):
        try:
            phcp_to_replace = PolicyHolderContributionPlanModel.objects.filter(
                id=policy_holder_contribution_plan['uuid']).first()
            phcp_to_replace.replace_object(data=policy_holder_contribution_plan, username=self.user.username)
            uuid_string = str(phcp_to_replace.id)
            dict_representation = model_to_dict(phcp_to_replace)
            dict_representation["id"], dict_representation["uuid"] = (str(uuid_string), str(uuid_string))
        except Exception as exc:
            return _output_exception(model_name="PolicyHolderContributionPlan", method="replace", exception=exc)
        return {
            "success": True,
            "message": "Ok",
            "detail": "",
            "old_object": json.loads(json.dumps(dict_representation, cls=DjangoJSONEncoder)),
            "uuid_new_object": str(phcp_to_replace.replacement_uuid),
        }


class PolicyHolderUser(object):

    def __init__(self, user):
        self.user = user

    @check_authentication
    def get_by_id(self, by_policy_holder_user):
        try:
            phu = PolicyHolderUserModel.objects.get(id=by_policy_holder_user.id)
            uuid_string = str(phu.id)
            dict_representation = model_to_dict(phu)
            dict_representation["id"], dict_representation["uuid"] = (str(uuid_string), str(uuid_string))
        except Exception as exc:
            return _output_exception(model_name="PolicyHolderUser", method="get", exception=exc)
        return _output_result_success(dict_representation=dict_representation)

    @check_authentication
    def create(self, policy_holder_user):
        try:
            phu = PolicyHolderUserModel(**policy_holder_user)
            phu.save(username=self.user.username)
            uuid_string = str(phu.id)
            dict_representation = model_to_dict(phu)
            dict_representation["id"], dict_representation["uuid"] = (str(uuid_string), str(uuid_string))
        except Exception as exc:
            return _output_exception(model_name="PolicyHolderUser", method="create", exception=exc)
        return _output_result_success(dict_representation=dict_representation)

    @check_authentication
    def update(self, policy_holder_user):
        try:
            updated_phu = PolicyHolderUserModel.objects.filter(id=policy_holder_user['id']).first()
            [setattr(updated_phu, key, policy_holder_user[key]) for key in policy_holder_user]
            updated_phu.save(username=self.user.username)
            uuid_string = str(updated_phu.id)
            dict_representation = model_to_dict(updated_phu)
            dict_representation["id"], dict_representation["uuid"] = (str(uuid_string), str(uuid_string))
        except Exception as exc:
            return _output_exception(model_name="PolicyHolderUser", method="update", exception=exc)
        return _output_result_success(dict_representation=dict_representation)

    @check_authentication
    def delete(self, policy_holder_user):
        try:
            phu_to_delete = PolicyHolderUserModel.objects.filter(id=policy_holder_user['id']).first()
            phu_to_delete.delete(username=self.user.username)
            return {
                "success": True,
                "message": "Ok",
                "detail": "",
            }
        except Exception as exc:
            return _output_exception(model_name="PolicyHolderUser", method="delete", exception=exc)

    @check_authentication
    def replace_policy_holder_user(self, policy_holder_user):
        try:
            phu_to_replace = PolicyHolderUserModel.objects.filter(id=policy_holder_user['uuid']).first()
            phu_to_replace.replace_object(data=policy_holder_user, username=self.user.username)
            uuid_string = str(phu_to_replace.id)
            dict_representation = model_to_dict(phu_to_replace)
            dict_representation["id"], dict_representation["uuid"] = (str(uuid_string), str(uuid_string))
        except Exception as exc:
            return _output_exception(model_name="PolicyHolderUser", method="replace", exception=exc)
        return {
            "success": True,
            "message": "Ok",
            "detail": "",
            "old_object": json.loads(json.dumps(dict_representation, cls=DjangoJSONEncoder)),
            "uuid_new_object": str(phu_to_replace.replacement_uuid),
        }


class PolicyHolderActivity(object):
    def __init__(self, user):
        self.user = user

    @check_authentication
    def get_all(self):
        return _output_result_success(PolicyholderConfig.policyholder_activity)


class PolicyHolderLegalForm(object):
    def __init__(self, user):
        self.user = user

    @check_authentication
    def get_all(self):
        return _output_result_success(PolicyholderConfig.policyholder_legal_form)


def _output_exception(model_name, method, exception):
    return {
        "success": False,
        "message": f"Failed to {method} {model_name}",
        "detail": str(exception),
        "data": "",
    }


def _output_result_success(dict_representation):
    return {
        "success": True,
        "message": "Ok",
        "detail": "",
        "data": json.loads(json.dumps(dict_representation, cls=DjangoJSONEncoder)),
    }


def assign_ph_exception_policy(ph_exception):
    return True


def generate_camu_registration_number(code):
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


def tipl_contract_scenarios(user, contract):
    from contract.gql.gql_mutations.mutations import ContractCreateMutationMixin, ContractSubmitMutationMixin, \
        ContractApproveMutationMixin
    # Validation
    if not user or not contract:
        logger.error(f"Invalid user or contract data: user={user}, contract={contract}")
        return False

    try:
        contract_create_mixin = ContractCreateMutationMixin()
        c_output = contract_create_mixin.create_contract(user, contract)
        logger.info(f"Contract creation output: {c_output}")
        data = c_output.get('data', None)
        contract['id'] =data.get('id', None)
        contract_submit_mixin = ContractSubmitMutationMixin()
        s_output = contract_submit_mixin.submit_contract(user, contract)
        logger.info(f"Contract submission output: {s_output}")

        contract_approved_mixin = ContractApproveMutationMixin()
        a_output = contract_approved_mixin.approve_contract(user, contract)
        logger.info(f"Contract approval output: {a_output}")

    except Exception as e:
        logger.error(f"Error during contract processing: {str(e)}", exc_info=True)
        return False

    logger.info(f"Contract scenarios processed successfully for user: {user.id}, contract: {contract['id']}")
    return True


def tipl_payment_scenarios(user, contract, payment_date, bank, payment_amount, payment_reference):
    # Validation
    if not all([user, contract, payment_date, bank, payment_amount, payment_reference]):
        logger.error(f"Invalid data: user={user}, contract={contract}, payment_date={payment_date}, "
                     f"bank={bank}, payment_amount={payment_amount}, payment_reference={payment_reference}")
        return False

    try:
        # Log beginning of the process
        logger.info(f"Starting payment scenario for contract: {contract['id']} and user: {user.id}")

        # Prepare JSON extended data
        bank_encode_id = f'BanksType:{bank.id}'
        json_ext_data = {
            "bank": {
                "id": base64_encode(bank_encode_id),
                "code": bank.code,
                "name": bank.name,
                "erpId": bank.erp_id,
                "jsonExt": None,  # Assuming this is still None as per your example
                "journauxId": bank.journaux_id,
                "altLangName": bank.alt_lang_name,
                "dateCreated": bank.date_created.strftime("%Y-%m-%d %H:%M:%S") if bank.date_created else None,
                "dateUpdated": bank.date_updated.strftime("%Y-%m-%d %H:%M:%S") if bank.date_updated else None
            },
            "amount": int(payment_amount),
            "receiptNo": payment_reference,
            "journauxId": bank.journaux_id,
            "payment_method_id": TIPL_PAYMENT_METHOD_ID,
        }

        # Validate contract existence
        contract_obj = Contract.objects.filter(id=contract['id']).first()
        if not contract_obj:
            logger.error(f"Contract not found: {contract['id']}")
            return False

        # Retrieve the first valid payment
        payment = Payment.objects.filter(
            contract=contract_obj,
            legacy_id__isnull=True,
            validity_to__isnull=True,
            status=Payment.STATUS_CREATED
        ).order_by('validity_from').first()

        if not payment:
            logger.error(f"No valid payment found for contract: {contract['id']}")
            return False
        if payment.expected_amount != payment_amount:
            return False
        # Update payment data
        payment.received_amount = payment.expected_amount
        payment.status = Payment.STATUS_APPROVED
        payment.matched_date = payment_date
        payment.received_amount_transaction = [json_ext_data]

        # Save payment and log the update
        payment.save()
        logger.info(f"Payment updated and approved for contract: {contract['id']}, payment: {payment.id}")

    except Exception as e:
        logger.error(f"Error processing payment scenario: {str(e)}", exc_info=True)
        return False

    logger.info(f"Payment scenario processed successfully for user: {user.id}, contract: {contract['id']}")
    return True
