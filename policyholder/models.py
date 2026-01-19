import uuid

import core
from contribution_plan.models import ContributionPlanBundle
from django.conf import settings
from django.db import models
from core import models as core_models, fields
from graphql import ResolveInfo

from core.models import User
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
    code = models.CharField(db_column="PolicyHolderCode", max_length=32, null=True)
    trade_name = models.CharField(db_column="TradeName", max_length=255)
    locations = models.ForeignKey(
        Location,
        db_column="LocationsId",
        on_delete=models.deletion.DO_NOTHING,
        blank=True,
        null=True,
    )
    address = models.JSONField(db_column="Address", blank=True, null=True)
    phone = models.CharField(db_column="Phone", max_length=16, blank=True, null=True)
    fax = models.CharField(db_column="Fax", max_length=16, blank=True, null=True)
    email = models.CharField(db_column="Email", max_length=255, blank=True, null=True)
    contact_name = models.JSONField(db_column="ContactName", blank=True, null=True)
    legal_form = models.IntegerField(db_column="LegalForm", blank=True, null=True)
    activity_code = models.IntegerField(db_column="ActivityCode", blank=True, null=True)
    accountancy_account = models.CharField(
        db_column="AccountancyAccount", max_length=64, blank=True, null=True
    )
    bank_account = models.JSONField(db_column="bankAccount", blank=True, null=True)
    payment_reference = models.CharField(
        db_column="PaymentReference", max_length=128, blank=True, null=True
    )
    is_approved = models.BooleanField(db_column="IsApproved", default=False)
    is_review = models.BooleanField(db_column="IsReview", default=False)
    is_submit = models.BooleanField(db_column="IsSubmit", default=False)
    request_number = models.CharField(
        db_column="RequestNumber", max_length=255, null=True
    )
    form_ims = models.BooleanField(db_column="FormIMS", default=False)
    form_ph_portal = models.BooleanField(db_column="FormPhPortal", default=False)
    status = models.CharField(db_column="Status", max_length=255, blank=True, null=True)
    is_rejected = models.BooleanField(db_column="IsRejected", default=False)
    rejected_reason = models.CharField(
        db_column="RejectedReason", max_length=255, blank=True, null=True
    )
    is_rework = models.BooleanField(db_column="IsRework", default=False)
    rework_option = models.CharField(
        db_column="ReworkOption", max_length=255, blank=True, null=True
    )
    rework_comment = models.CharField(
        db_column="ReworkComment", max_length=255, blank=True, null=True
    )
    erp_partner_id = models.IntegerField(
        db_column="ErpPartnerID", blank=True, null=True
    )
    erp_partner_access_id = models.CharField(
        db_column="ErpPartnerAccessID", max_length=255, blank=True, null=True
    )
    is_blocked = models.BooleanField(db_column="IsBlocked", default=False)

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
        db_table = "tblPolicyHolder"


class PolicyHolderInsureeManager(core_models.HistoryModelManager):
    def filter(self, *args, **kwargs):
        keys = [x for x in kwargs if "itemsvc" in x]
        for key in keys:
            new_key = key.replace("itemsvc", self.model.model_prefix)
            kwargs[new_key] = kwargs.pop(key)
        return super(PolicyHolderInsureeManager, self).filter(*args, **kwargs)


class PolicyHolderInsuree(core_models.HistoryBusinessModel):
    policy_holder = models.ForeignKey(
        PolicyHolder, db_column="PolicyHolderId", on_delete=models.deletion.DO_NOTHING
    )
    insuree = models.ForeignKey(
        Insuree, db_column="InsureeId", on_delete=models.deletion.DO_NOTHING
    )
    contribution_plan_bundle = models.ForeignKey(
        ContributionPlanBundle,
        db_column="ContributionPlanBundleId",
        on_delete=models.deletion.DO_NOTHING,
        blank=True,
        null=True,
    )
    user = models.ForeignKey(
        User,
        db_column="PortalUser",
        on_delete=models.deletion.DO_NOTHING,
        blank=True,
        null=True,
    )
    last_policy = models.ForeignKey(
        Policy,
        db_column="LastPolicyId",
        on_delete=models.deletion.DO_NOTHING,
        blank=True,
        null=True,
    )
    is_payment_done_by_policy_holder = models.BooleanField(
        db_column="IsPaymentDoneByPolicyHolder", default=False
    )
    is_rights_enable_for_insuree = models.BooleanField(
        db_column="IsRightsEnableForInsuree", default=False
    )
    employer_number = models.CharField(
        db_column="EmployerNumber", blank=True, null=True, max_length=50
    )
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
        db_table = "tblPolicyHolderInsuree"


