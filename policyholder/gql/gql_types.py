import graphene
from django_filters import CharFilter, FilterSet

from contribution_plan.gql import ContributionPlanBundleGQLType
from core import prefix_filterset, ExtendedConnection
from core.gql_queries import UserGQLType
from graphene_django import DjangoObjectType
from insuree.schema import InsureeGQLType
from location.gql_queries import LocationGQLType

from policyholder.models import PolicyHolder, PolicyHolderInsuree, PolicyHolderUser, PolicyHolderContributionPlan, \
    PolicyHolderMutation, PolicyHolderExcption, CategoryChange


class PolicyHolderGQLType(DjangoObjectType):
    class Meta:
        model = PolicyHolder
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "code": ["exact", "istartswith", "icontains", "iexact"],
            "version": ["exact"],
            "trade_name": ["exact", "istartswith", "icontains", "iexact"],
            **prefix_filterset("locations__", LocationGQLType._meta.filter_fields),
            "phone": ["exact", "istartswith", "icontains", "iexact"],
            "fax": ["exact", "istartswith", "icontains", "iexact"],
            "email": ["exact", "istartswith", "icontains", "iexact"],
            "legal_form": ["exact"],
            "activity_code": ["exact"],
            "accountancy_account": ["exact"],
            "payment_reference": ["exact"],
            "date_created": ["exact", "lt", "lte", "gt", "gte"],
            "date_updated": ["exact", "lt", "lte", "gt", "gte"],
            "is_deleted": ["exact"],
            "request_number": ["exact", "istartswith", "icontains", "iexact"],
            "status": ["exact", "istartswith", "icontains", "iexact"],
            "form_ph_portal": ["exact"],
            "is_approved": ["exact"],
            "is_review": ["exact"],
            "is_submit": ["exact"],
            "is_rejected": ["exact"],
            "is_rework": ["exact"]
        }

        connection_class = ExtendedConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        return PolicyHolder.get_queryset(queryset, info)
    
class ExceptionReasonGQLType(DjangoObjectType):
    class Meta:
        model = PolicyHolderExcption
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "exception_reason": ["exact", "istartswith", "icontains", "iexact"],
            "period": ["exact"],
            "scope": ["exact", "istartswith", "icontains", "iexact"],
            "created_at": ["exact", "lt", "lte", "gt", "gte"],
            "modified_at": ["exact", "lt", "lte", "gt", "gte"]
        }

        connection_class = ExtendedConnection


class PolicyHolderByFamilyGQLType(DjangoObjectType):
    class Meta:
        model = PolicyHolder
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "code": ["exact", "istartswith", "icontains", "iexact"],
            "version": ["exact"],
            "trade_name": ["exact", "istartswith", "icontains", "iexact"],
            "phone": ["exact", "istartswith", "icontains", "iexact"],
            "fax": ["exact", "istartswith", "icontains", "iexact"],
            "email": ["exact", "istartswith", "icontains", "iexact"],
            "legal_form": ["exact"],
            "activity_code": ["exact"],
            "accountancy_account": ["exact"],
            "payment_reference": ["exact"],
            "date_created": ["exact", "lt", "lte", "gt", "gte"],
            "date_updated": ["exact", "lt", "lte", "gt", "gte"],
            "is_deleted": ["exact"]
        }

        connection_class = ExtendedConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        return PolicyHolder.get_queryset(queryset, info)


class PolicyHolderByInureeGQLType(DjangoObjectType):
    class Meta:
        model = PolicyHolder
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "code": ["exact", "istartswith", "icontains", "iexact"],
            "version": ["exact"],
            "trade_name": ["exact", "istartswith", "icontains", "iexact"],
            "phone": ["exact", "istartswith", "icontains", "iexact"],
            "fax": ["exact", "istartswith", "icontains", "iexact"],
            "email": ["exact", "istartswith", "icontains", "iexact"],
            "legal_form": ["exact"],
            "activity_code": ["exact"],
            "accountancy_account": ["exact"],
            "payment_reference": ["exact"],
            "date_created": ["exact", "lt", "lte", "gt", "gte"],
            "date_updated": ["exact", "lt", "lte", "gt", "gte"],
            "is_deleted": ["exact"]
        }

        connection_class = ExtendedConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        return PolicyHolder.get_queryset(queryset, info)


