import json
import requests
import logging

from policyholder.constants import BANK_ACCOUNT_ID
from policyholder.models import PolicyHolderContributionPlan, PolicyHolder
from rest_framework.decorators import permission_classes, api_view, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from location.models import HealthFacility, HealthFacilityCategory
from policyholder.apps import MODULE_NAME
from core.models import ErpApiFailedLogs


logger = logging.getLogger(__name__)

# erp_url = os.environ.get('ERP_HOST')
erp_url = "https://camu-staging-13483170.dev.odoo.com"

headers = {
    'Content-Type': 'application/json',
    'Tmr-Api-Key': 'test'
}

def erp_mapping_data(phcp, bank_accounts, is_vendor, account_payable_id=None):
    mapping_dict = {
        "name": phcp.policy_holder.trade_name,
        "partner_type": phcp.contribution_plan_bundle.partner_type,
        "email": phcp.policy_holder.email,
        "phone": phcp.policy_holder.phone,
        "mobile": phcp.policy_holder.phone,
        "address": phcp.policy_holder.address["address"],
        "city": None,
        "zip": None,
        "state_id": None,
        "is_customer": True,
        "is_vendor": is_vendor,
        "country_id": 2,
        "account_receivable_id": phcp.contribution_plan_bundle.account_receivable_id,
        "account_payable_id": account_payable_id,
        "bank_accounts" : bank_accounts
    }
    return mapping_dict

def filter_null_values(data):
    return {k: v for k, v in data.items() if v is not None}

def erp_create_update_policyholder(ph_id, cpb_id, user):
    logger.debug(" ======    erp_create_update_policyholder - start    =======")
    logger.debug(f" ======    erp_create_update_policyholder : ph_id : {ph_id}    =======")
    logger.debug(f" ======    erp_create_update_policyholder : cpb_id : {cpb_id}    =======")

    phcp = PolicyHolderContributionPlan.objects.filter(
        policy_holder__id=ph_id, contribution_plan_bundle__id=cpb_id, is_deleted=False).first()

    bank_accounts = None
    if phcp and phcp.policy_holder.bank_account:
        bank_account = phcp.policy_holder.bank_account.get("bankAccount", {})
        account_no = bank_account.get("accountNb")

        if account_no:
            # bank = bank_account.get("bank")
            # bank_id = BANK_ACCOUNT_ID.get(bank)
            bank_id = 2  # just for test purpose
            bank_accounts = []
            bank_account_details = {
                "account_number": account_no,
                "bank_id": bank_id,
                "account_holder_name": phcp.policy_holder.trade_name
            }
            bank_accounts.append(filter_null_values(bank_account_details))

    policyholder_data = erp_mapping_data(phcp, bank_accounts, False)
    policyholder_data = filter_null_values(policyholder_data)

    if phcp.policy_holder.erp_partner_access_id:
        logger.debug(" ======    erp_create_update_policyholder - update    =======")
        action = "Create Policyholder"
        url = '{}/update/partner/{}'.format(erp_url, phcp.policy_holder.erp_partner_access_id)
        logger.debug(f" ======    erp_create_update_policyholder : url : {url}    =======")
    else:
        logger.debug(" ======    erp_create_update_policyholder - create    =======")
        action = "Update Policyholder"
        url = '{}/create/partner'.format(erp_url)
        logger.debug(f" ======    erp_create_update_policyholder : url : {url}    =======")

    logger.debug(f" ======    erp_create_update_policyholder : policyholder_data : {policyholder_data}    =======")

    try:
        json_data = json.dumps(policyholder_data)
        logger.debug(f" ======    erp_create_update_policyholder : json_data : {json_data}    =======")
    except TypeError as e:
        logger.error(f"Error serializing JSON: {e}")

    response = requests.post(url, headers=headers, json=policyholder_data, verify=False)
    logger.debug(f" ======    erp_create_update_policyholder : response.status_code : {response.status_code}    =======")
    logger.debug(f" ======    erp_create_update_policyholder : response.text : {response.text}    =======")

    if response.status_code != 200:
        failed_data = {
            "module": MODULE_NAME,
            "policy_holder": phcp.policy_holder,
            "action": action,
            "response_status_code": response.status_code,
            "response_json": response.json(),
            "request_url": url,
            "message": response.text,
            "request_data": policyholder_data,
            "resync_status": 0,
            "created_by": user
        }
        try:
            ErpApiFailedLogs.objects.create(**failed_data)
            logger.info("ERP API Failed log saved successfully")
        except Exception as e:
            logger.error(f"Failed to save ERP API Failed log: {e}")
    try:
        response_json = response.json()
        logger.debug(f" ======    erp_create_update_policyholder : response.json : {response_json}    =======")

        # Update the PolicyHolder with the IDs from the response
        PolicyHolder.objects.filter(id=ph_id).update(
            erp_partner_id=response_json.get("id"), erp_partner_access_id=response_json.get("partner_access_id"))
    except json.JSONDecodeError:
        logger.error("Failed to decode JSON response")

    logger.debug(" ======    erp_create_update_policyholder - end    =======")
    return True

