import json
import requests
import logging
from policyholder.models import PolicyHolderContributionPlan

logger = logging.getLogger(__name__)

# erp_url = os.environ.get('ERP_HOST')
erp_url = "https://camu-staging-13483170.dev.odoo.com"

headers = {
    'Content-Type': 'application/json',
    'Tmr-Api-Key': 'test'
}

def erp_mapping_data(phcp, is_vendor, account_payable_id=None):
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
    }
    return mapping_dict

def filter_null_values(data):
    return {k: v for k, v in data.items() if v is not None}

def erp_create_update_policyholder(ph_id, cpb_id):
    logger.debug(" ======    erp_create_update_policyholder - start    =======")
    logger.debug(f" ======    erp_create_update_policyholder : ph_id : {ph_id}    =======")
    logger.debug(f" ======    erp_create_update_policyholder : cpb_id : {cpb_id}    =======")
    
    phcp = PolicyHolderContributionPlan.objects.filter(
        policy_holder__id=ph_id, contribution_plan_bundle__id=cpb_id, is_deleted=False).first()
    
    policyholder_data = erp_mapping_data(phcp, False)
    
    policyholder_data = filter_null_values(policyholder_data)
    
    if phcp.policy_holder.erp_partner_access_id:
        logger.debug(" ======    erp_create_update_policyholder - update    =======")
        url = '{}/update/partner/{}'.format(erp_url, phcp.policy_holder.erp_partner_access_id)
        logger.debug(f" ======    erp_create_update_policyholder : url : {url}    =======")
    else:
        logger.debug(" ======    erp_create_update_policyholder - create    =======")
        url = '{}/create/partner'.format(erp_url)
        logger.debug(f" ======    erp_create_update_policyholder : url : {url}    =======")
        
    logger.debug(f" ======    erp_create_update_policyholder : policyholder_data : {policyholder_data}    =======")
    
    try:
        json_data = json.dumps(policyholder_data)
        logger.debug(f" ======    erp_create_update_policyholder : json_data : {json_data}    =======")
    except TypeError as e:
        logger.error(f"Error serializing JSON: {e}")
    
    response = requests.post(url, headers=headers, json=json_data, verify=False)
    logger.debug(f" ======    erp_create_update_policyholder : response.status_code : {response.status_code}    =======")
    logger.debug(f" ======    erp_create_update_policyholder : response.json : {response.json()}    =======")
    logger.debug(" ======    erp_create_update_policyholder - end    =======")
    return True

def erp_create_update_fosa():
    logger.debug(" ======    erp_create_update_fosa - start    =======")
    policyholder_data = {}
    
    policyholder_obj = None
    
    for key, field_path in mapping_dict.items():
        policyholder_data[key] = get_value_from_mapping(policyholder_obj, field_path)
        
    policyholder_data.update(static_values_fosa)
    
    print(policyholder_data)
    logger.debug(" ======    erp_create_update_fosa - end    =======")
    return True
