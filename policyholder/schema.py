import graphene
import graphene_django_optimizer as gql_optimizer
import calendar
import logging

from django.db.models import Q

from insuree.schema import CommonQueryType
from location.apps import LocationConfig
from core.schema import (
    OrderedDjangoFilterConnectionField,
    signal_mutation_module_validate,
)
from dateutil.relativedelta import relativedelta
from core.utils import append_validity_filter
from payment.gql_queries import PaymentPenaltyAndSanctionType, PaymentGQLType
from payment.models import PaymentPenaltyAndSanction, Payment
from policyholder.models import (
    ExceptionReason,
    PolicyHolder,
    PolicyHolderInsuree,
    PolicyHolderUser,
    PolicyHolderContributionPlan,
    PolicyHolderMutation,
    PolicyHolderInsureeMutation,
    PolicyHolderContributionPlanMutation,
    PolicyHolderUserMutation,
    PolicyHolderExcption,
    CategoryChange,
)
from policyholder.gql.gql_mutations.create_mutations import (
    CreateExceptionReasonMutation,
    CreatePolicyHolderMutation,
    CreatePolicyHolderInsureeMutation,
    CreatePolicyHolderUserMutation,
    CreatePolicyHolderContributionPlanMutation,
    CreatePolicyHolderExcption,
    CategoryChangeStatusChange,
    CreatePHPortalUserMutation,
)
from policyholder.gql.gql_mutations.delete_mutations import (
    DeleteExceptionReasonMutation,
    DeletePolicyHolderMutation,
    DeletePolicyHolderInsureeMutation,
    DeletePolicyHolderUserMutation,
    DeletePolicyHolderContributionPlanMutation,
)
from policyholder.gql.gql_mutations.update_mutations import (
    UpdateExceptionReasonMutation,
    UpdatePolicyHolderMutation,
    UpdatePolicyHolderInsureeMutation,
    UpdatePolicyHolderUserMutation,
    UpdatePolicyHolderContributionPlanMutation,
    UpdatePolicyHolderInsureeDesignation,
    PHApprovalMutation,
    # UnlockPolicyHolderMutation,
    VerifyUserAndUpdatePasswordMutation,
    NewPasswordRequestMutation,
)
from policyholder.gql.gql_mutations.replace_mutation import (
    ReplacePolicyHolderInsureeMutation,
    ReplacePolicyHolderContributionPlanMutation,
    ReplacePolicyHolderUserMutation,
)

from policyholder.apps import PolicyholderConfig
from policyholder.services import (
    assign_ph_exception_policy,
    PolicyHolder as PolicyHolderServices,
)
from policyholder.gql.gql_types import (
    ExceptionReasonGQLType,
    PolicyHolderUserGQLType,
    PolicyHolderGQLType,
    PolicyHolderInsureeGQLType,
    PolicyHolderContributionPlanGQLType,
    PolicyHolderByFamilyGQLType,
    PolicyHolderByInureeGQLType,
    NotDeclaredPolicyHolderGQLType,
    PolicyHolderExcptionType,
    CategoryChangeGQLType,
)

from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _

from payment.signals import signal_before_payment_query
from .constants import CC_WAITING_FOR_APPROVAL
from .signals import append_policy_holder_filter

from contract.models import Contract, ContractDetails
from datetime import datetime, timedelta
from graphql import GraphQLError

logger = logging.getLogger("openimis." + __name__)


class ApprovePolicyholderExceptionType(graphene.ObjectType):
    success = graphene.Boolean()
    message = graphene.String()


