import logging
import random
from datetime import datetime

import pandas as pd
from django.http import JsonResponse

from rest_framework.decorators import permission_classes, api_view
from rest_framework.permissions import IsAuthenticated

from contribution_plan.models import ContributionPlanBundle
from insuree.gql_mutations import temp_generate_employee_camu_registration_number
from insuree.models import Insuree, Gender, Family
from location.models import Location
from policyholder.apps import PolicyholderConfig
from policyholder.models import PolicyHolder, PolicyHolderInsuree
from workflow.workflow_stage import insuree_add_to_workflow
from insuree.abis_api import create_abis_insuree

logger = logging.getLogger(__name__)


HEADER_ENROLMENT_TYPE = "enrolment_type"
HEADER_FAMILY_HEAD = "family_head"
HEADER_FAMILY_LOCATION_CODE = "family_location_code"
HEADER_CONTRIBUTION_PLAN_BUNDLE_CODE = "contrib_code"
HEADER_INSUREE_OTHER_NAMES = "insuree_other_names"
HEADER_INSUREE_LAST_NAME = "insuree_last_names"
HEADER_INSUREE_DOB = "insuree_dob"
HEADER_INSUREE_GENDER = "insuree_gender"
HEADER_PHONE = "phone"
HEADER_ADDRESS = "address"
HEADER_INSUREE_ID = "insuree_id"
HEADER_INCOME = "income"
HEADERS = [
    HEADER_FAMILY_HEAD,
    HEADER_FAMILY_LOCATION_CODE,
    HEADER_CONTRIBUTION_PLAN_BUNDLE_CODE,
    HEADER_INSUREE_OTHER_NAMES,
    HEADER_INSUREE_LAST_NAME,
    HEADER_INSUREE_DOB,
    HEADER_INSUREE_GENDER,
    HEADER_INSUREE_ID,
    HEADER_INCOME,
    HEADER_PHONE,
    HEADER_ADDRESS,
    HEADER_ENROLMENT_TYPE,
]

GENDERS = {
    "F": Gender.objects.get(code='F'),
    "M": Gender.objects.get(code='M'),
}

RANDOM_INSUREE_ID_MIN_VALUE = 900_000_000_000
RANDOM_INSUREE_ID_MAX_VALUE = 999_999_999_999


def check_user_with_rights(rights):
    class UserWithRights(IsAuthenticated):
        def has_permission(self, request, view):
            return super().has_permission(request, view) and request.user.has_perms(
                rights
            )

    return UserWithRights


def clean_line(line):
    for header in HEADERS:
        value = line[header]
        if isinstance(value, str):
            line[header] = value.strip()


def validate_line(line):
    errors = ""
    # add here any additional cleaning/conditions/formatting:
    # make sure gender is "M" or "F"
    # make sure dob is in the right format
    # make sure the IDs are in the right format
    # make sure mandatory values are not null and len(str) > 0
    # ...
    # if something is not right, append an error message to errors
    return errors


def get_village_from_line(line):
    village_code = line[HEADER_FAMILY_LOCATION_CODE]
    village = (Location.objects.filter(validity_to__isnull=True,
                                      type="V",
                                      code=village_code)
                               .first())
    return village


def get_or_create_family_from_line(line, village: Location, audit_user_id: int):
    head_id = line[HEADER_FAMILY_HEAD]
    family = (Family.objects.filter(validity_to__isnull=True,
                                   head_insuree__chf_id=head_id,
                                   location=village)
                            .first())
    created = False

    if not family:
        family = Family.objects.create(
            head_insuree_id=1,  # dummy
            location=village,
            audit_user_id=audit_user_id,
            status="PRE_REGISTERED",
        )
        created = True

    return family, created


def generate_available_chf_id(gender, village, dob):
    data = {
        "gender_id": gender.upper(),
        "json_ext": {"insureelocations": {"parent": {"parent": {"parent": {"code": village.parent.parent.parent.code}}}}},
        "dob": dob,
    }
    return temp_generate_employee_camu_registration_number(None, data)


def get_or_create_insuree_from_line(line, family: Family, is_family_created: bool, audit_user_id: int, location = None):
    id = line[HEADER_INSUREE_ID]
    insuree = (Insuree.objects.filter(validity_to__isnull=True, chf_id=id)
                              .first())
    created = False

    if not insuree:
        insuree_id = generate_available_chf_id(
            line[HEADER_INSUREE_GENDER],
            location if location else family.location,
            line[HEADER_INSUREE_DOB]
        )
        insuree = Insuree.objects.create(
            other_names=line[HEADER_INSUREE_OTHER_NAMES],
            last_name=line[HEADER_INSUREE_LAST_NAME],
            dob=line[HEADER_INSUREE_DOB],
            family=family,
            audit_user_id=audit_user_id,
            card_issued=False,
            chf_id=insuree_id,
            gender=GENDERS[line[HEADER_INSUREE_GENDER]],
            head=is_family_created,
            current_village=location if location else family.location,
            current_address=line[HEADER_ADDRESS],
            phone=line[HEADER_PHONE],
            json_ext={"enrolmentType": line[HEADER_ENROLMENT_TYPE].lower() if line[HEADER_ENROLMENT_TYPE].lower() in [
                            "government",
                            "private",
                            "selfEmployed",
                           ] else "government",
                      }
        )
        created = True

    return insuree, created


def get_contrib_plan_bundle_from_line(line):
    cpb_code = line[HEADER_CONTRIBUTION_PLAN_BUNDLE_CODE]
    return ContributionPlanBundle.objects.filter(code=cpb_code, is_deleted=False, date_valid_to__isnull=True).first()