def erp_create_update_fosa(policyholder_code, account_receivable_id, user):
    logger.debug(" ======    erp_create_update_fosa - start    =======")
    logger.debug(f" ======    erp_create_update_fosa : policyholder_code : {policyholder_code}    =======")

    policy_holder = PolicyHolder.objects.filter(code=policyholder_code, is_deleted=False).first()
    phcp = PolicyHolderContributionPlan.objects.filter(policy_holder=policy_holder, is_deleted=False).first()

    health_facility = HealthFacility.objects.filter(legacy_id__isnull=True, validity_to__isnull=True, json_ext__camuCode=policyholder_code).first()
    bank_accounts = None
    if phcp and phcp.policy_holder.bank_account:
        bank_account = phcp.policy_holder.bank_account.get("bankAccount", {})
        account_no = bank_account.get("accountNb")

        if account_no:
            # bank = bank_account.get("bank")
            # bank_id = BANK_ACCOUNT_ID.get(bank)
            bank_id = 2  # just for test purpose
            bank_accounts = []
            bank_account_details = {
                "account_number": account_no,
                "bank_id": bank_id,
                "account_holder_name": phcp.policy_holder.trade_name
            }
            bank_accounts.append(filter_null_values(bank_account_details))

    policyholder_data = erp_mapping_data(phcp, bank_accounts, True, account_receivable_id)
    policyholder_data = filter_null_values(policyholder_data)

    url = '{}/update/partner/{}'.format(erp_url, phcp.policy_holder.erp_partner_access_id)
    logger.debug(f" ======    erp_create_update_fosa : url : {url}    =======")
    logger.debug(f" ======    erp_create_update_fosa : policyholder_data : {policyholder_data}    =======")

    try:
        json_data = json.dumps(policyholder_data)
        logger.debug(f" ======    erp_create_update_fosa : json_data : {json_data}    =======")
    except TypeError as e:
        logger.error(f"Error serializing JSON: {e}")

    response = requests.post(url, headers=headers, json=policyholder_data, verify=False)
    logger.debug(f" ======    erp_create_update_fosa : response.status_code : {response.status_code}    =======")
    logger.debug(f" ======    erp_create_update_fosa : response.text : {response.text}    =======")

    if response.status_code != 200:
        failed_data = {
            "module": 'fosa',
            "health_facility": health_facility,
            "action": "Fosa Creation",
            "response_status_code": response.status_code,
            "response_json": response.json(),
            "request_url": url,
            "message": response.text,
            "request_data": policyholder_data,
            "resync_status": 0,
            "created_by": user
        }
        try:
            ErpApiFailedLogs.objects.create(**failed_data)
            logger.info("ERP API Failed log saved successfully")
        except Exception as e:
            logger.error(f"Failed to save ERP API Failed log: {e}")

    try:
        response_json = response.json()
        logger.debug(f" ======    erp_create_update_fosa : response.json : {response_json}    =======")
    except json.JSONDecodeError:
        logger.error("Failed to decode JSON response")

    logger.debug(" ======    erp_create_update_fosa - end    =======")
    return True


