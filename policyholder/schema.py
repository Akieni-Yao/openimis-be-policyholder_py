import graphene
import graphene_django_optimizer as gql_optimizer

from django.db.models import Q
from location.apps import LocationConfig
from core.schema import OrderedDjangoFilterConnectionField, signal_mutation_module_validate
from core.utils import append_validity_filter
from policyholder.models import PolicyHolder, PolicyHolderInsuree, PolicyHolderUser, \
    PolicyHolderContributionPlan, PolicyHolderMutation, PolicyHolderInsureeMutation, \
    PolicyHolderContributionPlanMutation, PolicyHolderUserMutation
from policyholder.gql.gql_mutations.create_mutations import CreatePolicyHolderMutation, \
    CreatePolicyHolderInsureeMutation, CreatePolicyHolderUserMutation, CreatePolicyHolderContributionPlanMutation
from policyholder.gql.gql_mutations.delete_mutations import DeletePolicyHolderMutation, \
    DeletePolicyHolderInsureeMutation, DeletePolicyHolderUserMutation, DeletePolicyHolderContributionPlanMutation
from policyholder.gql.gql_mutations.update_mutations import UpdatePolicyHolderMutation, \
    UpdatePolicyHolderInsureeMutation, UpdatePolicyHolderUserMutation, UpdatePolicyHolderContributionPlanMutation
from policyholder.gql.gql_mutations.replace_mutation import ReplacePolicyHolderInsureeMutation, \
    ReplacePolicyHolderContributionPlanMutation, ReplacePolicyHolderUserMutation

from policyholder.apps import PolicyholderConfig
from policyholder.services import PolicyHolder as PolicyHolderServices
from policyholder.gql.gql_types import PolicyHolderUserGQLType, PolicyHolderGQLType, PolicyHolderInsureeGQLType, \
    PolicyHolderContributionPlanGQLType

from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _

from payment.signals import signal_before_payment_query
from .signals import append_policy_holder_filter


class Query(graphene.ObjectType):
    policy_holder = OrderedDjangoFilterConnectionField(
        PolicyHolderGQLType,
        parent_location=graphene.String(),
        parent_location_level=graphene.Int(),
        orderBy=graphene.List(of_type=graphene.String),
        dateValidFrom__Gte=graphene.DateTime(),
        dateValidTo__Lte=graphene.DateTime(),
        applyDefaultValidityFilter=graphene.Boolean(),
    )

    policy_holder_insuree = OrderedDjangoFilterConnectionField(
        PolicyHolderInsureeGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        dateValidFrom__Gte=graphene.DateTime(),
        dateValidTo__Lte=graphene.DateTime(),
        applyDefaultValidityFilter=graphene.Boolean()
    )

    policy_holder_user = OrderedDjangoFilterConnectionField(
        PolicyHolderUserGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        dateValidFrom__Gte=graphene.DateTime(),
        dateValidTo__Lte=graphene.DateTime(),
        applyDefaultValidityFilter=graphene.Boolean()
    )

    policy_holder_contribution_plan_bundle = OrderedDjangoFilterConnectionField(
        PolicyHolderContributionPlanGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        dateValidFrom__Gte=graphene.DateTime(),
        dateValidTo__Lte=graphene.DateTime(),
        applyDefaultValidityFilter=graphene.Boolean()
    )
    validate_policy_holder_code = graphene.Field(
        graphene.Boolean,
        policy_holder_code=graphene.String(required=True),
        description="Checks that the specified policy holder code is unique."
    )

    def resolve_validate_policy_holder_code(self, info, **kwargs):
        if not info.context.user.has_perms(PolicyholderConfig.gql_query_policyholder_perms):
            raise PermissionDenied(_("unauthorized"))
        errors = PolicyHolderServices.check_unique_code_policy_holder(code=kwargs['policy_holder_code'])
        return False if errors else True


    def resolve_policy_holder(self, info, **kwargs):
        filters = []
        # go to process additional filter only when this arg of filter was passed into query
        if not info.context.user.has_perms(PolicyholderConfig.gql_query_policyholder_perms):
            # then check perms
            if info.context.user.has_perms(PolicyholderConfig.gql_query_policyholder_portal_perms):
                # check if user is linked to ph in policy holder user table
                if info.context.user.i_user_id:
                    from core import datetime
                    now = datetime.datetime.now()
                    uuids = PolicyHolderUser.objects.filter(
                        Q(user_id=info.context.user.id)
                    ).filter(
                        Q(date_valid_from__lte=now),
                        Q(date_valid_to__isnull=True) | Q(date_valid_to__gte=now),
                        Q(is_deleted=False)
                    ).values_list('policy_holder', flat=True).distinct()
                 
                    if uuids:
                        filters.append(Q(id__in=uuids))
                    else:
                        raise PermissionError("Unauthorized, no PolicyHolder found for this portal user")
                else:
                    raise PermissionError("Unauthorized, no active user")
            else:
                raise PermissionError("Unauthorized, user has neither policyholder perms nor policyholder portal perms")
        # if there is a filter it means that there is restricted permission found by a signal

        filters += append_validity_filter(**kwargs)
        parent_location = kwargs.get('parent_location')
        if parent_location is not None:
            parent_location_level = kwargs.get('parent_location_level')
            if parent_location_level is None:
                raise NotImplementedError("Missing parentLocationLevel argument when filtering on parentLocation")
            f = "uuid"
            for i in range(len(LocationConfig.location_types) - parent_location_level - 1):
                f = "parent__" + f
            f = "locations__" + f
            filters += [Q(**{f: parent_location})]
        return gql_optimizer.query(PolicyHolder.objects.filter(*filters).all(), info)

    def resolve_policy_holder_insuree(self, info, **kwargs):
        if not info.context.user.has_perms(PolicyholderConfig.gql_query_policyholderinsuree_perms):
            if not info.context.user.has_perms(PolicyholderConfig.gql_query_policyholderinsuree_portal_perms):
                raise PermissionError("Unauthorized")

        filters = append_validity_filter(**kwargs)
        query = PolicyHolderInsuree.objects
        return gql_optimizer.query(query.filter(*filters).all(), info)

    def resolve_policy_holder_user(self, info, **kwargs):
        if not info.context.user.has_perms(PolicyholderConfig.gql_query_policyholderuser_perms):
            if not info.context.user.has_perms(PolicyholderConfig.gql_query_policyholderuser_portal_perms):
                raise PermissionError("Unauthorized")

        filters = append_validity_filter(**kwargs)
        query = PolicyHolderUser.objects
        return gql_optimizer.query(query.filter(*filters).all(), info)

    def resolve_policy_holder_contribution_plan_bundle(self, info, **kwargs):
        if not info.context.user.has_perms(PolicyholderConfig.gql_query_policyholdercontributionplanbundle_perms):
            if not info.context.user.has_perms(PolicyholderConfig.gql_query_policyholdercontributionplanbundle_portal_perms):
                raise PermissionError("Unauthorized")

        filters = append_validity_filter(**kwargs)
        query = PolicyHolderContributionPlan.objects
        return gql_optimizer.query(query.filter(*filters).all(), info)


