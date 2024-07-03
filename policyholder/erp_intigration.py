import json
import requests

mapping_dict = {
    "name": "policy_holder.trade_name",
    "partner_type": "contribution_plan_bundle.partner_type",
    "email": "policy_holder.email",
    "phone": "policy_holder.phone",
    "mobile": "policy_holder.phone",
    "address": "policy_holder.address",
    "city": None,
    "zip": None,
    "state_id": None,
    "account_receivable_id": "contribution_plan_bundle.account_receivable_id",
    "account_payable_id": "hf_category.account_payable_id"
}
# "json_field_value": "json_data.key_in_json"  # JSON field access

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
    policyholder_data = {}
    
    for key, field_path in mapping_dict.items():
        policyholder_data[key] = get_value_from_mapping(phcp, field_path)
        
    policyholder_data.update(static_values_policyholder)
    
    if phcp.policy_holder.erp_partner_access_id:
        #TODO: call update partner api
        print(policyholder_data)
    else:
        #TODO: call update partner api
        print(policyholder_data)

def erp_create_update_fosa():
    policyholder_data = {}
    
    policyholder_obj = None
    
    for key, field_path in mapping_dict.items():
        policyholder_data[key] = get_value_from_mapping(policyholder_obj, field_path)
        
    policyholder_data.update(static_values)
    
    print(policyholder_data)