class Query(graphene.ObjectType):
    policy_holder = OrderedDjangoFilterConnectionField(
        PolicyHolderGQLType,
        parent_location=graphene.String(),
        parent_location_level=graphene.Int(),
        orderBy=graphene.List(of_type=graphene.String),
        dateValidFrom__Gte=graphene.DateTime(),
        dateValidTo__Lte=graphene.DateTime(),
        applyDefaultValidityFilter=graphene.Boolean(),
        contactName=graphene.String(),
        shortName=graphene.String(),
    )

    exception_reason = OrderedDjangoFilterConnectionField(
        ExceptionReasonGQLType,
        orderBy=graphene.List(of_type=graphene.String),
    )

    # can_unlock_policyholder = graphene.Field(
    #     success=graphene.Boolean,
    #     message=graphene.String,
    #     policyholder_id=graphene.String(required=True),
    # )

    policy_holder_by_family = OrderedDjangoFilterConnectionField(
        PolicyHolderInsureeGQLType,
        family_uuid=graphene.String(required=True),
        # active_or_last_expired_only=graphene.Boolean(),
        # show_history=graphene.Boolean(),
        # order_by=graphene.String(),
    )

    # def resolve_can_unlock_policyholder(self, info, **kwargs):
    #     # Fetch the policyholder
    #     policyholder_id = kwargs.get("policyholder_id")
    #     try:
    #         policyholder = PolicyHolder.objects.get(id=policyholder_id)
    #     except PolicyHolder.DoesNotExist:
    #         return UnlockPolicyHolderMutation(
    #             success=False, message="Policyholder does not exist."
    #         )

    #     # Query all payments associated with the policyholder's contracts
    #     payments = Payment.objects.filter(Q(contract__policy_holder__id=policyholder_id))

    #     # Check if any payments exist for the policyholder
    #     if not payments.exists():
    #         return UnlockPolicyHolderMutation(
    #             success=False, message="No payments found for this policyholder."
    #         )

    #     if payments.filter(~Q(status=1) & ~Q(status=5)).exists():
    #         return UnlockPolicyHolderMutation(
    #             success=False, message="Not all payments are fully paid."
    #         )

    #     # Check penalties of those payments: should have status 3 or 4, penalty_type 'Penalty', and is_approved=True
    #     penalties = PaymentPenaltyAndSanction.objects.filter(
    #         Q(payment__in=payments) & ~Q(status__in=[PaymentPenaltyAndSanction.PENALTY_APPROVED, PaymentPenaltyAndSanction.PENALTY_CANCELED, PaymentPenaltyAndSanction.INSTALLMENT_APPROVED])
    #     )

    #     # If penalties exist that are unresolved or not approved
    #     if penalties.exists():
    #         if not penalties.filter(is_approved=True).exists():
    #             return UnlockPolicyHolderMutation(
    #                 success=False, message="Penalties are not approved."
    #             )
    #         return UnlockPolicyHolderMutation(
    #             success=False, message="Penalties are not fully resolved."
    #         )

    #     return UnlockPolicyHolderMutation(
    #         success=True, message="Policyholder can be unlocked."
    #     )

    # def resolve_exception_reason(self, info, **kwargs):
    #     """
    #     Resolve the exception reason query.
    #     This method retrieves all exception reasons from the database.
    #     """

    #     filters = {}

    #     for key, value in kwargs.items():
    #         if value is not None:
    #             filters[key] = value

    #     exception_reasons =  ExceptionReason.objects.filter(**filters).all()
    #     return gql_optimizer.query(exception_reasons, info)

    def resolve_policy_holder_by_family(self, info, **kwargs):
        # family_uuid=kwargs.get('family_uuid')
        family_uuid = kwargs.pop("family_uuid")
        print("family_uuid : ", family_uuid)
        policy_holder_insuree = PolicyHolderInsuree.objects.filter(
            insuree__family__uuid=family_uuid, insuree__head=True
        ).all()
        # policy_holder_ids = [phi.policy_holder.id for phi in policy_holder_insuree]
        # print("policy_holder_ids : ", policy_holder_ids)
        # return gql_optimizer.query(PolicyHolder.objects.filter(id__in=policy_holder_ids).all(), info)
        return gql_optimizer.query(policy_holder_insuree.all(), info)

    policy_holder_by_insuree = OrderedDjangoFilterConnectionField(
        PolicyHolderInsureeGQLType,
        insuree_uuid=graphene.String(required=True),
        # active_or_last_expired_only=graphene.Boolean(),
        # show_history=graphene.Boolean(),
        # order_by=graphene.String(),
    )

    def resolve_policy_holder_by_insuree(self, info, **kwargs):
        # family_uuid=kwargs.get('family_uuid')
        insuree_uuid = kwargs.pop("insuree_uuid")
        print("insuree_uuid : ", insuree_uuid)
        policy_holder_insuree = PolicyHolderInsuree.objects.filter(
            insuree__uuid=insuree_uuid
        )
        # policy_holder_ids = [phi.policy_holder.id for phi in policy_holder_insuree]
        # print("policy_holder_ids : ", policy_holder_ids)
        # return gql_optimizer.query(PolicyHolder.objects.filter(id__in=policy_holder_ids).all(), info)
        return gql_optimizer.query(policy_holder_insuree.all(), info)

    policy_holder_insuree = OrderedDjangoFilterConnectionField(
        PolicyHolderInsureeGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        dateValidFrom__Gte=graphene.DateTime(),
        dateValidTo__Lte=graphene.DateTime(),
        applyDefaultValidityFilter=graphene.Boolean(),
        contract_id=graphene.UUID(required=False),
    )

    policy_holder_user = OrderedDjangoFilterConnectionField(
        PolicyHolderUserGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        dateValidFrom__Gte=graphene.DateTime(),
        dateValidTo__Lte=graphene.DateTime(),
        applyDefaultValidityFilter=graphene.Boolean(),
    )

    policy_holder_contribution_plan_bundle = OrderedDjangoFilterConnectionField(
        PolicyHolderContributionPlanGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        dateValidFrom__Gte=graphene.DateTime(),
        dateValidTo__Lte=graphene.DateTime(),
        applyDefaultValidityFilter=graphene.Boolean(),
    )
    validate_policy_holder_code = graphene.Field(
        graphene.Boolean,
        policy_holder_code=graphene.String(required=True),
        description="Checks that the specified policy holder code is unique.",
    )

    not_declared_policy_holder = OrderedDjangoFilterConnectionField(
        NotDeclaredPolicyHolderGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        dateContractFrom__Gte=graphene.DateTime(),
        dateContractTo__Lte=graphene.DateTime(),
        declared=graphene.Boolean(),
    )

    def resolve_not_declared_policy_holder(self, info, **kwargs):
        declared = kwargs.get("declared", None)
        dateContractFrom = kwargs.get("dateContractFrom__Gte", None)
        dateContractTo = kwargs.get("dateContractTo__Lte", None)

        if dateContractFrom is None:
            today = datetime.today()
            dateContractFrom = today.replace(day=1)
        print("dateContractFrom : ", dateContractFrom)

        if dateContractTo is None:
            today = datetime.today()
            _, last_day = calendar.monthrange(today.year, today.month)
            dateContractTo = today.replace(day=last_day)
        print("dateContractTo : ", dateContractTo)

        if dateContractFrom > dateContractTo:
            error = GraphQLError("Dates are not proper!", extensions={"code": 200})
            raise error

        contract_list = list(
            set(
                Contract.objects.filter(
                    date_valid_from__date__gte=dateContractFrom.date(),
                    date_valid_to__date__lte=dateContractTo.date(),
                    is_deleted=False,
                ).values_list("policy_holder__id", flat=True)
            )
        )
        print(contract_list)
        ph_object = None
        if declared:
            ph_object = PolicyHolder.objects.filter(
                id__in=contract_list, is_deleted=False
            ).all()
        else:
            ph_object = (
                PolicyHolder.objects.filter(is_deleted=False)
                .all()
                .exclude(id__in=contract_list)
            )
        return gql_optimizer.query(ph_object, info)

    approve_policyholder_exception = graphene.Field(
        ApprovePolicyholderExceptionType,
        id=graphene.Int(required=True),
        is_approved=graphene.Boolean(required=True),
        rejection_reason=graphene.String(required=False),
    )

    def resolve_approve_policyholder_exception(
        self, info, id, is_approved, rejection_reason
    ):
        from policy.models import Policy
        from contract.models import ContractPolicy
        from insuree.models import InsureeExcption
        from insuree.models import Family

        ph_exception = PolicyHolderExcption.objects.filter(id=id).first()
        if not ph_exception:
            return ApprovePolicyholderExceptionType(
                success=False, message="Exception Not Found!"
            )

        reason = ExceptionReason.objects.filter(id=ph_exception.reason.id).first()
        if not reason:
            return ApprovePolicyholderExceptionType(
                success=False, message="Exception Reason Not Found!"
            )
        ph_exception.status = "APPROVED" if is_approved else "REJECTED"
        if is_approved:
            ph_exception.is_used = True
            # approve exception
            ph_insurees = PolicyHolderInsuree.objects.filter(
                policy_holder=ph_exception.policy_holder,
                is_deleted=False,
            ).all()
            for ph_insuree in ph_insurees:
                print(f"=====> ph_insuree : {ph_insuree.insuree.status}")

                if not ph_insuree.insuree or not ph_insuree.insuree.family:
                    continue

                # if ph_insuree.insuree.status != "APPROVED":
                #     continue

                family = Family.objects.filter(id=ph_insuree.insuree.family.id).first()

                if not family:
                    continue

                ph_exception_started_at = ph_exception.started_at

                if not ph_exception.started_at:
                    ph_exception_started_at = ph_exception.created_time

                custom_filter = {
                    "status__in": [
                        Policy.STATUS_ACTIVE,
                        Policy.STATUS_READY,
                        Policy.STATUS_EXPIRED,
                    ],
                    "is_valid": True,
                    "family__id": family.id,
                    "expiry_date__month": ph_exception_started_at.month,
                    "expiry_date__year": ph_exception_started_at.year,
                }

                policy = (
                    Policy.objects.filter(**custom_filter)
                    .order_by("-expiry_date")
                    .first()
                )

                check_insuree_exception = InsureeExcption.objects.filter(
                    insuree=ph_insuree.insuree, is_used=True
                ).first()

                if check_insuree_exception:
                    continue

                if policy:
                    policy.initial_expiry_date = policy.expiry_date
                    policy.expiry_date = policy.expiry_date + relativedelta(
                        months=reason.period
                    )
                    policy.ph_exception = ph_exception
                    policy.save()
                    print(f"=====> policy : {policy.uuid}")

        else:
            ph_exception.rejection_reason = rejection_reason
        ph_exception.save()

        if is_approved:
            # remove all pending exceptions for this policy holder
            PolicyHolderExcption.objects.filter(
                policy_holder=ph_exception.policy_holder, status="PENDING"
            ).delete()

        return ApprovePolicyholderExceptionType(
            success=True, message="Exception Approved!"
        )

    category_change_requests = OrderedDjangoFilterConnectionField(
        CategoryChangeGQLType,
        orderBy=graphene.List(of_type=graphene.String),
    )

    def resolve_category_change_requests(self, info, **kwargs):
        order_by = kwargs.get("orderBy")
        query = CategoryChange.objects.all()
        if order_by:
            query = query.order_by(*order_by)
        return gql_optimizer.query(query, info)

    def resolve_validate_policy_holder_code(self, info, **kwargs):
        if not info.context.user.has_perms(
            PolicyholderConfig.gql_query_policyholder_perms
        ):
            raise PermissionDenied(_("unauthorized"))
        errors = PolicyHolderServices.check_unique_code_policy_holder(
            code=kwargs["policy_holder_code"]
        )
        return False if errors else True

    def resolve_policy_holder(self, info, **kwargs):
        filters = []
        # go to process additional filter only when this arg of filter was passed into query
        if not info.context.user.has_perms(
            PolicyholderConfig.gql_query_policyholder_perms
        ):
            # then check perms
            if info.context.user.has_perms(
                PolicyholderConfig.gql_query_policyholder_portal_perms
            ):
                # check if user is linked to ph in policy holder user table
                if info.context.user.i_user_id:
                    from core import datetime

                    now = datetime.datetime.now()
                    uuids = (
                        PolicyHolderUser.objects.filter(Q(user_id=info.context.user.id))
                        .filter(
                            Q(date_valid_from__lte=now),
                            Q(date_valid_to__isnull=True) | Q(date_valid_to__gte=now),
                            Q(is_deleted=False),
                        )
                        .values_list("policy_holder", flat=True)
                        .distinct()
                    )

                    if uuids:
                        filters.append(Q(id__in=uuids))
                    else:
                        raise PermissionError(
                            "Unauthorized, no PolicyHolder found for this portal user"
                        )
                else:
                    raise PermissionError("Unauthorized, no active user")
            else:
                raise PermissionError(
                    "Unauthorized, user has neither policyholder perms nor policyholder portal perms"
                )
        # if there is a filter it means that there is restricted permission found by a signal

        contact_name = kwargs.pop("contactName") if "contactName" in kwargs else None
        short_name = kwargs.pop("shortName") if "shortName" in kwargs else None

        filters += append_validity_filter(**kwargs)
        parent_location = kwargs.get("parent_location")
        if parent_location is not None:
            parent_location_level = kwargs.get("parent_location_level")
            if parent_location_level is None:
                raise NotImplementedError(
                    "Missing parentLocationLevel argument when filtering on parentLocation"
                )
            f = "uuid"
            for i in range(
                len(LocationConfig.location_types) - parent_location_level - 1
            ):
                f = "parent__" + f
            f = "locations__" + f
            filters += [Q(**{f: parent_location})]
        # return gql_optimizer.query(PolicyHolder.objects.filter(*filters).all(), info)

        queryset = PolicyHolder.objects.filter(*filters).all()

        if contact_name:
            queryset = queryset.filter(
                **{"contact_name__contactName__icontains": contact_name}
            )
        if short_name:
            queryset = queryset.filter(
                **{"json_ext__jsonExt__shortName__icontains": short_name}
            )
        return gql_optimizer.query(queryset, info)

    def resolve_policy_holder_insuree(self, info, **kwargs):
        if not info.context.user.has_perms(
            PolicyholderConfig.gql_query_policyholderinsuree_perms
        ):
            if not info.context.user.has_perms(
                PolicyholderConfig.gql_query_policyholderinsuree_portal_perms
            ):
                raise PermissionError("Unauthorized")

        contract_id = kwargs.pop("contract_id", None)

        filters = append_validity_filter(**kwargs)
        query = PolicyHolderInsuree.objects

        if contract_id:
            insuree_ids = ContractDetails.objects.filter(
                contract__id=contract_id, is_deleted=False
            ).values_list("insuree_id", flat=True)
            if insuree_ids:
                query = query.exclude(insuree_id__in=insuree_ids)

        if kwargs.get("insuree__id") is not None:
            query = query.filter(insuree__id=kwargs.get("insuree__id"))
        # # check validity_to is null
        # if kwargs.get("insuree__validity_to__isnull") is not None:
        #     print(f"******************* display kwargs : {kwargs} *******************")
        #     # query = query.filter(insuree__validity_to__isnull=True)
        #     kwargs.pop("insuree__validity_to__isnull")
        #     query = query.exclude(insuree__validity_to__isnull=True)

        return gql_optimizer.query(query.filter(*filters).all(), info)

    def resolve_policy_holder_user(self, info, **kwargs):
        # if not info.context.user.has_perms(PolicyholderConfig.gql_query_policyholderuser_perms):
        #     if not info.context.user.has_perms(PolicyholderConfig.gql_query_policyholderuser_portal_perms):
        #         raise PermissionError("Unauthorized")

        filters = append_validity_filter(**kwargs)
        query = PolicyHolderUser.objects
        return gql_optimizer.query(query.filter(*filters).all(), info)

    def resolve_policy_holder_contribution_plan_bundle(self, info, **kwargs):
        if not info.context.user.has_perms(
            PolicyholderConfig.gql_query_policyholdercontributionplanbundle_perms
        ):
            if not info.context.user.has_perms(
                PolicyholderConfig.gql_query_policyholdercontributionplanbundle_portal_perms
            ):
                raise PermissionError("Unauthorized")

        filters = append_validity_filter(**kwargs)
        # query = PolicyHolderContributionPlan.objects
        query = PolicyHolderContributionPlan.objects.filter(
            date_valid_to__isnull=True, is_deleted=False
        )
        return gql_optimizer.query(query.filter(*filters).all(), info)

    all_policyholder_exceptions = OrderedDjangoFilterConnectionField(
        PolicyHolderExcptionType,
        orderBy=graphene.List(of_type=graphene.String),
    )

    def resolve_all_policyholder_exceptions(self, info, **kwargs):
        order_by = kwargs.get("orderBy")
        query = PolicyHolderExcption.objects.all()
        if order_by:
            query = query.order_by(*order_by)
        return gql_optimizer.query(query, info)

    category_change_doc_upload = graphene.Field(
        CommonQueryType,
        code=graphene.String(required=True),
        document_provided=graphene.Boolean(required=True),
    )

    def resolve_category_change_doc_upload(self, info, **kwargs):
        code = kwargs.get("code")
        document_provided = kwargs.get("document_provided")
        cc_object = CategoryChange.objects.filter(code=code).first()
        if cc_object:
            if document_provided:
                cc_object.status = CC_WAITING_FOR_APPROVAL
                cc_object.save()
                return CommonQueryType(
                    success=True, message="Request Updated successfully!"
                )
            else:
                return CommonQueryType(success=False, message="Documents Not Provided!")
        else:
            return CommonQueryType(success=False, message="Request Not Found!")

    unpaid_declaration_by_policyholder = (
        graphene.List(  # Change to graphene.List to handle multiple contracts
            PaymentGQLType, policy_holder_id=graphene.String(required=True)
        )
    )

    def resolve_unpaid_declaration_by_policyholder(self, info, **kwargs):
        if not info.context.user.has_perms(
            PolicyholderConfig.gql_query_policyholdercontributionplanbundle_perms
        ):
            if not info.context.user.has_perms(
                PolicyholderConfig.gql_query_policyholdercontributionplanbundle_portal_perms
            ):
                raise PermissionError("Unauthorized")

        policy_holder_id = kwargs.get("policy_holder_id")
        if not policy_holder_id:
            raise ValueError("policy_holder_id is required.")

        payments_with_penalties = (
            Payment.objects.filter(
                contract__policy_holder=policy_holder_id,
                payments_penalty__isnull=False,  # Ensures there are penalties
            )
            .distinct()
            .order_by("contract__date_valid_from")[:3]
            # .order_by("-payment_date")[:3]
        )

        return gql_optimizer.query(payments_with_penalties, info)