@authentication_classes([])
@permission_classes([AllowAny])
def create_existing_policyholder_in_erp():
    logger.debug(" ======    create_existing_policyholder_in_erp - Start    =======")
    policyholder_list = PolicyHolder.objects.filter(erp_partner_id__isnull=True, is_deleted=False)
    logger.debug(f" ======    create_existing_policyholder_in_erp : policyholder_list : {policyholder_list}    =======")
    for policyholder in policyholder_list:
        phcp = PolicyHolderContributionPlan.objects.filter(policy_holder=policyholder, is_deleted=False).first()
        logger.debug(f" ======    create_existing_policyholder_in_erp : phcp : {phcp}    =======")
        if phcp:
            policyholder_data = erp_mapping_data(phcp, False)
            policyholder_data = filter_null_values(policyholder_data)

            url = '{}/create/partner'.format(erp_url)
            logger.debug(f" ======    create_existing_policyholder_in_erp : url : {url}    =======")

            logger.debug(f" ======    create_existing_policyholder_in_erp : policyholder_data : {policyholder_data}    =======")

            try:
                json_data = json.dumps(policyholder_data)
                logger.debug(f" ======    create_existing_policyholder_in_erp : json_data : {json_data}    =======")
            except TypeError as e:
                logger.error(f"Error serializing JSON: {e}")

            response = requests.post(url, headers=headers, json=policyholder_data, verify=False)
            logger.debug(f" ======    create_existing_policyholder_in_erp : response.status_code : {response.status_code}    =======")
            logger.debug(f" ======    create_existing_policyholder_in_erp : response.text : {response.text}    =======")

            try:
                response_json = response.json()
                logger.debug(f" ======    create_existing_policyholder_in_erp : response.json : {response_json}    =======")

                # Update the PolicyHolder with the IDs from the response
                PolicyHolder.objects.filter(id=ph_id).update(
                    erp_partner_id=response_json.get("id"), erp_partner_access_id=response_json.get("partner_access_id"))
            except json.JSONDecodeError:
                logger.error("Failed to decode JSON response")

    logger.debug(" ======    create_existing_policyholder_in_erp - End    =======")
    return Response({"message": "Script Successfully Run."})


@authentication_classes([])
@permission_classes([AllowAny])
def create_existing_fosa_in_erp():
    logger.debug(" ======    create_existing_fosa_in_erp - Start    =======")
    fosa_list = HealthFacility.objects.filter(legacy_id__isnull=True, validity_to__isnull=True)
    logger.debug(f" ======    create_existing_fosa_in_erp : fosa_list : {fosa_list}    =======")
    for fosa in fosa_list:
        logger.debug(f" ======    create_existing_fosa_in_erp : fosa.id : {fosa.id}    =======")
        logger.debug(f" ======    create_existing_fosa_in_erp : fosa.fosa_code : {fosa.fosa_code}    =======")
        policyholder_code = fosa.json_ext["camuCode"]
        category_fosa = fosa.json_ext["category_fosa"]
        policy_holder = PolicyHolder.objects.filter(code=policyholder_code, is_deleted=False).first()
        hf_cat = HealthFacilityCategory.objects.filter(code=updated_object.json_ext['category_fosa'], is_deleted=False).first()
        logger.debug(f" ======    create_existing_fosa_in_erp : policyholder_code : {policyholder_code}    =======")
        logger.debug(f" ======    create_existing_fosa_in_erp : category_fosa : {category_fosa}    =======")
        if policy_holder and hf_cat and hf_cat.account_receivable_id:
            logger.debug(f" ======    create_existing_fosa_in_erp : policy_holder.id : {policy_holder.id}    =======")
            logger.debug(f" ======    create_existing_fosa_in_erp : policy_holder.code : {policy_holder.code}    =======")
            logger.debug(f" ======    create_existing_fosa_in_erp : hf_cat.id : {hf_cat.id}    =======")
            logger.debug(f" ======    create_existing_fosa_in_erp : hf_cat.account_receivable_id : {hf_cat.account_receivable_id}    =======")
            phcp = PolicyHolderContributionPlan.objects.filter(policy_holder=policy_holder, is_deleted=False).first()
            logger.debug(f" ======    create_existing_fosa_in_erp : phcp.id : {phcp.id}    =======")
            if phcp:
                policyholder_data = erp_mapping_data(phcp, True, hf_cat.account_receivable_id)
                policyholder_data = filter_null_values(policyholder_data)

                url = '{}/update/partner/{}'.format(erp_url, phcp.policy_holder.erp_partner_access_id)
                logger.debug(f" ======    create_existing_fosa_in_erp : url : {url}    =======")
                logger.debug(f" ======    create_existing_fosa_in_erp : policyholder_data : {policyholder_data}    =======")

                try:
                    json_data = json.dumps(policyholder_data)
                    logger.debug(f" ======    create_existing_fosa_in_erp : json_data : {json_data}    =======")
                except TypeError as e:
                    logger.error(f"Error serializing JSON: {e}")

                response = requests.post(url, headers=headers, json=policyholder_data, verify=False)
                logger.debug(f" ======    create_existing_fosa_in_erp : response.status_code : {response.status_code}    =======")
                logger.debug(f" ======    create_existing_fosa_in_erp : response.text : {response.text}    =======")

    logger.debug(" ======    create_existing_fosa_in_erp - End    =======")
    return Response({"message": "Script Successfully Run."})