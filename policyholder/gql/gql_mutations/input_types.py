import graphene

from core.schema import OpenIMISMutation, TinyInt, UserBase
from core.gql.gql_mutations import ReplaceInputType


class PolicyHolderInputType(OpenIMISMutation.Input):
    id = graphene.UUID(required=False)

    code = graphene.String(max_length=255, required=False)
    trade_name = graphene.String(max_length=255, required=True)
    locations_id = graphene.Int(required=False, name="locationsId")
    address = graphene.types.json.JSONString(max_length=255, required=False)
    phone = graphene.String(max_length=50, required=False)
    fax = graphene.String(max_length=50, required=False)
    email = graphene.String(max_length=255, required=False)
    contact_name = graphene.types.json.JSONString(required=False)
    legal_form = graphene.Int(required=False)
    activity_code = graphene.Int(required=False)
    accountancy_account = graphene.String(required=False)
    bank_account = graphene.types.json.JSONString(required=False)
    payment_reference = graphene.String(required=False)
    date_valid_from = graphene.Date(required=False)
    date_valid_to = graphene.Date(required=False)
    json_ext = graphene.types.json.JSONString(required=False)


class PolicyHolderUpdateInputType(OpenIMISMutation.Input):
    id = graphene.UUID(required=True)
    code = graphene.String(max_length=255, required=False)
    trade_name = graphene.String(max_length=255, required=False)
    locations_id = graphene.Int(required=False, name="locationsId")
    address = graphene.types.json.JSONString(max_length=255, required=False)
    phone = graphene.String(max_length=50, required=False)
    fax = graphene.String(max_length=50, required=False)
    email = graphene.String(max_length=255, required=False)
    contact_name = graphene.types.json.JSONString(required=False)
    legal_form = graphene.Int(required=False)
    activity_code = graphene.Int(required=False)
    accountancy_account = graphene.String(required=False)
    bank_account = graphene.types.json.JSONString(required=False)
    payment_reference = graphene.String(required=False)
    date_valid_from = graphene.Date(required=False)
    date_valid_to = graphene.Date(required=False)
    json_ext = graphene.types.json.JSONString(required=False)
    is_review = graphene.Boolean(required=False)
    is_submit = graphene.Boolean(required=False)
    status = graphene.String(required=False)


class PolicyHolderInsureeInputType(OpenIMISMutation.Input):
    id = graphene.UUID(required=False)
    policy_holder_id = graphene.UUID(required=False)
    insuree_id = graphene.Int(required=False, name="insureeId")
    contribution_plan_bundle_id = graphene.UUID(requried=False, name="contributionPlanBundleId")
    last_policy_id = graphene.Int(required=False, name="lastPolicyId")
    date_valid_from = graphene.Date(required=False)
    date_valid_to = graphene.Date(required=False)
    json_ext = graphene.types.json.JSONString(required=False)
    employer_number = graphene.String(required =False, max_length=50)


class PolicyHolderInsureeUpdateInputType(OpenIMISMutation.Input):
    id = graphene.UUID(required=True)
    policy_holder_id = graphene.UUID(required=False)
    insuree_id = graphene.Int(required=False, name="insureeId")
    contribution_plan_bundle_id = graphene.UUID(requried=False, name="contributionPlanBundleId")
    last_policy_id = graphene.Int(required=False, name="lastPolicyId")
    date_valid_from = graphene.Date(required=False)
    date_valid_to = graphene.Date(required=False)
    json_ext = graphene.types.json.JSONString(required=False)
    employer_number = graphene.String(required=False, max_length=50)


class PolicyHolderInsureeReplaceInputType(ReplaceInputType):
    insuree_id = graphene.Int(required=True, name="insureeId")
    contribution_plan_bundle_id = graphene.UUID(requried=True, name="contributionPlanBundleId")
    json_ext = graphene.types.json.JSONString(required=False)
    date_valid_from = graphene.Date(required=True)
    date_valid_to = graphene.Date(required=False)


class PolicyHolderContributionPlanInputType(OpenIMISMutation.Input):
    id = graphene.UUID(required=False)
    policy_holder_id = graphene.UUID(required=False)
    contribution_plan_bundle_id = graphene.UUID(requried=False, name="contributionPlanBundleId")
    date_valid_from = graphene.Date(required=False)
    date_valid_to = graphene.Date(required=False)
    json_ext = graphene.types.json.JSONString(required=False)
    skip_erp_update = graphene.Boolean(required=False)


class PolicyHolderContributionPlanUpdateInputType(OpenIMISMutation.Input):
    id = graphene.UUID(required=True)
    policy_holder_id = graphene.UUID(required=False)
    contribution_plan_bundle_id = graphene.UUID(requried=False, name="contributionPlanBundleId")
    date_valid_from = graphene.Date(required=False)
    date_valid_to = graphene.Date(required=False)
    json_ext = graphene.types.json.JSONString(required=False)


class PolicyHolderContributionPlanReplaceInputType(ReplaceInputType):
    contribution_plan_bundle_id = graphene.UUID(requried=True, name="contributionPlanBundleId")
    date_valid_from = graphene.Date(required=True)
    date_valid_to = graphene.Date(required=False)


class PolicyHolderUserInputType(OpenIMISMutation.Input):
    id = graphene.UUID(required=False)
    user_id = graphene.UUID(required=False)
    policy_holder_id = graphene.UUID(required=False)
    date_valid_from = graphene.Date(required=False)
    date_valid_to = graphene.Date(required=False)
    json_ext = graphene.types.json.JSONString(required=False)


class PolicyHolderUserUpdateInputType(OpenIMISMutation.Input):
    id = graphene.UUID(required=True)
    user_id = graphene.UUID(required=False)
    policy_holder_id = graphene.UUID(required=False)
    date_valid_from = graphene.Date(required=False)
    date_valid_to = graphene.Date(required=False)
    json_ext = graphene.types.json.JSONString(required=False)


class PolicyHolderUserReplaceInputType(ReplaceInputType):
    user_id = graphene.UUID(required=True)
    policy_holder_id = graphene.UUID(required=False)
    date_valid_from = graphene.Date(required=True)
    date_valid_to = graphene.Date(required=False)


class PolicyHolderExcptionInput(graphene.InputObjectType):
    policy_holder_id = graphene.UUID(required=True)
    exception_reason = graphene.String()


class PHPortalUserCreateInput(graphene.InputObjectType, UserBase):
    trade_name = graphene.String(max_length=255, required=True)
    json_ext = graphene.types.json.JSONString(required=False)


class PHApprovalInput(graphene.InputObjectType):
    id = graphene.UUID(required=True)
    request_number = graphene.String(required=True)
    is_approved = graphene.Boolean(required=True)
    is_rejected = graphene.Boolean(required=True)
    is_rework = graphene.Boolean(required=True)
    rejected_reason = graphene.String(required=False)
    rework_option = graphene.String(required=False)
    rework_comment = graphene.String(required=False)