class Mutation(graphene.ObjectType):
    create_policy_holder = CreatePolicyHolderMutation.Field()
    create_policy_holder_insuree = CreatePolicyHolderInsureeMutation.Field()
    create_policy_holder_user = CreatePolicyHolderUserMutation.Field()
    create_policy_holder_contribution_plan_bundle = (
        CreatePolicyHolderContributionPlanMutation.Field()
    )

    update_policy_holder = UpdatePolicyHolderMutation.Field()
    update_policy_holder_insuree = UpdatePolicyHolderInsureeMutation.Field()
    update_policy_holder_user = UpdatePolicyHolderUserMutation.Field()
    update_policy_holder_contribution_plan_bundle = (
        UpdatePolicyHolderContributionPlanMutation.Field()
    )

    delete_policy_holder = DeletePolicyHolderMutation.Field()
    delete_policy_holder_insuree = DeletePolicyHolderInsureeMutation.Field()
    delete_policy_holder_user = DeletePolicyHolderUserMutation.Field()
    delete_policy_holder_contribution_plan_bundle = (
        DeletePolicyHolderContributionPlanMutation.Field()
    )

    replace_policy_holder_insuree = ReplacePolicyHolderInsureeMutation.Field()
    replace_policy_holder_user = ReplacePolicyHolderUserMutation.Field()
    replace_policy_holder_contribution_plan_bundle = (
        ReplacePolicyHolderContributionPlanMutation.Field()
    )
    update_designation = UpdatePolicyHolderInsureeDesignation.Field()
    create_policy_holder_exception = CreatePolicyHolderExcption.Field()
    category_change_status_change = CategoryChangeStatusChange.Field()
    create_ph_portal_user = CreatePHPortalUserMutation.Field()
    policyholder_approval = PHApprovalMutation.Field()
    verify_user_and_update_password = VerifyUserAndUpdatePasswordMutation.Field()
    new_password_request = NewPasswordRequestMutation.Field()

    create_exception_reason = CreateExceptionReasonMutation.Field()
    update_exception_reason = UpdateExceptionReasonMutation.Field()
    delete_exception_reason = DeleteExceptionReasonMutation.Field()