class PolicyHolderContributionPlanManager(core_models.HistoryModelManager):
    def filter(self, *args, **kwargs):
        keys = [x for x in kwargs if "itemsvc" in x]
        for key in keys:
            new_key = key.replace("itemsvc", self.model.model_prefix)
            kwargs[new_key] = kwargs.pop(key)
        return super(PolicyHolderContributionPlanManager, self).filter(*args, **kwargs)


class PolicyHolderContributionPlan(core_models.HistoryBusinessModel):
    policy_holder = models.ForeignKey(
        PolicyHolder, db_column="PolicyHolderId", on_delete=models.deletion.DO_NOTHING
    )
    contribution_plan_bundle = models.ForeignKey(
        ContributionPlanBundle,
        db_column="ContributionPlanBundleId",
        on_delete=models.deletion.DO_NOTHING,
    )

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
        db_table = "tblPolicyHolderContributionPlan"


class PolicyHolderUserManager(core_models.HistoryModelManager):
    def filter(self, *args, **kwargs):
        keys = [x for x in kwargs if "itemsvc" in x]
        for key in keys:
            new_key = key.replace("itemsvc", self.model.model_prefix)
            kwargs[new_key] = kwargs.pop(key)
        return super(PolicyHolderUserManager, self).filter(*args, **kwargs)


class PolicyHolderUser(core_models.HistoryBusinessModel):
    user = models.ForeignKey(
        core_models.User, db_column="UserID", on_delete=models.deletion.DO_NOTHING
    )
    policy_holder = models.ForeignKey(
        PolicyHolder, db_column="PolicyHolderId", on_delete=models.deletion.DO_NOTHING
    )

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
        db_table = "tblPolicyHolderUser"


class PolicyHolderMutation(core_models.UUIDModel, core_models.ObjectMutation):
    policyholder = models.ForeignKey(
        PolicyHolder,
        models.DO_NOTHING,
        db_column="policy_holder_id",
        related_name="mutations",
    )
    mutation = models.ForeignKey(
        core_models.MutationLog, models.DO_NOTHING, related_name="policy_holder"
    )

    class Meta:
        managed = True
        db_table = "policy_holder_PolicyHolderMutation"


class PolicyHolderInsureeMutation(core_models.UUIDModel):
    policy_holder_insuree = models.ForeignKey(
        PolicyHolderInsuree, models.DO_NOTHING, related_name="mutations"
    )
    mutation = models.ForeignKey(
        core_models.MutationLog, models.DO_NOTHING, related_name="policy_holder_insuree"
    )

    class Meta:
        managed = True
        db_table = "policy_holder_insuree_PolicyHolderInsureeMutation"


class PolicyHolderContributionPlanMutation(core_models.UUIDModel):
    policy_holder_contribution_plan = models.ForeignKey(
        PolicyHolderContributionPlan, models.DO_NOTHING, related_name="mutations"
    )
    mutation = models.ForeignKey(
        core_models.MutationLog,
        models.DO_NOTHING,
        related_name="policy_holder_contribution_plan",
    )

    class Meta:
        managed = True
        db_table = (
            "policy_holder_contribution_plan_PolicyHolderContributionPlanMutation"
        )


class PolicyHolderUserMutation(core_models.UUIDModel):
    policy_holder_user = models.ForeignKey(
        PolicyHolderUser, models.DO_NOTHING, related_name="mutations"
    )
    mutation = models.ForeignKey(
        core_models.MutationLog, models.DO_NOTHING, related_name="policy_holder_user"
    )

    class Meta:
        managed = True
        db_table = "policy_holder_user_PolicyHolderUserMutation"


