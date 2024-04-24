import uuid

import core
from contribution_plan.models import ContributionPlanBundle
from django.conf import settings
from django.db import models
from core import models as core_models, fields
from graphql import ResolveInfo
from location.models import Location, UserDistrict
from insuree.models import Insuree
from policy.models import Policy


class PolicyHolderManager(core_models.HistoryModelManager):
    def filter(self, *args, **kwargs):
        keys = [x for x in kwargs if "itemsvc" in x]
        for key in keys:
            new_key = key.replace("itemsvc", self.model.model_prefix)
            kwargs[new_key] = kwargs.pop(key)
        return super(PolicyHolderManager, self).filter(*args, **kwargs)


class PolicyHolder(core_models.HistoryBusinessModel):
    code = models.CharField(db_column='PolicyHolderCode', max_length=32, null=True)
    trade_name = models.CharField(db_column='TradeName', max_length=255)
    locations = models.ForeignKey(Location, db_column='LocationsId', on_delete=models.deletion.DO_NOTHING, blank=True, null=True)
    address = models.JSONField(db_column='Address', blank=True, null=True)
    phone = models.CharField(db_column='Phone', max_length=16, blank=True, null=True)
    fax = models.CharField(db_column='Fax', max_length=16, blank=True, null=True)
    email = models.CharField(db_column='Email', max_length=255, blank=True, null=True)
    contact_name = models.JSONField(db_column='ContactName', blank=True, null=True)
    legal_form = models.IntegerField(db_column='LegalForm', blank=True, null=True)
    activity_code = models.IntegerField(db_column='ActivityCode', blank=True, null=True)
    accountancy_account = models.CharField(db_column='AccountancyAccount', max_length=64, blank=True, null=True)
    bank_account = models.JSONField(db_column="bankAccount", blank=True, null=True)
    payment_reference = models.CharField(db_column='PaymentReference', max_length=128, blank=True, null=True)
    is_approved = models.BooleanField(db_column="IsApproved", default=False)
    is_review = models.BooleanField(db_column="IsReview", default=False)
    is_submit = models.BooleanField(db_column="IsSubmit", default=False)
    request_number = models.CharField(db_column='RequestNumber', max_length=255, null=True)
    form_ims = models.BooleanField(db_column="FormIMS", default=False)

    objects = PolicyHolderManager()

    @classmethod
    def get_queryset(cls, queryset, user):
        queryset = cls.filter_queryset(queryset)
        if isinstance(user, ResolveInfo):
            user = user.context.user
        if settings.ROW_SECURITY and user.is_anonymous:
            return queryset.filter(id=None)
        if settings.ROW_SECURITY:
            dist = UserDistrict.get_user_districts(user._u)
            return queryset.filter(
                locations__parent__parent_id__in=[l.location_id for l in dist]
            )
        return queryset

    class Meta:
        db_table = 'tblPolicyHolder'


class PolicyHolderInsureeManager(core_models.HistoryModelManager):
    def filter(self, *args, **kwargs):
        keys = [x for x in kwargs if "itemsvc" in x]
        for key in keys:
            new_key = key.replace("itemsvc", self.model.model_prefix)
            kwargs[new_key] = kwargs.pop(key)
        return super(PolicyHolderInsureeManager, self).filter(*args, **kwargs)