class Mutation(graphene.ObjectType):
    create_policy_holder = CreatePolicyHolderMutation.Field()
    create_policy_holder_insuree = CreatePolicyHolderInsureeMutation.Field()
    create_policy_holder_user = CreatePolicyHolderUserMutation.Field()
    create_policy_holder_contribution_plan_bundle = CreatePolicyHolderContributionPlanMutation.Field()
        
    update_policy_holder = UpdatePolicyHolderMutation.Field()
    update_policy_holder_insuree = UpdatePolicyHolderInsureeMutation.Field()
    update_policy_holder_user = UpdatePolicyHolderUserMutation.Field()
    update_policy_holder_contribution_plan_bundle = UpdatePolicyHolderContributionPlanMutation.Field()       
    
    delete_policy_holder = DeletePolicyHolderMutation.Field()
    delete_policy_holder_insuree = DeletePolicyHolderInsureeMutation.Field()
    delete_policy_holder_user = DeletePolicyHolderUserMutation.Field()
    delete_policy_holder_contribution_plan_bundle = DeletePolicyHolderContributionPlanMutation.Field()

    replace_policy_holder_insuree = ReplacePolicyHolderInsureeMutation.Field()
    replace_policy_holder_user = ReplacePolicyHolderUserMutation.Field()
    replace_policy_holder_contribution_plan_bundle = ReplacePolicyHolderContributionPlanMutation.Field()


def on_policy_holder_mutation(sender, **kwargs):
    uuid = kwargs['data'].get('uuid', None)
    if not uuid:
        return []
    if "PolicyHolderMutation" in str(sender._mutation_class):
        impacted_policy_holder = PolicyHolder.objects.get(id=uuid)
        PolicyHolderMutation.objects.create(
            policy_holder=impacted_policy_holder, mutation_id=kwargs['mutation_log_id'])
    if "PolicyHolderInsuree" in str(sender._mutation_class):
        impacted_policy_holder_insuree = PolicyHolderInsuree.objects.get(id=uuid)
        PolicyHolderInsureeMutation.objects.create(
            policy_holder_insuree=impacted_policy_holder_insuree, mutation_id=kwargs['mutation_log_id'])
    if "PolicyHolderContributionPlan" in str(sender._mutation_class):
        impacted_policy_holder_contribution_plan = PolicyHolderContributionPlan.objects.get(id=uuid)
        PolicyHolderContributionPlanMutation.objects.create(
            policy_holder_contribution_plan=impacted_policy_holder_contribution_plan, mutation_id=kwargs['mutation_log_id'])
    if "PolicyHolderUser" in str(sender._mutation_class):
        impacted_policy_holder_user = PolicyHolderUser.objects.get(id=uuid)
        PolicyHolderUserMutation.objects.create(
            policy_holder_user=impacted_policy_holder_user, mutation_id=kwargs['mutation_log_id'])
    return []


def bind_signals():
    signal_mutation_module_validate["policyholder"].connect(on_policy_holder_mutation)
    signal_before_payment_query.connect(append_policy_holder_filter)