class ExceptionReason(models.Model):
    id = models.AutoField(db_column="ID", primary_key=True)
    reason = models.CharField(db_column="reason", max_length=255, null=True)
    period = models.IntegerField(db_column="period")
    # scope could be insuree or policy holder
    scope = models.CharField(db_column="scopeReason", max_length=50, null=True)

    created_at = models.DateTimeField(db_column="CreatedTime", auto_now_add=True)
    modified_at = models.DateTimeField(db_column="ModifiedTime", auto_now=True)

    class Meta:
        managed = True
        db_table = "tblExceptionReason"


class PolicyHolderExcption(models.Model):
    id = models.AutoField(db_column="InsureeExptionID", primary_key=True)
    policy_holder = models.ForeignKey(
        PolicyHolder, on_delete=models.DO_NOTHING, db_column="PolicyHolder"
    )
    reason = models.ForeignKey(
        ExceptionReason, on_delete=models.DO_NOTHING, db_column="reason", null=True
    )
    code = models.CharField(db_column="ExceptionCode", max_length=255, null=True)
    status = models.CharField(db_column="Status", max_length=255, null=True)
    exception_reason = models.CharField(
        db_column="ExceptionReason", max_length=255, null=True
    )
    rejection_reason = models.CharField(
        db_column="RejectionReason", max_length=255, null=True
    )
    is_used = models.BooleanField(db_column="IsUsed", default=False)
    month = models.CharField(db_column="Month", max_length=255, null=True)
    contract_id = models.UUIDField(db_column="ContractId", editable=False, null=True)
    created_by = models.CharField(db_column="CreatedBy", max_length=56, null=True)
    modified_by = models.CharField(db_column="ModifiedBy", max_length=56, null=True)
    started_at = models.DateTimeField(db_column="StartedAt", null=True)
    ended_at = models.DateTimeField(db_column="EndedAt", null=True)
    created_time = models.DateTimeField(
        db_column="CreatedTime", auto_now_add=True, null=True
    )
    modified_time = models.DateTimeField(
        db_column="ModifiedTime", auto_now=True, null=True
    )

    class Meta:
        managed = True
        db_table = "tblPolicyHolderException"


class CategoryChange(models.Model):
    id = models.AutoField(db_column="ID", primary_key=True)
    code = models.CharField(db_column="Code", max_length=256)
    insuree = models.ForeignKey(
        Insuree, on_delete=models.DO_NOTHING, db_column="Insuree"
    )
    old_category = models.CharField(db_column="OldCategory", max_length=256, null=True)
    new_category = models.CharField(db_column="NewCategory", max_length=256)
    policy_holder = models.ForeignKey(
        PolicyHolder, on_delete=models.DO_NOTHING, db_column="PolicyHolder"
    )
    request_type = models.CharField(db_column="RequestType", max_length=256)
    status = models.CharField(db_column="Status", max_length=256)
    rejected_reason = models.CharField(db_column="Reason", max_length=256, null=True)
    json_ext = models.JSONField(db_column="JsonExt", blank=True, null=True)
    created_by = models.ForeignKey(
        core_models.User,
        on_delete=models.DO_NOTHING,
        db_column="CreatedBy",
        related_name="created_by_user",
        null=True,
    )
    modified_by = models.ForeignKey(
        core_models.User,
        on_delete=models.DO_NOTHING,
        db_column="modified_by",
        related_name="modified_by_user",
        null=True,
    )
    created_time = models.DateTimeField(db_column="CreatedTime", auto_now_add=True)
    modified_time = models.DateTimeField(db_column="ModifiedTime", auto_now=True)

    class Meta:
        managed = True
        db_table = "tblCategoryChange"


class PolicyHolderUserPending(models.Model):
    id = models.AutoField(db_column="ID", primary_key=True)
    user = models.ForeignKey(
        core_models.User, db_column="UserID", on_delete=models.deletion.DO_NOTHING
    )
    policy_holder = models.ForeignKey(
        PolicyHolder, db_column="PolicyHolderId", on_delete=models.deletion.DO_NOTHING
    )

    class Meta:
        managed = True
        db_table = "tblPolicyHolderUserPending"


