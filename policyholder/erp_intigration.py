import json
import requests
import logging

logger = logging.getLogger(__name__)

# erp_url = os.environ.get('ERP_HOST')
erp_url = "https://camu-staging-13483170.dev.odoo.com"

mapping_dict = {
    "name": "policy_holder.trade_name",
    "partner_type": "contribution_plan_bundle.partner_type",
    "email": "policy_holder.email",
    "phone": "policy_holder.phone",
    "mobile": "policy_holder.phone",
    "address": "policy_holder.address.address",
    "city": None,
    "zip": None,
    "state_id": None,
    "account_receivable_id": "contribution_plan_bundle.account_receivable_id",
}
# "json_field_value": "json_data.key_in_json"  # JSON field access

fosa_mapping_dict = {
    "account_payable_id": "hf_category.account_payable_id"
}

static_values_policyholder = {
    "is_customer": True,
    "is_vendor": False,
    "country_id": 2
}

static_values_fosa = {
    "is_customer": True,
    "is_vendor": True,
    "country_id": 2
}

headers = {
    'Content-Type': 'application/json',
    'Tmr-Api-Key': 'test'
}

def get_value_from_mapping(obj, field_path):
    parts = field_path.split('.')
    for part in parts:
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj

def erp_create_update_policyholder(phcp):
    logger.info(" ======    erp_create_update_policyholder - start    =======")
    policyholder_data = {}
    
    for key, field_path in mapping_dict.items():
        policyholder_data[key] = get_value_from_mapping(phcp, field_path)
        
    policyholder_data.update(static_values_policyholder)
    
    if phcp.policy_holder.erp_partner_access_id:
        #TODO: call update partner api
        logger.info(" ======    erp_create_update_policyholder - update    =======")
        logger.info(f" ======    erp_create_update_policyholder : policyholder_data : {policyholder_data}    =======")
        print(policyholder_data)
    else:
        logger.info(" ======    erp_create_update_policyholder - create    =======")
        #TODO: call update partner api
        url = '{}/create/partner'.format(erp_url)
        logger.info(f" ======    erp_create_update_policyholder : url : {url}    =======")
        logger.info(f" ======    erp_create_update_policyholder : policyholder_data : {policyholder_data}    =======")
        print(policyholder_data)
        response = requests.post(url, headers=headers, json=policyholder_data, verify=False)
        logger.info(f" ======    erp_create_update_policyholder : response.status_code : {response.status_code}    =======")
        logger.info(f" ======    erp_create_update_policyholder : response.json : {response.json()}    =======")
    logger.info(" ======    erp_create_update_policyholder - end    =======")
    return True

def erp_create_update_fosa():
    logger.info(" ======    erp_create_update_fosa - start    =======")
    policyholder_data = {}
    
    policyholder_obj = None
    
    for key, field_path in mapping_dict.items():
        policyholder_data[key] = get_value_from_mapping(policyholder_obj, field_path)
        
    policyholder_data.update(static_values_fosa)
    
    print(policyholder_data)
    logger.info(" ======    erp_create_update_fosa - end    =======")
    return True