class PolicyHolderInsuree(core_models.HistoryBusinessModel):
    policy_holder = models.ForeignKey(PolicyHolder, db_column='PolicyHolderId',
                                      on_delete=models.deletion.DO_NOTHING)
    insuree = models.ForeignKey(Insuree, db_column='InsureeId',
                                on_delete=models.deletion.DO_NOTHING)
    contribution_plan_bundle = models.ForeignKey(ContributionPlanBundle, db_column='ContributionPlanBundleId',
                                                 on_delete=models.deletion.DO_NOTHING, blank=True, null=True)
    last_policy = models.ForeignKey(Policy, db_column='LastPolicyId', on_delete=models.deletion.DO_NOTHING, blank=True, null=True)
    is_payment_done_by_policy_holder = models.BooleanField(db_column='IsPaymentDoneByPolicyHolder', default=False)
    is_rights_enable_for_insuree = models.BooleanField(db_column='IsRightsEnableForInsuree', default=False)
    employer_number = models.CharField(db_column='EmployerNumber', blank=True, null=True, max_length=50)
    objects = PolicyHolderInsureeManager()

    @classmethod
    def get_queryset(cls, queryset, user):
        queryset = cls.filter_queryset(queryset)
        if isinstance(user, ResolveInfo):
            user = user.context.user
        if settings.ROW_SECURITY and user.is_anonymous:
            return queryset.filter(id=None)
        if settings.ROW_SECURITY:
            pass
        return queryset

    class Meta:
        db_table = 'tblPolicyHolderInsuree'


class PolicyHolderContributionPlanManager(core_models.HistoryModelManager):
    def filter(self, *args, **kwargs):
        keys = [x for x in kwargs if "itemsvc" in x]
        for key in keys:
            new_key = key.replace("itemsvc", self.model.model_prefix)
            kwargs[new_key] = kwargs.pop(key)
        return super(PolicyHolderContributionPlanManager, self).filter(*args, **kwargs)


class PolicyHolderContributionPlan(core_models.HistoryBusinessModel):
    policy_holder = models.ForeignKey(PolicyHolder, db_column='PolicyHolderId',
                                      on_delete=models.deletion.DO_NOTHING)
    contribution_plan_bundle = models.ForeignKey(ContributionPlanBundle, db_column='ContributionPlanBundleId',
                                                 on_delete=models.deletion.DO_NOTHING)

    objects = PolicyHolderContributionPlanManager()

    @classmethod
    def get_queryset(cls, queryset, user):
        queryset = cls.filter_queryset(queryset)
        if isinstance(user, ResolveInfo):
            user = user.context.user
        if settings.ROW_SECURITY and user.is_anonymous:
            return queryset.filter(id=None)
        if settings.ROW_SECURITY:
            pass
        return queryset

    class Meta:
        db_table = 'tblPolicyHolderContributionPlan'


class PolicyHolderUserManager(core_models.HistoryModelManager):
    def filter(self, *args, **kwargs):
        keys = [x for x in kwargs if "itemsvc" in x]
        for key in keys:
            new_key = key.replace("itemsvc", self.model.model_prefix)
            kwargs[new_key] = kwargs.pop(key)
        return super(PolicyHolderUserManager, self).filter(*args, **kwargs)


class PolicyHolderUser(core_models.HistoryBusinessModel):
    user = models.ForeignKey(core_models.User, db_column='UserID',
                                                 on_delete=models.deletion.DO_NOTHING)
    policy_holder = models.ForeignKey(PolicyHolder, db_column='PolicyHolderId',
                                      on_delete=models.deletion.DO_NOTHING)

    objects = PolicyHolderUserManager()

    @classmethod
    def get_queryset(cls, queryset, user):
        queryset = cls.filter_queryset(queryset)
        if isinstance(user, ResolveInfo):
            user = user.context.user
        if settings.ROW_SECURITY and user.is_anonymous:
            return queryset.filter(id=None)
        if settings.ROW_SECURITY:
            pass
        return queryset

    class Meta:
        db_table = 'tblPolicyHolderUser'


class PolicyHolderMutation(core_models.UUIDModel, core_models.ObjectMutation):
    policyholder = models.ForeignKey(PolicyHolder, models.DO_NOTHING, db_column="policy_holder_id",
                                 related_name='mutations')
    mutation = models.ForeignKey(
        core_models.MutationLog, models.DO_NOTHING, related_name='policy_holder')

    class Meta:
        managed = True
        db_table = "policy_holder_PolicyHolderMutation"