class PolicyHolderInsureeBatchUpload(core_models.UUIDModel):
    """
    Model to track policyholder insuree import progress.
    """
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    policy_holder = models.ForeignKey(
        PolicyHolder,
        on_delete=models.CASCADE,
        db_column="PolicyHolderUUID",
        related_name="insuree_batch_uploads",
    )

    input_file_name = models.CharField(
        max_length=255,
        db_column="InputFileName",
        help_text="Original uploaded file name",
    )
    results = models.JSONField(
        null=True,
        blank=True,
        db_column="Results",
        help_text="Row-specific results stored as JSON array with ligne, nom, prenom, numero_camu, Etat, remarque",
    )

    celery_task_id = models.CharField(
        max_length=255,
        db_column="CeleryTaskID",
        unique=True,
        blank=True,
        null=True,
        help_text="Celery AsyncResult task ID",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_column="Status",
    )

    total_rows = models.IntegerField(
        default=0,
        db_column="TotalRows",
        help_text="Total rows to process (excluding header)",
    )
    processed_rows = models.IntegerField(
        default=0,
        db_column="ProcessedRows",
        help_text="Number of rows processed so far",
    )
    success_count = models.IntegerField(
        default=0,
        db_column="SuccessCount",
        help_text="Number of successfully processed rows",
    )
    error_count = models.IntegerField(
        default=0, db_column="ErrorCount", help_text="Number of rows with errors"
    )

    started_at = models.DateTimeField(null=True, blank=True, db_column="StartedAt")
    completed_at = models.DateTimeField(null=True, blank=True, db_column="CompletedAt")

    error_message = models.TextField(
        null=True,
        blank=True,
        db_column="ErrorMessage",
        help_text="Error message if status is FAILED",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        db_column="CreatedBy",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column="CreatedAt")
    updated_at = models.DateTimeField(auto_now=True, db_column="UpdatedAt")

    class Meta:
        managed = True
        db_table = "policyholder_PolicyHolderInsureeBatchUpload"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["celery_task_id"]),
            models.Index(fields=["policy_holder", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"PolicyHolderInsureeUpload-{self.id} ({self.status})"

    @property
    def progress_percentage(self):
        """Calculate progress percentage (0-100)"""
        if self.total_rows == 0:
            return 0
        return int((self.processed_rows / self.total_rows) * 100)

    @property
    def is_complete(self):
        """Check if processing is complete"""
        return self.status in [self.Status.COMPLETED, self.Status.FAILED]

    @property
    def duration_seconds(self):
        """Calculate duration in seconds"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def mark_as_processing(self, total_rows):
        """Mark batch as processing with total row count"""
        from django.utils import timezone

        self.status = self.Status.PROCESSING
        self.total_rows = total_rows
        self.started_at = timezone.now()
        self.save(update_fields=["status", "total_rows", "started_at", "updated_at"])

    def update_progress(self, processed_rows, success_count=None, error_count=None):
        """Update progress counters"""
        self.processed_rows = processed_rows
        if success_count is not None:
            self.success_count = success_count
        if error_count is not None:
            self.error_count = error_count
        self.save(
            update_fields=[
                "processed_rows",
                "success_count",
                "error_count",
                "updated_at",
            ]
        )

    def mark_as_completed(self):
        """Mark batch as completed"""
        from django.utils import timezone

        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])

    def mark_as_failed(self, error_message):
        """Mark batch as failed with error message"""
        from django.utils import timezone

        self.status = self.Status.FAILED
        self.completed_at = timezone.now()
        self.error_message = error_message
        self.save(
            update_fields=["status", "completed_at", "error_message", "updated_at"]
        )


class PolicyHolderInsureeUploadedFile(core_models.UUIDModel):
    """
    Model to track uploaded files for policyholder insuree imports.
    Files are stored in S3 bucket.
    """
    policy_holder = models.ForeignKey(
        PolicyHolder,
        on_delete=models.deletion.CASCADE,
        db_column="PolicyHolderUUID",
        related_name="insuree_uploaded_files",
    )
    file_name_hash = models.CharField(max_length=255, db_column="FileNameHash")
    file_path = models.CharField(
        max_length=255, db_column="FilePath", null=True, blank=True
    )

    class Meta:
        managed = True
        db_table = "policyholder_PolicyHolderInsureeUploadedFile"

    def __str__(self):
        return f"PolicyHolderInsureeUploadedFile-{self.id}"