class PolicyHolderInsureeFilter(FilterSet):
    json_ext_contains = CharFilter(method='filter_json_ext_contains')

    class Meta:
        model = PolicyHolderInsuree
        fields = {
            "id": ["exact"],
            "version": ["exact"],
            **prefix_filterset("policy_holder__", PolicyHolderGQLType._meta.filter_fields),
            **prefix_filterset("insuree__", InsureeGQLType._meta.filter_fields),
            **prefix_filterset("contribution_plan_bundle__", ContributionPlanBundleGQLType._meta.filter_fields),
            "date_created": ["exact", "lt", "lte", "gt", "gte"],
            "date_updated": ["exact", "lt", "lte", "gt", "gte"],
            "user_created": ["exact"],
            "user_updated": ["exact"],
            "is_deleted": ["exact"],
            "employer_number": ["exact", "istartswith", "icontains", "iexact"],
        }

    def filter_json_ext_contains(self, queryset, name, value):
        # Here `name` will be `json_ext_contains`, and `value` will be what you want to filter by
        return queryset.filter(json_ext__icontains=value)


class PolicyHolderInsureeGQLType(DjangoObjectType):
    class Meta:
        model = PolicyHolderInsuree
        interfaces = (graphene.relay.Node,)
        filterset_class = PolicyHolderInsureeFilter
        connection_class = ExtendedConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        return PolicyHolderInsuree.get_queryset(queryset, info)


class PolicyHolderContributionPlanGQLType(DjangoObjectType):
    class Meta:
        model = PolicyHolderContributionPlan
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "version": ["exact"],
            **prefix_filterset("policy_holder__", PolicyHolderGQLType._meta.filter_fields),
            **prefix_filterset("contribution_plan_bundle__", ContributionPlanBundleGQLType._meta.filter_fields),
            "date_created": ["exact", "lt", "lte", "gt", "gte"],
            "date_updated": ["exact", "lt", "lte", "gt", "gte"],
            "user_created": ["exact"],
            "user_updated": ["exact"],
            "is_deleted": ["exact"],
        }

        connection_class = ExtendedConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        return PolicyHolderContributionPlan.get_queryset(queryset, info)


class PolicyHolderUserGQLType(DjangoObjectType):
    class Meta:
        model = PolicyHolderUser
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "user": ["exact"],
            **prefix_filterset("policy_holder__", PolicyHolderGQLType._meta.filter_fields),
            **prefix_filterset("user__", UserGQLType._meta.filter_fields),
            "date_created": ["exact", "lt", "lte", "gt", "gte"],
            "date_updated": ["exact", "lt", "lte", "gt", "gte"],
            "user_created": ["exact"],
            "user_updated": ["exact"],
            "is_deleted": ["exact"],
        }

        connection_class = ExtendedConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        return PolicyHolderUser.get_queryset(queryset, info)


class PolicyHolderMutationGQLType(DjangoObjectType):
    class Meta:
        model = PolicyHolderMutation


class NotDeclaredPolicyHolderGQLType(DjangoObjectType):
    class Meta:
        model = PolicyHolder
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "code": ["exact", "istartswith", "icontains", "iexact"],
            "version": ["exact"],
            "trade_name": ["exact", "istartswith", "icontains", "iexact"],
            **prefix_filterset("locations__", LocationGQLType._meta.filter_fields),
            "phone": ["exact", "istartswith", "icontains", "iexact"],
            "fax": ["exact", "istartswith", "icontains", "iexact"],
            "email": ["exact", "istartswith", "icontains", "iexact"],
            "legal_form": ["exact"],
            "activity_code": ["exact"],
            "accountancy_account": ["exact"],
            "payment_reference": ["exact"],
            "date_created": ["exact", "lt", "lte", "gt", "gte"],
            "date_updated": ["exact", "lt", "lte", "gt", "gte"],
            "is_deleted": ["exact"]
        }

        connection_class = ExtendedConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        return PolicyHolder.get_queryset(queryset, info)


class PolicyHolderExcptionType(DjangoObjectType):
    class Meta:
        model = PolicyHolderExcption
        filter_fields = {
            "id": ["exact"],
            "status": ["exact", "istartswith", "icontains", "iexact"],
            "exception_reason": ["exact", "istartswith", "icontains", "iexact"],
            **prefix_filterset("policy_holder__", PolicyHolderGQLType._meta.filter_fields),
        }
        interfaces = (graphene.relay.Node,)
        connection_class = ExtendedConnection


class CategoryChangeGQLType(DjangoObjectType):
    class Meta:
        model = CategoryChange
        filter_fields = {
            "id": ["exact"],
            "code": ["exact", "istartswith", "icontains", "iexact"],
            "new_category": ["exact", "istartswith", "icontains", "iexact"],
            "request_type": ["exact", "istartswith", "icontains", "iexact"],
            "status": ["exact", "istartswith", "icontains", "iexact"],
            **prefix_filterset("insuree__", InsureeGQLType._meta.filter_fields),
            **prefix_filterset("policy_holder__", PolicyHolderGQLType._meta.filter_fields),
        }
        interfaces = (graphene.relay.Node,)
        connection_class = ExtendedConnection