class PolicyHolderInsureeMutation(core_models.UUIDModel):
    policy_holder_insuree = models.ForeignKey(PolicyHolderInsuree, models.DO_NOTHING,
                                 related_name='mutations')
    mutation = models.ForeignKey(
        core_models.MutationLog, models.DO_NOTHING, related_name='policy_holder_insuree')

    class Meta:
        managed = True
        db_table = "policy_holder_insuree_PolicyHolderInsureeMutation"


class PolicyHolderContributionPlanMutation(core_models.UUIDModel):
    policy_holder_contribution_plan = models.ForeignKey(PolicyHolderContributionPlan, models.DO_NOTHING,
                                 related_name='mutations')
    mutation = models.ForeignKey(
        core_models.MutationLog, models.DO_NOTHING, related_name='policy_holder_contribution_plan')

    class Meta:
        managed = True
        db_table = "policy_holder_contribution_plan_PolicyHolderContributionPlanMutation"


class PolicyHolderUserMutation(core_models.UUIDModel):
    policy_holder_user = models.ForeignKey(PolicyHolderUser, models.DO_NOTHING,
                                 related_name='mutations')
    mutation = models.ForeignKey(
        core_models.MutationLog, models.DO_NOTHING, related_name='policy_holder_user')

    class Meta:
        managed = True
        db_table = "policy_holder_user_PolicyHolderUserMutation"


class PolicyHolderExcption(models.Model):
    id = models.AutoField(db_column='InsureeExptionID', primary_key=True)
    policy_holder = models.ForeignKey(PolicyHolder, on_delete=models.DO_NOTHING,
                                db_column='PolicyHolder')
    code = models.CharField(db_column='ExceptionCode',  max_length=255, null=True)
    status = models.CharField(db_column='Status', max_length=255, null=True)
    exception_reason = models.CharField(db_column='ExceptionReason', max_length=255, null=True)
    rejection_reason = models.CharField(db_column='RejectionReason', max_length=255, null=True)
    is_used = models.BooleanField(db_column='IsUsed', default=False)
    month = models.CharField(db_column='Month', max_length=255, null=True)
    contract_id = models.UUIDField(db_column="ContractId", editable=False, null=True)
    created_by = models.CharField(db_column='CreatedBy', max_length=56, null=True)
    modified_by = models.CharField(db_column='ModifiedBy', max_length=56, null=True)
    created_time = models.DateTimeField(db_column='CreatedTime', auto_now_add=True, null=True)
    modified_time = models.DateTimeField(db_column='ModifiedTime', auto_now=True, null=True)


    class Meta:
        managed = True
        db_table = 'tblPolicyHolderException'


class CategoryChange(models.Model):
    id = models.AutoField(db_column='ID', primary_key=True)
    code = models.CharField(db_column='Code', max_length=256)
    insuree = models.ForeignKey(Insuree, on_delete=models.DO_NOTHING, db_column='Insuree')
    old_category = models.CharField(db_column='OldCategory', max_length=256, null=True)
    new_category = models.CharField(db_column='NewCategory', max_length=256)
    policy_holder = models.ForeignKey(PolicyHolder, on_delete=models.DO_NOTHING, db_column='PolicyHolder')
    request_type = models.CharField(db_column='RequestType', max_length=256)
    status = models.CharField(db_column='Status', max_length=256)
    rejected_reason = models.CharField(db_column='Reason', max_length=256, null=True)
    json_ext = models.JSONField(db_column="JsonExt", blank=True, null=True)
    created_by = models.ForeignKey(core_models.User, on_delete=models.DO_NOTHING, db_column='CreatedBy', related_name ='created_by_user', null=True)
    modified_by = models.ForeignKey(core_models.User, on_delete=models.DO_NOTHING, db_column='modified_by', related_name='modified_by_user', null=True)
    created_time = models.DateTimeField(db_column='CreatedTime', auto_now_add=True)
    modified_time = models.DateTimeField(db_column='ModifiedTime', auto_now=True)
    
    class Meta:
        managed = True
        db_table = 'tblCategoryChange'