def get_policy_holder_from_code(ph_code: str):
    return PolicyHolder.objects.filter(code=ph_code, is_deleted=False).first()


@api_view(["POST"])
@permission_classes(
    [
        # Change this right and create a specific one instead
        check_user_with_rights(
            PolicyholderConfig.gql_query_policyholder_perms,
        )
    ]
)
def import_phi(request, policy_holder_code):
    file = request.FILES["file"]
    user_id = request.user.id_for_audit
    logger.info("User (audit id %s) requested import of PolicyHolderInsurees", user_id)

    policy_holder = get_policy_holder_from_code(policy_holder_code)
    if not policy_holder:
        return JsonResponse({"errors": f"Unknown policy holder ({policy_holder_code})"})

    total_lines = 0
    total_insurees_created = 0
    total_families_created = 0
    total_phi_created = 0
    total_phi_updated = 0
    total_locations_not_found = 0
    total_contribution_plan_not_found = 0
    total_validation_errors = 0

    df = pd.read_excel(file)

    # Renaming the headers
    rename_columns = {
        "Type d'enrôlement": HEADER_ENROLMENT_TYPE,
        "Prénom": HEADER_INSUREE_OTHER_NAMES,
        "Nom": HEADER_INSUREE_LAST_NAME,
        "ID": HEADER_INSUREE_ID,
        "Date de naissance": HEADER_INSUREE_DOB,
        "Sexe": HEADER_INSUREE_GENDER,
        "Téléphone": HEADER_PHONE,
        "Adresse": HEADER_ADDRESS,
        "Village": HEADER_FAMILY_LOCATION_CODE,
        "ID Famille": HEADER_FAMILY_HEAD,
        "Plan": HEADER_CONTRIBUTION_PLAN_BUNDLE_CODE,
        "Salaire": HEADER_INCOME,
    }
    df.rename(columns=rename_columns, inplace=True)

    errors = []
    logger.debug("Importing %s lines", len(df))
    for index, line in df.iterrows():  # for each line in the Excel file
        total_lines += 1
        clean_line(line)
        logger.debug("Importing line %s: %s", total_lines, line)

        validation_errors = validate_line(line)
        if validation_errors:
            errors.append(f"Error line {total_lines} - validation issues ({validation_errors})")
            logger.debug(f"Error line {total_lines} - validation issues ({validation_errors})")
            total_validation_errors += 1
            continue

        village = get_village_from_line(line)
        if not village:
            errors.append(f"Error line {total_lines} - unknown village ({line[HEADER_FAMILY_LOCATION_CODE]})")
            logger.debug(f"Error line {total_lines} - unknown village ({line[HEADER_FAMILY_LOCATION_CODE]})")
            total_locations_not_found += 1
            continue

        cpb = get_contrib_plan_bundle_from_line(line)
        if not cpb:
            errors.append(f"Error line {total_lines} - unknown contribution plan bundle ({line[HEADER_CONTRIBUTION_PLAN_BUNDLE_CODE]})")
            logger.debug(f"Error line {total_lines} - unknown contribution plan bundle ({line[HEADER_CONTRIBUTION_PLAN_BUNDLE_CODE]})")
            total_locations_not_found += 1
            continue

        family, family_created = get_or_create_family_from_line(line, village, user_id)
        logger.debug("family_created: %s", family_created)
        if family_created:
            total_families_created += 1

        insuree, insuree_created = get_or_create_insuree_from_line(line, family, family_created, user_id)
        logger.debug("insuree_created: %s", insuree_created)
        if insuree_created:
            total_insurees_created += 1
            try:
                insuree_add_to_workflow(None, insuree.id, "INSUREE_ENROLLMENT", "Pre_Register")
                create_abis_insuree(None, insuree)
                #TODO: GED Folder Creation
            except Exception as e:
                logger.error(f"insuree bulk upload error : {e}")
        if family_created:
            family.head_insuree = insuree
            family.save()
        phi_json_ext = {}
        if line[HEADER_INCOME]:
            phi_json_ext["calculation_rule"] = {
                "income": line[HEADER_INCOME]
            }
        # PolicyHolderInsuree is HistoryModel that prevents the use of .objects.update_or_create() :(
        phi = PolicyHolderInsuree.objects.filter(insuree=insuree, policy_holder=policy_holder).first()
        if phi:
            phi.contribution_plan_bundle = cpb
            phi.json_ext = {**phi.json_ext, **phi_json_ext} if phi.json_ext else phi_json_ext
            total_phi_updated += 1
        else:
            phi = PolicyHolderInsuree(
                insuree=insuree,
                policy_holder=policy_holder,
                contribution_plan_bundle=cpb,
                json_ext=phi_json_ext,
            )
            total_phi_created += 1
        phi.save(username=request.user.username)

    result = {
        "total_lines": total_lines,
        "total_insurees_created": total_insurees_created,
        "total_families_created": total_families_created,
        "total_phi_created": total_phi_created,
        "total_phi_updated": total_phi_updated,
        "total_errors": total_locations_not_found + total_contribution_plan_not_found,
        "total_locations_not_found": total_locations_not_found,
        "total_contribution_plan_not_found": total_contribution_plan_not_found,
        "total_validation_errors": total_validation_errors,
        "errors": errors,
    }
    logger.info("Import of PolicyHolderInsurees done")
    return JsonResponse(data=result)