def on_policy_holder_mutation(sender, **kwargs):
    uuid = kwargs["data"].get("uuid", None)
    if not uuid:
        return []
    if "PolicyHolderMutation" in str(sender._mutation_class):
        impacted_policy_holder = PolicyHolder.objects.get(id=uuid)
        PolicyHolderMutation.objects.create(
            policy_holder=impacted_policy_holder, mutation_id=kwargs["mutation_log_id"]
        )
    if "PolicyHolderInsuree" in str(sender._mutation_class):
        impacted_policy_holder_insuree = PolicyHolderInsuree.objects.get(id=uuid)
        PolicyHolderInsureeMutation.objects.create(
            policy_holder_insuree=impacted_policy_holder_insuree,
            mutation_id=kwargs["mutation_log_id"],
        )
    if "PolicyHolderContributionPlan" in str(sender._mutation_class):
        impacted_policy_holder_contribution_plan = (
            PolicyHolderContributionPlan.objects.get(id=uuid)
        )
        logger.info(
            f"===> impacted_policy_holder_contribution_plan : {impacted_policy_holder_contribution_plan}"
        )
        print(
            "=====>  impacted_policy_holder_contribution_plan  :  ",
            impacted_policy_holder_contribution_plan,
        )
        PolicyHolderContributionPlanMutation.objects.create(
            policy_holder_contribution_plan=impacted_policy_holder_contribution_plan,
            mutation_id=kwargs["mutation_log_id"],
        )
    if "PolicyHolderUser" in str(sender._mutation_class):
        impacted_policy_holder_user = PolicyHolderUser.objects.get(id=uuid)
        PolicyHolderUserMutation.objects.create(
            policy_holder_user=impacted_policy_holder_user,
            mutation_id=kwargs["mutation_log_id"],
        )
    return []


def bind_signals():
    signal_mutation_module_validate["policyholder"].connect(on_policy_holder_mutation)
    signal_before_payment_query.connect(append_policy_holder_filter)
