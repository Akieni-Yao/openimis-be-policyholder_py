import json
import logging
import math
import io
import calendar
from datetime import datetime, timedelta
import re

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage
from django.db.models import Q, Sum
from django.shortcuts import redirect
from django.utils import timezone
import pandas as pd
from django.http import JsonResponse, HttpResponse
from django.utils.dateparse import parse_date
from django.utils.encoding import force_text
from django.utils.http import urlsafe_base64_decode
from graphql import GraphQLError

from rest_framework.decorators import (
    permission_classes,
    api_view,
    authentication_classes,
)
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from contract.models import Contract
from contract.services import Contract as ContractService
from core.constants import *
from core.models import Role, InteractiveUser, Banks
from core.notification_service import create_camu_notification, base64_encode
from insuree.dms_utils import (
    create_openKm_folder_for_bulkupload,
    send_mail_to_temp_insuree_with_pdf,
)
from insuree.gql_mutations import temp_generate_employee_camu_registration_number
from insuree.models import Insuree, Gender, Family, InsureePolicy
from location.models import Location
from payment.models import Payment, PaymentPenaltyAndSanction
from payment.views import get_payment_product_config
from policy.models import Policy
from policyholder.apps import *
from policyholder.constants import (
    CC_WAITING_FOR_DOCUMENT,
    CC_APPROVED,
    CC_PENDING,
    CC_WAITING_FOR_APPROVAL,
    CC_PROCESSING,
    PH_STATUS_CREATED,
    PH_STATUS_LOCKED,
    TIPL_PAYMENT_METHOD_ID,
)
from policyholder.dms_utils import (
    create_folder_for_cat_chnage_req,
    validate_enrolment_type,
    send_notification_to_head,
)
from policyholder.models import (
    PolicyHolder,
    PolicyHolderInsuree,
    PolicyHolderContributionPlan,
    CategoryChange,
    PolicyHolderUser,
)
from contribution_plan.models import ContributionPlanBundleDetails
from workflow.workflow_stage import insuree_add_to_workflow
from insuree.abis_api import create_abis_insuree
from decimal import Decimal, InvalidOperation
from policyholder.tasks import sync_policyholders_to_erp

logger = logging.getLogger(__name__)

MINIMUM_AGE_LIMIT = 16
HEADER_INSUREE_CAMU_NO = "camu_number"
HEADER_FAMILY_HEAD = "family_head"
HEADER_FAMILY_LOCATION_CODE = "family_location_code"
HEADER_INSUREE_OTHER_NAMES = "insuree_other_names"
HEADER_INSUREE_LAST_NAME = "insuree_last_names"
HEADER_INSUREE_DOB = "insuree_dob"
HEADER_BIRTH_LOCATION_CODE = "birth_location_code"
HEADER_INSUREE_GENDER = "insuree_gender"
HEADER_CIVILITY = "civility"
HEADER_PHONE = "phone"
HEADER_ADDRESS = "address"
HEADER_INSUREE_ID = "insuree_id"
HEADER_INCOME = "income"
HEADER_EMAIL = "email"
HEADER_EMPLOYER_NUMBER = "employer_number"
HEADER_EMPLOYER_PERCENTAGE = "employer_percentage"
HEADER_EMPLOYER_SHARE = "employerContribution"
HEADER_EMPLOYEE_PERCENTAGE = "employee_percentage"
HEADER_EMPLOYEE_SHARE = "employeeContribution"
HEADER_TOTAL_SHARE = "totalContribution"
HEADER_DELETE = "Delete"
HEADERS = [
    HEADER_INSUREE_CAMU_NO,
    # HEADER_FAMILY_HEAD,
    HEADER_FAMILY_LOCATION_CODE,
    HEADER_INSUREE_OTHER_NAMES,
    HEADER_INSUREE_LAST_NAME,
    HEADER_INSUREE_DOB,
    HEADER_BIRTH_LOCATION_CODE,
    HEADER_INSUREE_GENDER,
    HEADER_CIVILITY,
    HEADER_PHONE,
    HEADER_ADDRESS,
    HEADER_INSUREE_ID,
    # HEADER_INCOME,
    HEADER_EMAIL,
    # HEADER_EMPLOYER_NUMBER,
    # HEADER_EMPLOYER_PERCENTAGE,
    # HEADER_EMPLOYER_SHARE,
    # HEADER_EMPLOYEE_PERCENTAGE,
    # HEADER_EMPLOYEE_SHARE,
    # HEADER_TOTAL_SHARE,
    HEADER_DELETE,
]

GENDERS = {
    "F": Gender.objects.get(code="F"),
    "M": Gender.objects.get(code="M"),
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
        if value is None:
            pass
        elif isinstance(value, str):
            line[header] = value.strip()
        elif isinstance(value, datetime):
            logger.info(f" ======    value is datetime : {value}   =======")
        elif math.isnan(value):
            logger.info(f" ======    value is nan : {value}   =======")
            line[header] = None
            logger.info(f" ======    after change value is : {line[header]}   =======")
        elif header == HEADER_PHONE and isinstance(value, float):
            line[header] = int(value)


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
    village = Location.objects.filter(
        validity_to__isnull=True, type="V", code=village_code
    ).first()
    return village


def get_or_create_family_from_line(
    line, village: Location, audit_user_id: int, enrolment_type
):
    # head_id = line[HEADER_FAMILY_HEAD]
    head_id = None
    family = None
    if head_id:
        family = Family.objects.filter(
            validity_to__isnull=True, head_insuree__chf_id=head_id, location=village
        ).first()
    created = False

    if not family and not head_id:
        family = Family.objects.create(
            head_insuree_id=1,  # dummy
            location=village,
            audit_user_id=audit_user_id,
            status="PRE_REGISTERED",
            address=line[HEADER_ADDRESS],
            json_ext={"enrolmentType": map_enrolment_type_to_category(enrolment_type)},
        )
        created = True

    return family, created


def generate_available_chf_id(gender, village, dob, insureeEnrolmentType):
    data = {
        "gender_id": gender.upper(),
        "json_ext": {
            "insureelocations": {
                "parent": {
                    "parent": {"parent": {"code": village.parent.parent.parent.code}}
                }
            }
        },
        "dob": dob,
        "insureeEnrolmentType": map_enrolment_type_to_category(insureeEnrolmentType),
    }
    return temp_generate_employee_camu_registration_number(None, data)


def get_or_create_insuree_from_line(
    line,
    family: Family,
    is_family_created: bool,
    audit_user_id: int,
    location=None,
    core_user_id=None,
    enrolment_type=None,
):
    id = line[HEADER_INSUREE_ID]
    camu_num = line[HEADER_INSUREE_CAMU_NO]
    insuree = None
    if id:
        insuree = Insuree.objects.filter(validity_to__isnull=True, chf_id=id).first()
    if not insuree and camu_num:
        insuree = Insuree.objects.filter(
            validity_to__isnull=True, camu_number=camu_num
        ).first()

    created = False
    # if insuree:
    #     json_ext = insuree.json_ext
    #     json_ext['employeeNumber'] = line[HEADER_EMPLOYER_NUMBER]
    #     insuree.json_ext = json_ext
    #     insuree.save()

    if not insuree:
        insuree_dob = line[HEADER_INSUREE_DOB]
        logger.info(
            f"=================================== LINE 244 {type(insuree_dob)}==========================="
        )
        if not isinstance(insuree_dob, datetime):
            datetime_obj = (
                datetime.strptime(f"{insuree_dob}", "%d/%m/%Y")
                if isinstance(insuree_dob, str)
                else datetime.combine(insuree_dob, datetime.min.time())
            )
            line[HEADER_INSUREE_DOB] = timezone.make_aware(datetime_obj).date()

        insuree_id = generate_available_chf_id(
            line[HEADER_INSUREE_GENDER],
            location if location else family.location,
            line[HEADER_INSUREE_DOB],
            enrolment_type,
        )
        current_village = location if location else family.location
        response_string = json.dumps(current_village, cls=LocationEncoder)
        response_data = json.loads(response_string)
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
            current_village=current_village,
            current_address=line[HEADER_ADDRESS],
            phone=line[HEADER_PHONE],
            created_by=core_user_id,
            modified_by=core_user_id,
            marital=mapping_marital_status(line[HEADER_CIVILITY]),
            email=line[HEADER_EMAIL],
            json_ext={
                "insureeEnrolmentType": map_enrolment_type_to_category(enrolment_type),
                "insureelocations": response_data,
                "BirthPlace": line[HEADER_BIRTH_LOCATION_CODE],
                "insureeaddress": line[HEADER_ADDRESS],
            },
        )
        created = True

    return insuree, created


def validating_insuree_on_name_dob(line):
    insuree_dob = line[HEADER_INSUREE_DOB]
    if not isinstance(insuree_dob, datetime):
        datetime_obj = datetime.strptime(insuree_dob, "%d/%m/%Y")
        line[HEADER_INSUREE_DOB] = timezone.make_aware(datetime_obj).date()

    insuree = Insuree.objects.filter(
        other_names=line[HEADER_INSUREE_OTHER_NAMES],
        last_name=line[HEADER_INSUREE_LAST_NAME],
        dob=line[HEADER_INSUREE_DOB],
        validity_to__isnull=True,
        legacy_id__isnull=True,
    ).first()

    return insuree


def get_policy_holder_from_code(ph_code: str):
    return PolicyHolder.objects.filter(code=ph_code, is_deleted=False).first()


def soft_delete_insuree(line, policy_holder_code, user_id):
    id = line[HEADER_INSUREE_ID]
    camu_num = line[HEADER_INSUREE_CAMU_NO]
    insuree = None
    if id:
        insuree = Insuree.objects.filter(validity_to__isnull=True, chf_id=id).first()
    if not insuree:
        insuree = Insuree.objects.filter(
            validity_to__isnull=True, camu_number=camu_num
        ).first()
    if insuree:
        phn = PolicyHolderInsuree.objects.filter(
            insuree_id=insuree.id,
            policy_holder__code=policy_holder_code,
            policy_holder__date_valid_to__isnull=True,
            policy_holder__is_deleted=False,
            date_valid_to__isnull=True,
            is_deleted=False,
        ).first()
        if phn:
            PolicyHolderInsuree.objects.filter(id=phn.id).update(
                is_deleted=True, date_valid_to=datetime.now()
            )
            return True
    return False


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
    core_user_id = request.user.id
    logger.info("User (audit id %s) requested import of PolicyHolderInsurees", user_id)

    logger.info(
        "=================================== LINE 349 ==========================="
    )

    policy_holder = get_policy_holder_from_code(policy_holder_code)
    if not policy_holder:
        return JsonResponse({"errors": f"Unknown policy holder ({policy_holder_code})"})

    logger.info(
        "=================================== LINE 354 ==========================="
    )

    total_lines = 0
    total_insurees_created = 0
    total_families_created = 0
    total_phi_created = 0
    total_phi_updated = 0
    total_locations_not_found = 0
    total_contribution_plan_not_found = 0
    total_validation_errors = 0

    logger.info(
        "=================================== LINE 360 ==========================="
    )

    df = pd.read_excel(file)
    df.columns = [col.strip() for col in df.columns]
    org_columns = df.columns

    logger.info(
        "=================================== LINE 366 ==========================="
    )
    # Renaming the headers
    rename_columns = {
        "Numéro CAMU": HEADER_INSUREE_CAMU_NO,
        "Prénom": HEADER_INSUREE_OTHER_NAMES,
        "Nom": HEADER_INSUREE_LAST_NAME,
        "Numéro CAMU temporaire": HEADER_INSUREE_ID,
        "Date de naissance": HEADER_INSUREE_DOB,
        "Lieu de naissance": HEADER_BIRTH_LOCATION_CODE,
        "Sexe": HEADER_INSUREE_GENDER,
        "Civilité": HEADER_CIVILITY,
        "Téléphone": HEADER_PHONE,
        "Adresse": HEADER_ADDRESS,
        "Village": HEADER_FAMILY_LOCATION_CODE,
        # "ID Famille": HEADER_FAMILY_HEAD,
        "Email": HEADER_EMAIL,
        # "Matricule": HEADER_EMPLOYER_NUMBER,
        # "Salaire Brut": HEADER_INCOME,
        # "Part Patronale %": HEADER_EMPLOYER_PERCENTAGE,
        # "Part Patronale": HEADER_EMPLOYER_SHARE,
        # "Part Salariale %": HEADER_EMPLOYEE_PERCENTAGE,
        # "Part Salariale": HEADER_EMPLOYEE_SHARE,
        # "Cotisation total": HEADER_TOTAL_SHARE,
        "Supprimé": HEADER_DELETE,
    }

    df.rename(columns=rename_columns, inplace=True)

    logger.info(
        "=================================== LINE 371 ==========================="
    )

    errors = []
    logger.debug("Importing %s lines", len(df))

    logger.info(
        "=================================== LINE 375 ==========================="
    )

    # For output excel with error and success message
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine="xlsxwriter")
    processed_data = pd.DataFrame()

    logger.info(
        "=================================== LINE 380 ==========================="
    )

    for index, line in df.iterrows():  # for each line in the Excel file
        total_lines += 1
        clean_line(line)
        logger.debug("Importing line %s: %s", total_lines, line)
        logger.info(
            "=================================== LINE 419 ==========================="
        )

        # List of possible date formats to try
        date_formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d/%m/%Y",
        ]  # Add more formats as needed

        dob_value = line[HEADER_INSUREE_DOB]
        logger.info(
            "=================================== LINE 422 ==========================="
        )

        # if not line.get(HEADER_INSUREE_ID) and line.get(HEADER_FAMILY_HEAD):
        if not line.get(HEADER_INSUREE_ID):
            if isinstance(dob_value, datetime):
                dob = dob_value
                logger.info(
                    "=================================== LINE 435 ==========================="
                )
            else:
                dob = None
                for date_format in date_formats:
                    try:
                        dob = datetime.strptime(dob_value, date_format)
                        break  # If parsing succeeds, break out of the loop
                    except ValueError:
                        continue  # If parsing fails, try the next format

                if dob is None:
                    # If none of the formats match, handle the error
                    errors.append(
                        f"Error line {total_lines} - Format de date invalide pour la date de naissance : {dob_value}"
                    )
                    logger.debug(
                        f"Error line {total_lines} - Format de date invalide pour la date de naissance : {dob_value}"
                    )
                    total_validation_errors += 1
                    # Adding error in output excel
                    row_data = line.tolist()
                    row_data.extend(
                        [
                            "Échec",
                            f"Format de date invalide pour la date de naissance : {dob_value}",
                        ]
                    )
                    processed_data = processed_data.append(
                        pd.Series(row_data), ignore_index=True
                    )
                    continue

            age = (datetime.now().date() - dob.date()) // timedelta(
                days=365.25
            )  # Calculate age in years
            if age < MINIMUM_AGE_LIMIT:
                errors.append(
                    f"Error line {total_lines} - L'assuré doit être âgé d'au moins {MINIMUM_AGE_LIMIT} ans."
                )
                logger.debug(
                    f"Error line {total_lines} - L'assuré doit être âgé d'au moins {MINIMUM_AGE_LIMIT} ans."
                )
                total_validation_errors += 1
                # Adding error in output excel
                row_data = line.tolist()
                row_data.extend(
                    [
                        "Échec",
                        f"L'assuré doit être âgé d'au moins {MINIMUM_AGE_LIMIT} ans.",
                    ]
                )
                processed_data = processed_data.append(
                    pd.Series(row_data), ignore_index=True
                )
                continue

            logger.info(
                "=================================== LINE 439 ==========================="
            )

            force_value = str(line.get("Force", "")).strip().lower()
            if force_value not in ["yes", "Yes", "YES"]:
                logger.info(
                    "=================================== LINE 442 ==========================="
                )
                # Check if insuree with the same name and DOB already exists
                insuree = validating_insuree_on_name_dob(line)
                if insuree:
                    # Generate an error message instructing to add insuree forcibly
                    errors.append(
                        f"Error line {total_lines} - Un assuré ayant le même nom et la même date de naissance existe déjà. Si vous voulez l'ajouter, veuillez le faire de force en ajoutant une nouvelle colonne nommée 'Force' avec la valeur 'YES'."
                    )
                    logger.debug(
                        f"Error line {total_lines} - Un assuré ayant le même nom et la même date de naissance existe déjà. Si vous voulez l'ajouter, veuillez le faire de force en ajoutant une nouvelle colonne nommée 'Force' avec la valeur 'YES'."
                    )

                    logger.info(
                        "=================================== LINE 445 ==========================="
                    )

                    # Adding error in output excel
                    row_data = line.tolist()
                    row_data.extend(
                        [
                            "Échec",
                            "Un assuré ayant le même nom et la même date de naissance existe déjà. Si vous voulez l'ajouter, veuillez le faire de force en ajoutant une nouvelle colonne nommée 'Force' avec la valeur 'YES'.",
                        ]
                    )
                    processed_data = processed_data.append(
                        pd.Series(row_data), ignore_index=True
                    )
                    continue

            logger.info(
                "=================================== LINE 448 ==========================="
            )

        validation_errors = validate_line(line)
        if validation_errors:
            errors.append(
                f"Error line {total_lines} - Problèmes de validation  ({validation_errors})"
            )
            logger.debug(
                f"Error line {total_lines} - Problèmes de validation  ({validation_errors})"
            )

            logger.info(
                "=================================== LINE 452 ==========================="
            )

            total_validation_errors += 1

            # Adding error in output excel
            row_data = line.tolist()
            row_data.extend(["Échec", validation_errors])
            processed_data = processed_data.append(
                pd.Series(row_data), ignore_index=True
            )
            continue

        logger.info(
            "=================================== LINE 455 ==========================="
        )

        if line[HEADER_DELETE] and line[HEADER_DELETE].lower() == "yes":
            is_deleted = soft_delete_insuree(line, policy_holder_code, user_id)
            if is_deleted:
                continue

            logger.info(
                "=================================== LINE 458 ==========================="
            )

        village = get_village_from_line(line)
        if not village:
            errors.append(
                f"Error line {total_lines} - Village inconnu ({line[HEADER_FAMILY_LOCATION_CODE]})"
            )
            logger.debug(
                f"Error line {total_lines} -Village inconnu ({line[HEADER_FAMILY_LOCATION_CODE]})"
            )
            total_locations_not_found += 1

            logger.info(
                "=================================== LINE 459 ==========================="
            )

            # Adding error in output excel
            row_data = line.tolist()
            row_data.extend(
                ["Échec", f"Village inconnu - {line[HEADER_FAMILY_LOCATION_CODE]}"]
            )
            processed_data = processed_data.append(
                pd.Series(row_data), ignore_index=True
            )
            continue

        try:
            ph_cpb = PolicyHolderContributionPlan.objects.filter(
                policy_holder=policy_holder, is_deleted=False
            ).first()
            if not ph_cpb:
                errors.append(
                    f"Error line {total_lines} - Pas de plans de cotisation avec ({policy_holder.trade_name})"
                )
                logger.debug(
                    f"Error line {total_lines} - Pas de plans de cotisation avec ({policy_holder.trade_name})"
                )
                total_contribution_plan_not_found += 1

                logger.info(
                    "=================================== LINE 460 ==========================="
                )

                # Adding error in output excel
                row_data = line.tolist()
                row_data.extend(
                    [
                        "Échec",
                        f"Pas de plans de cotisation avec - {policy_holder.trade_name}",
                    ]
                )
                processed_data = processed_data.append(
                    pd.Series(row_data), ignore_index=True
                )
                continue

            cpb = ph_cpb.contribution_plan_bundle
            if not cpb:
                errors.append(
                    f"Error line {total_lines} - Contribution plan inconnu ({ph_cpb.contribution_plan_bundle})"
                )
                logger.debug(
                    f"Error line {total_lines} - Contribution plan inconnu ({ph_cpb.contribution_plan_bundle})"
                )
                total_locations_not_found += 1

                logger.info(
                    "=================================== LINE 461 ==========================="
                )

                # Adding error in output excel
                row_data = line.tolist()
                row_data.extend(
                    [
                        "Échec",
                        f"Contribution plan inconnu - {ph_cpb.contribution_plan_bundle}",
                    ]
                )
                processed_data = processed_data.append(
                    pd.Series(row_data), ignore_index=True
                )
                continue

            enrolment_type = cpb.name
        except Exception as e:
            logger.error(
                f"Error occurred while retrieving Contribution Plan Bundle: {e}"
            )
            enrolment_type = None

            logger.info(
                "=================================== LINE 462 ==========================="
            )

        is_valid_enrolment = validate_enrolment_type(line, enrolment_type)
        if not is_valid_enrolment:
            row_data = line.tolist()
            row_data.extend(
                ["Échec", "Le type d'enrôlement doit être différent de 'étudiant'."]
            )
            processed_data = processed_data.append(
                pd.Series(row_data), ignore_index=True
            )
            continue

        logger.info(
            "=================================== LINE 463 ==========================="
        )

        is_cc_request = check_for_category_change_request(
            request.user, line, policy_holder, enrolment_type
        )
        if is_cc_request:
            row_data = line.tolist()
            row_data.extend(["Réussite", "Demande de changement de catégorie Créé."])
            processed_data = processed_data.append(
                pd.Series(row_data), ignore_index=True
            )
            # continue

        logger.info(
            "=================================== LINE 464 ==========================="
        )

        family, family_created = get_or_create_family_from_line(
            line, village, user_id, enrolment_type
        )
        # family
        logger.debug("family_created: %s", family_created)
        if family_created:
            total_families_created += 1
        elif not family_created and family is None:
            logger.info(
                "=================================== LINE 465 ==========================="
            )

            # Adding error in output excel
            row_data = line.tolist()
            row_data.extend(["Échec", "ID du chef de famille inconnu."])
            processed_data = processed_data.append(
                pd.Series(row_data), ignore_index=True
            )
            continue

        logger.info(
            "=================================== LINE 466 ==========================="
        )

        insuree, insuree_created = get_or_create_insuree_from_line(
            line, family, family_created, user_id, None, core_user_id, enrolment_type
        )
        logger.debug("insuree_created: %s", insuree_created)
        if insuree_created:
            total_insurees_created += 1

            logger.info(
                "=================================== LINE 467 ==========================="
            )

            try:
                logger.info(
                    "====  policyholder  ====  import_phi  ====  create_openKm_folder_for_bulkupload  ====  Start"
                )
                user = request.user
                create_openKm_folder_for_bulkupload(user, insuree)
                logger.info(
                    "====  policyholder  ====  import_phi  ====  create_openKm_folder_for_bulkupload  ====  End"
                )

                logger.info(
                    "=================================== LINE 468 ==========================="
                )

            except Exception as e:
                logger.error(f"insuree bulk upload error for dms: {e}")

            logger.info(
                "=================================== LINE 469 ==========================="
            )

            try:
                logger.info(
                    "====  policyholder  ====  import_phi  ====  insuree_add_to_workflow  ====  Start"
                )
                insuree_add_to_workflow(
                    None, insuree.id, "INSUREE_ENROLLMENT", "Pre_Register"
                )
                logger.info(
                    "====  policyholder  ====  import_phi  ====  insuree_add_to_workflow  ====  End"
                )
                logger.info(
                    "====  policyholder  ====  import_phi  ====  create_abis_insuree  ====  Start"
                )
                create_abis_insuree(None, insuree)
                logger.info(
                    "====  policyholder  ====  import_phi  ====  create_abis_insuree  ====  End"
                )
            except Exception as e:
                logger.error(f"insuree bulk upload error for abis or workflow : {e}")
        elif not insuree_created:
            family.delete()
            reason = None

            logger.info(
                "=================================== LINE 470 ==========================="
            )

            other_policyholder_connected = PolicyHolderInsuree.objects.filter(
                insuree=insuree, policy_holder__id__ne=policy_holder.id
            ).first()

            insuree_dob = line[HEADER_INSUREE_DOB]
            if not isinstance(insuree_dob, datetime):
                datetime_obj = datetime.strptime(insuree_dob, "%d/%m/%Y")
                line[HEADER_INSUREE_DOB] = timezone.make_aware(datetime_obj).date()

            if insuree.other_names != line[HEADER_INSUREE_OTHER_NAMES]:
                reason = "Le prénom de l'assuré ne correspond pas."
            elif insuree.last_name != line[HEADER_INSUREE_LAST_NAME]:
                reason = "Le nom de famille de l'assuré ne correspond pas."
            elif insuree.dob != line[HEADER_INSUREE_DOB]:
                reason = "La date de naissance de l'assuré ne correspond pas."
            elif insuree.gender != GENDERS[line[HEADER_INSUREE_GENDER]]:
                reason = "Le sexe de l'assuré ne correspond pas."
            elif insuree.marital != mapping_marital_status(line[HEADER_CIVILITY]):
                reason = "L'état civil de l'assuré ne correspond pas."
            elif other_policyholder_connected: 
                reason = "L'assuré est deja lié a un autre souscripteur."

            logger.info(
                "=================================== LINE 471 ==========================="
            )
            if reason:
                # Adding error in output excel
                row_data = line.tolist()
                row_data.extend(["Échec", reason])
                processed_data = processed_data.append(
                    pd.Series(row_data), ignore_index=True
                )
                continue

            logger.info(
                "=================================== LINE 472 ==========================="
            )

        if family_created and insuree_created:
            family.head_insuree = insuree
            family.save()
        phi_json_ext = {}

        logger.info(
            "=================================== LINE 473 ==========================="
        )

        # if line[HEADER_INCOME]:
        #     phi_json_ext["calculation_rule"] = {"income": line[HEADER_INCOME]}
        employer_number = None
        # if line[HEADER_INCOME]:
        #     employer_number = line[HEADER_EMPLOYER_NUMBER]
        # PolicyHolderInsuree is HistoryModel that prevents the use of .objects.update_or_create() :(
        phi = PolicyHolderInsuree.objects.filter(
            insuree=insuree, policy_holder=policy_holder
        ).first()

        logger.info(
            "=================================== LINE 474 ==========================="
        )

        if phi:
            phi._state.adding = True
            if (
                phi.contribution_plan_bundle != cpb
                or phi.employer_number != employer_number
                or phi.json_ext != phi_json_ext
            ):
                phi.contribution_plan_bundle = cpb
                phi.employer_number = employer_number
                # phi.json_ext = {**phi.json_ext, **phi_json_ext} if phi.json_ext else phi_json_ext
                phi.json_ext = phi_json_ext
                phi.save(username=request.user.username)
                total_phi_updated += 1

                logger.info(
                    "=================================== LINE 475 ==========================="
                )
        else:
            phi = PolicyHolderInsuree(
                insuree=insuree,
                policy_holder=policy_holder,
                contribution_plan_bundle=cpb,
                json_ext=phi_json_ext,
                employer_number=employer_number,
            )
            total_phi_created += 1
            phi.save(username=request.user.username)

            logger.info(
                "=================================== LINE 476 ==========================="
            )
        try:
            create_camu_notification(INS_ADDED_NT, phi)
            logger.info(
                "Successfully created CAMU notification with INS_ADDED_NT and phi."
            )

            logger.info(
                "=================================== LINE 477 ==========================="
            )

        except Exception as e:
            logger.error(
                f"Failed to create CAMU notification with with INS_ADDED_NT : {e}"
            )

            logger.info(
                "=================================== LINE 478 ==========================="
            )

        # Adding success entry in output Excel
        row_data = line.tolist()
        row_data.extend(["Réussite", ""])
        processed_data = processed_data.append(pd.Series(row_data), ignore_index=True)

        try:
            logger.info("---------------   if insuree have email   -------------------")
            if insuree.email:
                insuree_enrolment_type = insuree.json_ext[
                    "insureeEnrolmentType"
                ].lower()
                send_mail_to_temp_insuree_with_pdf(insuree, insuree_enrolment_type)
                logger.info("---------------  email is sent   -------------------")
        except Exception as e:
            logger.error(f"Fail to send auto mail : {e}")

    # Set the appropriate status code based on the type of errors encountered
    status_code = 200  # Default success status

    logger.info(
        "=================================== LINE 479 ==========================="
    )

    if total_locations_not_found > 0:
        status_code = 417  # Expectation Failed for unknown village
    elif total_contribution_plan_not_found > 0:
        status_code = 404  # Not Found for contribution plan issues
    elif total_validation_errors > 0:
        status_code = 422  # Unprocessable Entity for general validation errors

    logger.info(
        "=================================== LINE 480 ==========================="
    )

    # Generate output Excel
    output_headers = list(org_columns) + ["Status", "Reason"]
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        processed_data.to_excel(
            writer, sheet_name="Processed Data", index=False, header=output_headers
        )

    logger.info(
        "=================================== LINE 481 ==========================="
    )

    output.seek(0)
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        status=status_code,
    )
    response["Content-Disposition"] = "attachment; filename=import_results.xlsx"
    return response


def get_insuree_status(insuree_status):
    status = ""

    if insuree_status == "PRE_REGISTERED":
        status = "PRE-ENREGISTRÉ"
    elif insuree_status == "APPROVED":
        status = "APPROVÉ"
    elif insuree_status == "ACTIVE":
        status = "ACTIVÉ"
    elif insuree_status == "REJECTED":
        status = "REJETÉ"
    elif insuree_status == "REWORK":
        status = "REWORK"
    elif insuree_status == "NOT_ACTIVE":
        status = "NON ACTIF"
    elif insuree_status == "WAITING_FOR_DOCUMENT_AND_BIOMETRIC":
        status = "EN ATTENTE DE DOCUMENT ET BIOMETRIE"
    elif insuree_status == "WAITING_FOR_DOCUMENT_REWORK":
        status = "WAITING_FOR_DOCUMENT_REWORK"
    elif insuree_status == "WAITING_FOR_BIOMETRIC_REWORK":
        status = "EN ATTENTE DE BIOMETRIE"
    elif insuree_status == "WAITING_FOR_DOCUMENT":
        status = "EN ATTENTE DE DOCUMENT"
    elif insuree_status == "WAITING_FOR_BIOMETRIC":
        status = "EN ATTENTE DE BIOMETRIE"
    elif insuree_status == "WAITING_FOR_APPROVAL":
        status = "EN ATTENTE D'APPROBATION"
    elif insuree_status == "WAITING_FOR_QUEUE":
        status = "EN ATTENTE DE FILE"
    elif insuree_status == "ON_HOLD":
        status = "EN ATTENTE DE FILE"
    elif insuree_status == "END_OF_LIFE":
        status = "FIN DE VIE"
    elif insuree_status == "LOSS_OF_JOB":
        status = "PERTE D'EMPLOI"
    else:
        status = "NON DÉCLARÉ"

    return status


def export_phi(request, policy_holder_code):
    try:
        insuree_ids = (
            PolicyHolderInsuree.objects.filter(
                policy_holder__code=policy_holder_code,
                policy_holder__date_valid_to__isnull=True,
                policy_holder__is_deleted=False,
                date_valid_to__isnull=True,
                is_deleted=False,
            )
            .values_list("insuree_id", flat=True)
            .distinct()
        )

        queryset = Insuree.objects.filter(
            validity_to__isnull=True, id__in=insuree_ids, head=True
        ).select_related(
            "gender",
            "current_village",
            "family",
            "family__location",
            "family__location__parent",
            "family__location__parent__parent",
            "family__location__parent__parent__parent",
        )

        data = list(
            queryset.values(
                "camu_number",
                "last_name",
                "other_names",
                "chf_id",
                "gender__code",
                "phone",
                "family__location__code",
                "family__head_insuree__chf_id",
                "email",
                "json_ext",
                "id",
                "dob",
                "marital",
                "status",
            )
        )

        df = pd.DataFrame(data)
        df2 = pd.DataFrame(data)

        insuree_dob = [dob.strftime("%d/%m/%Y") for dob in df["dob"]]

        def extract_birth_place(json_data):
            return json_data.get("BirthPlace", None) if json_data else None

        birth_place = [extract_birth_place(json_data) for json_data in df["json_ext"]]

        def extract_civility(marital):
            return mapping_marital_status(None, marital)
            # return json_data.get('civilQuality', None) if json_data else None

        civility = [extract_civility(json_data) for json_data in df["marital"]]

        def extract_address(json_data):
            return json_data.get("insureeaddress", None) if json_data else None

        address = [extract_address(json_data) for json_data in df["json_ext"]]

        def extract_emp_no(insuree_id, policy_holder_code):
            phn_json = PolicyHolderInsuree.objects.filter(
                insuree_id=insuree_id,
                policy_holder__code=policy_holder_code,
                policy_holder__date_valid_to__isnull=True,
                policy_holder__is_deleted=False,
                date_valid_to__isnull=True,
                is_deleted=False,
            ).first()
            # return json_data.get('employeeNumber', None) if json_data else None
            if phn_json:
                return phn_json.employer_number
            return None

        emp_no = [
            extract_emp_no(insuree_id, policy_holder_code) for insuree_id in df["id"]
        ]

        employee_income = dict()

        def extract_income(insuree_id, policy_holder_code):
            phn_json = PolicyHolderInsuree.objects.filter(
                insuree_id=insuree_id,
                policy_holder__code=policy_holder_code,
                policy_holder__date_valid_to__isnull=True,
                policy_holder__is_deleted=False,
                date_valid_to__isnull=True,
                is_deleted=False,
            ).first()
            if phn_json:
                json_data = phn_json.json_ext
                if json_data:
                    ei = json_data.get("calculation_rule", None).get("income", None)
                    employee_income.update({insuree_id: ei})
                    return ei
            return None

        income = [
            extract_income(insuree_id, policy_holder_code) for insuree_id in df["id"]
        ]

        conti_plan = None
        ph_cpb = PolicyHolderContributionPlan.objects.filter(
            policy_holder__code=policy_holder_code, is_deleted=False
        ).first()
        if ph_cpb and ph_cpb.contribution_plan_bundle:
            cpb = ph_cpb.contribution_plan_bundle
            cpbd = ContributionPlanBundleDetails.objects.filter(
                contribution_plan_bundle=cpb, is_deleted=False
            ).first()
            conti_plan = cpbd.contribution_plan if cpbd else None
        else:
            logger.debug(" No contribution plan bundle.")

        employer_contri_per = dict()

        def extract_employer_percentage(insuree_id):
            if conti_plan:
                json_data = conti_plan.json_ext if conti_plan.json_ext else None
                calculation_rule = (
                    json_data.get("calculation_rule", None) if json_data else None
                )
                ercp = (
                    calculation_rule.get("employerContribution", None)
                    if calculation_rule
                    else None
                )
                employer_contri_per.update({insuree_id: ercp})
                return f"{ercp}%" if ercp else None
            return None

        employer_percentage = [
            extract_employer_percentage(insuree_id) for insuree_id in df["id"]
        ]

        employer_contri = dict()

        def extract_employer_share(insuree_id):
            try:
                if employer_contri_per[insuree_id] and employee_income[insuree_id]:
                    erc = round(
                        (float(employer_contri_per[insuree_id]) / 100)
                        * float(employee_income[insuree_id]),
                        2,
                    )
                    employer_contri.update({insuree_id: erc})
                    return erc
                return None
            except Exception as e:
                return None

        employer_share = [extract_employer_share(insuree_id) for insuree_id in df["id"]]

        employee_contri_per = dict()

        def extract_employee_percentage(insuree_id):
            if conti_plan:
                json_data = conti_plan.json_ext if conti_plan.json_ext else None
                calculation_rule = (
                    json_data.get("calculation_rule", None) if json_data else None
                )
                eecp = (
                    calculation_rule.get("employeeContribution", None)
                    if calculation_rule
                    else None
                )
                employee_contri_per.update({insuree_id: eecp})
                return f"{eecp}%" if eecp else None
            return None

        employee_percentage = [
            extract_employee_percentage(insuree_id) for insuree_id in df["id"]
        ]

        employee_contri = dict()

        def extract_employee_share(insuree_id):
            try:
                if employee_income[insuree_id] and employee_contri_per[insuree_id]:
                    eec = round(
                        (float(employee_contri_per[insuree_id]) / 100)
                        * float(employee_income[insuree_id]),
                        2,
                    )
                    employee_contri.update({insuree_id: eec})
                    return eec
                return None
            except Exception as e:
                return None

        employee_share = [extract_employee_share(insuree_id) for insuree_id in df["id"]]

        def extract_total_share(insuree_id):
            try:
                if employee_contri[insuree_id] and employer_contri[insuree_id]:
                    total_contri = (
                        employee_contri[insuree_id] + employer_contri[insuree_id]
                    )
                    return total_contri
                return None
            except Exception as e:
                return None

        total_share = [extract_total_share(insuree_id) for insuree_id in df["id"]]

        df2.drop(
            columns=[
                "camu_number",
                "last_name",
                "other_names",
                "chf_id",
                "gender__code",
                "phone",
                "family__location__code",
                "family__head_insuree__chf_id",
                "email",
                "json_ext",
                "id",
                "dob",
                "marital",
                "status",
            ],
            inplace=True,
        )

        camu_number = [camu_id for camu_id in df["camu_number"]]
        camu_chf_id = [chf_id for chf_id in df["chf_id"]]

        for n in range(len(camu_number)):
            if camu_number[n] is None:
                camu_number[n] = camu_chf_id[n]

        df2.insert(
            loc=0,
            column="Numéro CAMU",
            value=camu_number,
        )

        df2.insert(
            loc=1, column="Nom", value=[last_name for last_name in df["last_name"]]
        )
        df2.insert(
            loc=2,
            column="Prénom",
            value=[other_names for other_names in df["other_names"]],
        )
        df2.insert(loc=3, column="Date de naissance", value=insuree_dob)
        df2.insert(loc=4, column="Lieu de naissance", value=birth_place)
        df2.insert(
            loc=5,
            column="Sexe",
            value=[gender__code for gender__code in df["gender__code"]],
        )
        df2.insert(loc=6, column="État civile", value=civility)
        df2.insert(loc=7, column="Adresse", value=address)

        # df.insert(loc=13, column="Matricule", value=emp_no)
        # df.insert(loc=15, column="Salaire Brut", value=income)
        # df.insert(loc=16, column="Part Patronale %", value=employer_percentage)
        # df.insert(loc=17, column="Part Patronale", value=employer_share)
        # df.insert(loc=18, column="Part Salariale %", value=employee_percentage)
        # df.insert(loc=19, column="Part Salariale", value=employee_share)
        # df.insert(loc=20, column="Cotisation total", value=total_share)
        
        df2.insert(
            loc=8,
            column="Status d'enregistrement",
            value=[get_insuree_status(status) for status in df["status"]],
        )

        # df.rename(
        #     columns={
        #         "camu_number": "Numéro CAMU",
        #         "last_name": "Nom",
        #         "other_names": "Prénom",
        #         "chf_id": "Numéro CAMU temporaire",
        #         "gender__code": "Sexe",
        #         "phone": "Téléphone",
        #         "family__location__code": "Village",
        #         "family__head_insuree__chf_id": "ID Famille",
        #         "email": "Email",
        #     },
        #     inplace=True,
        # )

        # df.drop(
        #     columns=["json_ext", "id", "dob", "marital", "status"],
        #     inplace=True,
        # )

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = 'attachment; filename="data.xlsx"'

        # Write DataFrame to response as an Excel file
        df2.to_excel(response, index=False, header=True)
        # Write DataFrame to response as an csv file
        # df.to_csv(response, index=False, header=True)
        return response
    except Exception as e:
        logger.error("Unexpected error while exporting insurees", exc_info=e)
        return Response({"success": False, "error": str(e)}, status=500)


class LocationEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Location):
            # Define how to serialize a Location object
            return {
                "id": obj.id,
                "uuid": obj.uuid,
                "type": obj.type,
                "code": obj.code,
                "name": obj.name,
                "parent": self.default(obj.parent) if obj.parent else None,
            }
        return super().default(obj)


def map_enrolment_type_to_category(enrolment_type):
    # Define the mapping from input values to categories
    enrolment_type_mapping = {
        "Agents de l'Etat": "public_Employees",
        "Salariés du privé": "private_sector_employees",
        "Travailleurs indépendants et professions libérales": "Selfemployed_and_liberal_professions",
        "TIPL": "Selfemployed_and_liberal_professions",
        "Pensionnés CRF et CNSS": "CRF_and_CNSS_pensioners",
        "Personnes vulnérables": "vulnerable_Persons",
        "Etudiants": "students",
        "Pensionnés de la CRF et CNSS": "CRF_and_CNSS_pensioners",
        "Titulaire de pensions CRF et CNSS": "CRF_and_CNSS_pensioners",
    }

    # Check if the enrolment type exists in the mapping dictionary
    if enrolment_type in enrolment_type_mapping:
        return enrolment_type_mapping[enrolment_type]
    else:
        # If the value doesn't match any predefined category, you can handle it accordingly.
        # For example, set a default category or raise an exception.
        return None


def mapping_marital_status(marital, value=None):
    mapping = {
        "Veuf\/veuve": "W",
        "Célibataire": "S",
        "Divorcé": "D",
        "Marié": "M",
    }
    if value and marital is None:
        logger.info(
            "mapping_marital_status passing value : ",
            list(mapping.keys())[list(mapping.values()).index(value)],
        )
        return list(mapping.keys())[list(mapping.values()).index(value)]
    elif marital in mapping:
        return mapping[marital]
    else:
        """"""


def get_city(location_id):
    try:
        location = Location.objects.get(id=location_id)
        return location.parent.parent.name
    except Location.DoesNotExist:
        return " "


def get_department(location_id):
    try:
        location = Location.objects.get(id=location_id)
        return location.parent.parent.parent.name
    except Location.DoesNotExist:
        return ""


def not_declared_policy_holder(request):
    if request.method == "GET":
        declared = request.GET.get("declared", None)
        contract_from_date = request.GET.get("from_date", None)
        contract_to_date = request.GET.get("to_date", None)
        camu_code = request.GET.get("camu_code", None)
        trade_name = request.GET.get("trade_name", None)
        department = request.GET.get("department", None)

        if declared and declared.lower() == "true":
            declared = True
        else:
            declared = False

        logger.info("declared : ", declared)

        from contract.models import Contract

        today = datetime.today()
        if contract_from_date:
            contract_from_date = datetime.strptime(
                contract_from_date, "%Y-%m-%d"
            ).date()
        else:
            # if contract_from_date is None or contract_from_date == "":
            contract_from_date = today.replace(day=1)
            contract_from_date = contract_from_date.date()
        logger.info("contract_from_date : ", contract_from_date)

        if contract_to_date:
            contract_to_date = datetime.strptime(contract_to_date, "%Y-%m-%d").date()
        else:
            # if contract_to_date is None or contract_to_date == "":
            _, last_day = calendar.monthrange(today.year, today.month)
            contract_to_date = today.replace(day=last_day)
            contract_to_date = contract_to_date.date()
        logger.info("contract_to_date : ", contract_to_date)

        if contract_from_date > contract_to_date:
            error = GraphQLError("Dates are not proper!", extensions={"code": 200})
            raise error

        contract_list = list(
            set(
                Contract.objects.filter(
                    date_valid_from__date__gte=contract_from_date,
                    date_valid_to__date__lte=contract_to_date,
                    is_deleted=False,
                ).values_list("policy_holder__id", flat=True)
            )
        )
        logger.info(contract_list)
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

        if camu_code:
            ph_object = ph_object.filter(code=camu_code)

        if trade_name:
            ph_object = ph_object.filter(trade_name=trade_name)

        if department:
            ph_object = ph_object.filter(
                locations__parent__parent__parent__uuid=department
            )

        columns = [
            "code",
            "trade_name",
            "contact_name",
            "phone",
            "email",
            "locations_id",
        ]

        data_frame = pd.DataFrame.from_records(ph_object.values(*columns))

        data_frame["Department"] = data_frame["locations_id"].apply(
            lambda location_id: get_department(location_id)
        )
        data_frame["City"] = data_frame["locations_id"].apply(
            lambda location_id: get_city(location_id)
        )

        data_frame["contact_name"] = data_frame["contact_name"].apply(
            lambda x: x["contactName"] if x is not None else " "
        )

        data_frame.rename(
            columns={
                "code": "CAMU Number",
                "trade_name": "Trade Name",
                "contact_name": "Contact Name",
                "phone": "Phone",
                "email": "Email",
            },
            inplace=True,
        )
        # data_frame.rename(columns={'code':'CAMU temporaire', 'trade_name':'Nom ou Raison sociale', 'contact_name':'Nom du représentant', 'phone':'Téléphone', 'email':'E-mail','Department':'Département','City':'Ville'}, inplace=True)

        data_frame.drop(columns=["locations_id"], inplace=True)
        # data_frame
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = "attachment; filename=policyholder.xlsx"

        data_frame.to_excel(response, index=False, engine="openpyxl")
        return response

    return True


def get_emails_for_imis_administrators():
    try:
        # Fetch the role with the name 'IMIS Administrator'
        imis_admin_role = Role.objects.get(name="IMIS Administrator")

        # Fetch all InteractiveUser objects with the specified role
        imis_admin_users = InteractiveUser.objects.filter(role_id=imis_admin_role.id)

        # Extract the emails from the InteractiveUser objects, skipping records without email
        emails = [user.email for user in imis_admin_users if user.email]
        # getting unique emails
        if len(emails) > 0:
            emails = list(set(emails))

        return emails
    except Role.DoesNotExist:
        # Handle the case where the role does not exist
        logger.info("Role 'IMIS Administrator' does not exist.")
        return []
    except Exception as e:
        # Handle other exceptions if needed
        logger.info(f"An error occurred: {str(e)}")
        return []


@authentication_classes([])
@permission_classes([AllowAny])
@api_view(["GET"])
def not_declared_ph_rest(request):
    today = datetime.today()
    # if contract_from_date is None or contract_from_date == "":
    contract_from_date = today.replace(day=1)
    contract_from_date = contract_from_date.date()
    logger.info("contract_from_date : ", contract_from_date)
    # if contract_to_date is None or contract_to_date == "":
    _, last_day = calendar.monthrange(today.year, today.month)
    contract_to_date = today.replace(day=last_day)
    contract_to_date = contract_to_date.date()
    logger.info("contract_to_date : ", contract_to_date)

    # Example code structure for querying data from models
    try:
        # Query Contract model data for the previous month
        contract_list = list(
            set(
                Contract.objects.filter(
                    date_valid_from__date__gte=contract_from_date,
                    date_valid_to__date__lte=contract_to_date,
                    is_deleted=False,
                ).values_list("policy_holder__id", flat=True)
            )
        )
        logger.info(contract_list)

        # Query PolicyHolder model data based on declared flag
        ph_object = (
            PolicyHolder.objects.filter(is_deleted=False)
            .all()
            .exclude(id__in=contract_list)
        )

        # Example code for additional filtering if needed
        # if camu_code:
        #     ph_object = ph_object.filter(code=camu_code)
        #
        # if trade_name:
        #     ph_object = ph_object.filter(trade_name=trade_name)
        #
        # if department:
        #     ph_object = ph_object.filter(locations__parent__parent__parent__uuid=department)

        # Example code to extract required columns
        columns = ["code", "trade_name", "contact_name", "phone", "email"]
        data_frame = pd.DataFrame.from_records(ph_object.values(*columns))
        data_frame["contact_name"] = data_frame["contact_name"].apply(
            lambda x: x["contactName"] if x is not None else " "
        )

        data_frame.rename(
            columns={
                "code": "CAMU Number",
                "trade_name": "Trade Name",
                "contact_name": "Contact Name",
                "phone": "Phone",
                "email": "Email",
            },
            inplace=True,
        )

        # Create Excel response
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = "attachment; filename=policyholder.xlsx"
        data_frame.to_excel(response, index=False, engine="openpyxl")

        # Send email with attachment
        subject = "Non Declare Data"
        message = "Please find the attached non declared policyholder data."
        from_email = settings.EMAIL_HOST_USER
        # recipient_list = ['lakshya.soni@walkingtree.tech']
        recipient_list = get_emails_for_imis_administrators()

        email = EmailMessage(subject, message, from_email, recipient_list)
        email.attach(
            "non declare.xlsx",
            response.content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        email.send()

        return Response({"message": "Email sent successfully."})

    except Exception as e:
        logger.info("An error occurred:", str(e))
        return Response({"error": "An error occurred while processing the data."})


def request_number_cc():
    try:
        current_date = datetime.now()
        number = current_date.strftime("%m%d%H%M%S")
        return "CC{}".format(number)
    except Exception as e:
        logger.info("Error in generating request number:", e)
        return None


def create_dependent_category_change(
    user,
    code,
    insuree,
    old_category,
    new_category,
    policy_holder,
    request_type,
    status,
    income=None,
    employer_number=None,
):
    json_ext = {}
    if income and employer_number:
        json_ext = {"income": income, "employer_number": employer_number}
    cc = CategoryChange.objects.create(
        code=code,
        insuree=insuree,
        old_category=old_category,
        new_category=new_category,
        policy_holder=policy_holder,
        request_type=request_type,
        status=status,
        created_by=user,
        modified_by=user,
        json_ext=json_ext,
    )
    req_no = cc.code
    create_folder_for_cat_chnage_req(insuree, req_no, old_category, new_category)
    logger.info(
        f"CategoryChange request created for Insuree {insuree} for {request_type.lower()} request"
    )


def check_for_category_change_request(user, line, policy_holder, enrolment_type):
    try:
        insuree_id = line.get(HEADER_INSUREE_ID, "")
        camu_num = line.get(HEADER_INSUREE_CAMU_NO, "")
        income = line.get(HEADER_INCOME, "")
        employer_number = line.get(HEADER_EMPLOYER_NUMBER, "")
        insuree = None

        if insuree_id:
            insuree = Insuree.objects.filter(
                validity_to__isnull=True, chf_id=insuree_id
            ).first()

        if not insuree and camu_num:
            insuree = Insuree.objects.filter(
                validity_to__isnull=True, camu_number=camu_num
            ).first()

        if insuree:
            new_category = map_enrolment_type_to_category(enrolment_type)
            code = request_number_cc()
            old_category = insuree.json_ext.get("insureeEnrolmentType", "")
            if code:
                if insuree.family:
                    if insuree.head:
                        if new_category != old_category:
                            # Check if there's an existing category change request
                            existing_request = CategoryChange.objects.filter(
                                insuree=insuree,
                                status__in=[CC_PENDING, CC_WAITING_FOR_DOCUMENT, CC_PROCESSING, CC_WAITING_FOR_APPROVAL]
                            ).first()

                            if not existing_request:
                                create_dependent_category_change(
                                    user,
                                    code,
                                    insuree,
                                    old_category,
                                    new_category,
                                    policy_holder,
                                    "SELF_HEAD_REQ",
                                    CC_WAITING_FOR_DOCUMENT,
                                    income,
                                    employer_number,
                                )
                            return True
                        else:
                            return False
                    else:
                        create_dependent_category_change(
                            user,
                            code,
                            insuree,
                            old_category,
                            new_category,
                            policy_holder,
                            "DEPENDENT_REQ",
                            CC_WAITING_FOR_DOCUMENT,
                            income,
                            employer_number,
                        )
                        if new_category == "students":
                            send_notification_to_head(insuree)
                        return True
                else:
                    create_dependent_category_change(
                        user,
                        code,
                        insuree,
                        old_category,
                        new_category,
                        policy_holder,
                        "INDIVIDUAL_REQ",
                        CC_WAITING_FOR_DOCUMENT,
                        income,
                        employer_number,
                    )
                    return True
        return False
    except Exception as e:
        logger.info("Error in check_for_category_change_request:", e)
        return False


def manuall_check_for_category_change_request(
    user, insuree_id, policyholder_id, income, employer_number
):
    try:
        policy_holder = PolicyHolder.objects.filter(
            id=policyholder_id, is_deleted=False
        ).first()
        if not policy_holder:
            raise ValueError("Policy holder not found or deleted.")
        ph_cpb = PolicyHolderContributionPlan.objects.filter(
            policy_holder=policy_holder, is_deleted=False, date_valid_to__isnull=True
        ).first()
        if not ph_cpb:
            raise ValueError(
                "Contribution plan for the policy holder not found or deleted."
            )
        cpb = ph_cpb.contribution_plan_bundle
        if not cpb:
            raise ValueError("Contribution plan bundle not found.")
        enrolment_type = cpb.name
        insuree = Insuree.objects.filter(id=insuree_id).first()
        if not insuree:
            raise ValueError("Insuree not found.")
        line = {
            "insuree_id": insuree.chf_id,
            "camu_number": insuree.camu_number,
            "income": income,
            "employer_number": employer_number,
        }
        response = check_for_category_change_request(
            user, line, policy_holder, enrolment_type
        )
        return response
    except Exception as e:
        return False


@authentication_classes([])
@permission_classes([AllowAny])
def verify_email(request, uidb64, token, e_timestamp):
    try:
        uid = force_text(urlsafe_base64_decode(uidb64))
        user = InteractiveUser.objects.get(pk=uid)
        timestamp = force_text(urlsafe_base64_decode(e_timestamp))
    except (TypeError, ValueError, OverflowError, InteractiveUser.DoesNotExist) as e:
        logger.error(f"Error occurred while decoding parameters: {e}")
        return redirect(settings.PORTAL_FRONTEND)

    # Check if the token is valid and not expired
    if default_token_generator.check_token(user, token):
        timestamp = int(timestamp)
        logger.info("Timestamp decoded successfully.")
        expiration_time = datetime.fromtimestamp(timestamp) + timedelta(hours=24)
        logger.info(f"Expiration time calculated: {expiration_time}")
        current_time = datetime.now()
        logger.info(f"Current time: {current_time}")

        if current_time <= expiration_time:
            if not user.is_verified:
                user.is_verified = True
                user.save()
                logger.info("User verification successful.")
                return redirect(
                    settings.PORTAL_FRONTEND + "/portal/signupsuccess"
                )  # open page after verified successfully
            else:
                logger.info("User already verified.")
                return redirect(
                    settings.PORTAL_FRONTEND + "/portal/signupfailed"
                )  # open page after already verified
        else:
            logger.info("Token has expired.")
            user.delete_history()
            return redirect(
                settings.PORTAL_FRONTEND + "/portal/signupfailed"
            )  # open page when token has expired
    else:
        logger.info("Invalid token.")
        return redirect(
            settings.PORTAL_FRONTEND + "/portal/signupfailed"
        )  # open page when token is invalid


@authentication_classes([])
@permission_classes([AllowAny])
def portal_reset(request, uidb64, token, e_timestamp):
    try:
        uid = force_text(urlsafe_base64_decode(uidb64))
        user = InteractiveUser.objects.get(pk=uid)
        timestamp = force_text(urlsafe_base64_decode(e_timestamp))
    except (TypeError, ValueError, OverflowError, InteractiveUser.DoesNotExist) as e:
        logger.error(f"Error occurred while decoding parameters: {e}")
        return redirect(settings.PORTAL_FRONTEND)

    if default_token_generator.check_token(user, token):
        timestamp = int(timestamp)
        logger.info("Timestamp decoded successfully.")
        expiration_time = datetime.fromtimestamp(timestamp) + timedelta(hours=24)
        logger.info(f"Expiration time calculated: {expiration_time}")
        current_time = datetime.now()
        logger.info(f"Current time: {current_time}")

        if current_time <= expiration_time:
            return redirect(
                settings.PORTAL_FRONTEND + "/portal/set_password"
            )  # open page after verified successfully
        else:
            logger.info("Token has expired.")
            return redirect(
                settings.PORTAL_FRONTEND + "/portal/resetFailure"
            )  # open page when token has expired
    else:
        logger.info("Invalid token.")
        return redirect(settings.PORTAL_FRONTEND)  # open page when token is invalid


@authentication_classes([])
@permission_classes([AllowAny])
def deactivate_not_submitted_request(request):
    logger.info("deactivate_not_submitted_request : Start")
    thirty_days_ago = timezone.now() - timedelta(days=30)
    logger.info(
        f"deactivate_not_submitted_request : thirty_days_ago : {thirty_days_ago}"
    )
    not_submitted_ph_ids = PolicyHolder.objects.filter(
        form_ph_portal=True,
        is_submit=False,
        status=PH_STATUS_CREATED,
        date_updated__lte=thirty_days_ago,
    ).values_list("id", flat=True)
    logger.info(
        f"deactivate_not_submitted_request : not_submitted_ph_ids : {not_submitted_ph_ids}"
    )
    ph_user_ids = PolicyHolderUser.objects.filter(
        policy_holder__id__in=not_submitted_ph_ids
    ).values_list("user__i_user__id", flat=True)
    logger.info(f"deactivate_not_submitted_request : ph_user_ids : {ph_user_ids}")
    InteractiveUser.objects.filter(id__in=ph_user_ids).update(
        validity_to=timezone.now()
    )
    PolicyHolderUser.objects.filter(policy_holder__id__in=not_submitted_ph_ids).update(
        is_deleted=True
    )
    PolicyHolder.objects.filter(id__in=not_submitted_ph_ids).update(is_deleted=True)
    logger.info("deactivate_not_submitted_request : End")
    return Response({"message": "Script Successfully Run."})


@authentication_classes([])
@permission_classes([AllowAny])
def custom_policyholder_policies_expire(request):
    logger.info("====  expire_policies_manual_job  ====  start  ====")

    custom_date_str = request.GET.get("custom_date")
    policy_holder_code = request.GET.get("policy_holder_code")

    if not custom_date_str:
        return JsonResponse({"error": "custom_date parameter is required"}, status=400)

    try:
        custom_date = parse_date(custom_date_str)
        if not custom_date:
            raise ValueError("Invalid date format")
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        return JsonResponse(
            {"error": "Invalid date format. Use YYYY-MM-DD."}, status=400
        )

    if not policy_holder_code:
        return JsonResponse(
            {"error": "policy_holder_code parameter is required"}, status=400
        )

    policy_holder = PolicyHolder.objects.filter(
        code=policy_holder_code, is_deleted=False
    ).first()

    if not policy_holder:
        return JsonResponse({"error": "Policy holder not found."}, status=404)

    insuree_ids = (
        PolicyHolderInsuree.objects.filter(
            policy_holder=policy_holder,
            policy_holder__date_valid_to__isnull=True,
            policy_holder__is_deleted=False,
            date_valid_to__isnull=True,
            is_deleted=False,
        )
        .values_list("insuree_id", flat=True)
        .distinct()
    )

    ips = InsureePolicy.objects.filter(
        insuree_id__in=insuree_ids, legacy_id__isnull=True, validity_to__isnull=True
    )

    policy_ids = ips.values_list("policy_id", flat=True)

    policies_to_expire = Policy.objects.filter(
        id__in=policy_ids, expiry_date__lt=custom_date, status=Policy.STATUS_ACTIVE
    )

    expired_count = policies_to_expire.update(status=Policy.STATUS_EXPIRED)

    logger.info(
        f"====  expire_policies_manual_job  ====  {expired_count} policies expired before {custom_date} ===="
    )

    data = {"message": "Success!", "expired_count": expired_count}
    logger.info("====  expire_policies_manual_job  ====  end  ====")

    return JsonResponse(data)


def has_active_policy(insuree):
    current_date = datetime.now()
    current_date = current_date.date()
    ins_pol = (
        InsureePolicy.objects.filter(
            insuree__chf_id=insuree.chf_id,
            insuree__legacy_id__isnull=True,
            policy__legacy_id__isnull=True,
            start_date__lte=current_date,
            expiry_date__gte=current_date,
            legacy_id__isnull=True,
        )
        .order_by("-expiry_date")
        .all()
    )
    latest_record = None
    if ins_pol and len(ins_pol) > 0:
        for pol in ins_pol:
            if pol.policy.status == 2:
                latest_record = pol
                break
    return True if latest_record else False


@api_view(["GET"])
@permission_classes(
    [
        check_user_with_rights(
            PolicyholderConfig.gql_query_policyholder_perms,
        )
    ]
)
def get_declaration_details(requests, policy_holder_code):
    data = {}
    user = requests.user
    # Prepare to store contract and payment data
    contract_data = []
    earliest_payment = None
    earliest_contract = None
    # Validate inputs
    if not policy_holder_code:
        logger.error("Policy holder code is missing.")
        return JsonResponse({"errors": "Policy holder code is required."}, status=400)

    # Fetch the policy holder
    policy_holder = get_policy_holder_from_code(policy_holder_code)
    if not policy_holder:
        logger.error(f"Unknown policy holder ({policy_holder_code})")
        return JsonResponse(
            {"errors": f"Unknown policy holder ({policy_holder_code})"}, status=404
        )

    logger.info(f"Policy holder found: {policy_holder_code}")

    # Check if policy holder is locked or unlocked
    if policy_holder.status == PH_STATUS_LOCKED:
        logger.warning(f"Policy holder ({policy_holder_code}) is locked.")
        return JsonResponse(
            {"errors": f"({policy_holder_code}) Policy Holder is Locked."}, status=400
        )
    else:
        policy_holder_status = "Unlocked"
        logger.info(f"Policy holder status: {policy_holder_status}")

    # Fetch policy holder insurees
    ph_insuree_list = PolicyHolderInsuree.objects.filter(
        policy_holder=policy_holder, is_deleted=False
    )
    ph_insuree = ph_insuree_list.first()

    if not ph_insuree:
        logger.error(f"No insuree found for policy holder ({policy_holder_code})")
        return JsonResponse(
            {"errors": "No insuree found for this policy holder."}, status=404
        )

    if ph_insuree_list.count() != 1:
        logger.error(
            f"Multiple insurees attached to policy holder ({policy_holder_code})"
        )
        return JsonResponse(
            {
                "errors": f"Multiple insurees attached with this policy holder ({policy_holder_code})"
            },
            status=400,
        )

    # Check insuree's active status
    is_active = has_active_policy(ph_insuree.insuree)
    insuree_right_status = "Active" if is_active else "Inactive"
    logger.info(
        f"Insuree status for policy holder {policy_holder_code}: {insuree_right_status}"
    )

    # Fetch executable contracts
    contracts = Contract.objects.filter(
        state=Contract.STATE_EXECUTABLE, policy_holder=policy_holder, is_deleted=False
    ).order_by("date_valid_from")

    if not contracts:
        contract = {
            "policy_holder_id": policy_holder.id,
        }
        # logger.error(f"No executable contracts found for policy holder ({policy_holder_code})")
        try:
            contract_service = ContractService(user=user)
            output_data = contract_service.tipl_contract_evaluation(contract=contract)
            logger.info(
                f"Contract evaluation completed for policy holder {policy_holder.id}"
            )
        except Exception as e:
            logger.error(
                f"Error during contract evaluation for policy holder {policy_holder.id}: {str(e)}"
            )
            return JsonResponse({"errors": "Error evaluating contract."}, status=500)
        period = datetime.now().strftime("%m-%Y")
        contract_data.append(
            {
                "policy_holder": getattr(policy_holder, "trade_name", None),
                "policy_holder_code": getattr(policy_holder, "code", None),
                "insuree_right_status": insuree_right_status,
                "period": period,  # This will now show the next month's MM-YYYY
                "label": "declaration",
                "total_amount": output_data,  # Ensure this is always a Decimal (since no payment was found)
            }
        )
        data["data"] = contract_data
        logger.info(f"Returning data for policy holder: {policy_holder_code}")
        return JsonResponse(data, status=200)

    logger.info(f"Executable contracts found for policy holder: {policy_holder_code}")

    for contract in contracts:
        # Fetch the first non-approved payment for each contract
        payment = (
            Payment.objects.filter(
                contract=contract,
                legacy_id__isnull=True,
                validity_to__isnull=True,
                status=Payment.STATUS_CREATED,  # Exclude approved payments
            )
            .order_by("validity_from")
            .first()
        )

        if payment:
            logger.info(
                f"Found payment for contract: {contract.code} with amount {payment.expected_amount}"
            )
            # Check for the earliest payment
            if (
                earliest_payment is None
                or payment.validity_from < earliest_payment.validity_from
            ):
                earliest_payment = payment
                earliest_contract = contract

    if earliest_payment and earliest_contract:
        # Fetch penalties related to the earliest payment
        penalty = PaymentPenaltyAndSanction.objects.filter(
            outstanding_payment__isnull=True, payment=earliest_payment, is_deleted=False
        ).first()

        penalty_rate = None
        total_penalty_amount = Decimal(0)  # Default to 0 if no penalty

        if penalty:
            logger.info(
                f"Penalty found for payment {earliest_payment.id} with level {penalty.penalty_level}"
            )
            product_config = get_payment_product_config(earliest_payment)
            if product_config:
                if penalty.penalty_level == "1st":
                    penalty_rate = product_config.get("firstPenaltyRate", None)
                elif penalty.penalty_level == "2nd":
                    penalty_rate = product_config.get("secondPenaltyRate", None)

            # Aggregate penalty amount
            total_penalty_amount = PaymentPenaltyAndSanction.objects.filter(
                payment=earliest_payment,
                outstanding_payment__isnull=True,
                is_deleted=False,
            ).aggregate(Sum("amount"))["amount__sum"] or Decimal(0)
            logger.info(f"Total penalty amount calculated: {total_penalty_amount}")

        total_amount = total_penalty_amount + earliest_payment.expected_amount

        # Collect contract and payment details
        contract_data.append(
            {
                "policy_holder": getattr(policy_holder, "trade_name", None),
                "policy_holder_code": getattr(policy_holder, "code", None),
                "insuree_right_status": insuree_right_status,
                "period": (
                    getattr(earliest_contract, "date_valid_from", None).strftime(
                        "%m-%Y"
                    )
                    if earliest_contract and earliest_contract.date_valid_from
                    else None
                ),
                "label": (
                    f"declaration + {penalty_rate}% de penalité"
                    if penalty_rate
                    else "declaration"
                ),
                "total_amount": total_amount
                or Decimal(0),  # Ensure this is always a Decimal
            }
        )
        logger.info(
            f"Contract and payment details collected for policy holder: {policy_holder_code}"
        )
    else:
        latest_executable_contract = contracts.last()
        if latest_executable_contract and latest_executable_contract.date_valid_from:
            date_valid_from = latest_executable_contract.date_valid_from
            # Calculate the first day of the next month
            next_month = (date_valid_from.replace(day=1) + timedelta(days=32)).replace(
                day=1
            )
            period = next_month.strftime("%m-%Y")
            logger.info(
                f"Calculated future period based on last executable contract: {period}"
            )
        else:
            period = None
            logger.warning(
                f"No executable contracts available for policy holder {policy_holder_code} to calculate future period."
            )

        contract = {
            "policy_holder_id": policy_holder.id,
        }
        logger.debug(
            f"Contract prepared for policy holder {policy_holder.id}: {contract}"
        )

        try:
            contract_service = ContractService(user=user)
            output_data = contract_service.tipl_contract_evaluation(contract=contract)
            logger.info(
                f"Contract evaluation completed for policy holder {policy_holder.id}"
            )
        except Exception as e:
            logger.error(
                f"Error during contract evaluation for policy holder {policy_holder.id}: {str(e)}"
            )
            return JsonResponse({"errors": "Error evaluating contract."}, status=500)

        # Append contract data with future period
        contract_data.append(
            {
                "policy_holder": getattr(policy_holder, "trade_name", None),
                "policy_holder_code": getattr(policy_holder, "code", None),
                "insuree_right_status": insuree_right_status,
                "period": period,  # This will now show the next month's MM-YYYY
                "label": "declaration",
                "total_amount": output_data,  # Ensure this is always a Decimal (since no payment was found)
            }
        )
        logger.info(
            f"Future contract data appended for policy holder {policy_holder.id}"
        )

    data["data"] = contract_data
    logger.info(f"Returning data for policy holder: {policy_holder_code}")
    return JsonResponse(data, status=200)


@api_view(["PUT"])
@permission_classes(
    [
        check_user_with_rights(
            PolicyholderConfig.gql_query_policyholder_perms,
        )
    ]
)
def paid_contract_payment(request):
    from policyholder.services import tipl_contract_scenarios, tipl_payment_scenarios

    try:
        username = request.user.username

        # Check if the request is PUT
        if request.method != "PUT":
            logger.error("Invalid request method. Only PUT requests are allowed.")
            return JsonResponse(
                {"errors": "Invalid request method. Only PUT requests are allowed."},
                status=405,
            )

        # Parse the request body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON input: {str(e)}")
            return JsonResponse({"errors": "Invalid JSON input."}, status=400)

        # Validate required fields
        required_fields = [
            "policy_holder_code",
            "payment_amount",
            "period",
            "mmp_identifier",
            "payment_date",
            "payment_reference",
        ]
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            logger.error(f"Required field(s) missing: {missing_fields}")
            return JsonResponse(
                {"errors": f"Missing fields: {', '.join(missing_fields)}"}, status=400
            )

        policy_holder_code = data.get("policy_holder_code")
        payment_amount = data.get("payment_amount")
        period = data.get("period")
        mmp_identifier = data.get("mmp_identifier")
        payment_date = data.get("payment_date")
        payment_reference = data.get("payment_reference")

        # Fetch Bank data using mmp_identifier
        bank = Banks.objects.filter(code=mmp_identifier, is_deleted=False).first()
        if not bank:
            logger.error(f"No bank found with MMP identifier: {mmp_identifier}")
            return JsonResponse(
                {"errors": f"No bank found with MMP identifier {mmp_identifier}."},
                status=404,
            )

        # Validate payment_date format (DD-MM-YYYY)
        try:
            payment_date = datetime.strptime(payment_date, "%d-%m-%Y").date()
        except ValueError as e:
            logger.error(f"Invalid payment date format: {str(e)}")
            return JsonResponse(
                {"errors": "Invalid payment date format. Expected DD-MM-YYYY."},
                status=400,
            )

        # Validate payment_amount and ensure it is a positive decimal
        try:
            payment_amount = Decimal(payment_amount)
            if payment_amount <= 0:
                raise ValueError("Payment amount must be greater than zero.")
        except (InvalidOperation, ValueError, TypeError) as e:
            logger.error(f"Invalid payment amount: {str(e)}")
            return JsonResponse({"errors": "Invalid payment amount."}, status=400)

        # Fetch the policy holder
        try:
            policy_holder = PolicyHolder.objects.filter(
                code=policy_holder_code, is_deleted=False
            ).first()
            if not policy_holder:
                logger.error(f"No policy holder found for code: {policy_holder_code}")
                return JsonResponse({"errors": "No policy holder found."}, status=404)
        except Exception as e:
            logger.error(f"Database error while fetching policy holder: {str(e)}")
            return JsonResponse(
                {"errors": "Internal server error while fetching policy holder."},
                status=500,
            )

        # Validate and parse period (MM-YYYY format)
        try:
            period_date = datetime.strptime(period, "%m-%Y")
            start_of_period = period_date.replace(day=1)
            end_of_period = (start_of_period + relativedelta(months=1)) - timedelta(
                days=1
            )
        except ValueError as e:
            logger.error(f"Invalid period format: {str(e)}")
            return JsonResponse(
                {"errors": "Invalid period format. Expected MM-YYYY."}, status=400
            )

        # Fetch executable contracts for the policy holder that match the period
        try:
            contracts = Contract.objects.filter(
                policy_holder=policy_holder,
                state=Contract.STATE_EXECUTABLE,
                is_deleted=False,
                date_valid_from__gte=start_of_period,
                date_valid_from__lte=end_of_period,
            ).order_by("date_valid_from")

            matching_contracts = [
                contract
                for contract in contracts
                if contract.date_valid_from.strftime("%m-%Y") == period
            ]

            # If no contracts are found, create a new contract
            if not matching_contracts:
                logger.info(
                    f"No executable contracts found for period {period}. Creating a new contract."
                )
                contract = {
                    "policy_holder_id": policy_holder.id,
                    "date_valid_from": start_of_period.strftime("%Y-%m-%d"),
                    "date_valid_to": end_of_period.strftime("%Y-%m-%d"),
                    "penalty_waive_off_contract": False,
                    "penalty_waive_off_payment": False,
                }
                output = tipl_contract_scenarios(request.user, contract)
                if output:
                    payment_output = tipl_payment_scenarios(
                        request.user,
                        contract,
                        payment_date,
                        bank,
                        payment_amount,
                        payment_reference,
                    )
                    if payment_output:
                        logger.info(
                            f"Payment scenario successfully executed for contract: {contract}"
                        )
                    else:
                        logger.error("Payment scenario failed after contract creation.")
                        return JsonResponse(
                            {
                                "errors": "Failed to approve payment after contract creation."
                            },
                            status=400,
                        )

                return JsonResponse(
                    {
                        "success": f"Payment and contract created successfully for period {period}.",
                        "payment_reference": payment_reference,
                        "mmp_identifier": mmp_identifier,
                        "payment_date": payment_date.strftime("%Y-%m-%d"),
                    },
                    status=200,
                )

            # Find earliest payment for the matching contracts
            earliest_payment, earliest_contract = None, None
            for contract in matching_contracts:
                payment = (
                    Payment.objects.filter(
                        contract=contract,
                        legacy_id__isnull=True,
                        validity_to__isnull=True,
                        status=Payment.STATUS_CREATED,
                    )
                    .order_by("validity_from")
                    .first()
                )

                if payment and (
                    earliest_payment is None
                    or payment.validity_from < earliest_payment.validity_from
                ):
                    earliest_payment = payment
                    earliest_contract = contract

            if not earliest_payment or not earliest_contract:
                logger.error(f"No due payment found for the period {period}.")
                return JsonResponse(
                    {"errors": f"No due payment found for the period {period}."},
                    status=404,
                )

            # Fetch and validate penalty
            penalty = PaymentPenaltyAndSanction.objects.filter(
                outstanding_payment__isnull=True,
                payment=earliest_payment,
                is_deleted=False,
            ).first()

            total_expected_amount = earliest_payment.expected_amount
            if penalty:
                total_expected_amount += penalty.amount
                penalty.received_amount = penalty.amount
                penalty.status = PaymentPenaltyAndSanction.PENALTY_APPROVED
                earliest_payment.is_penalty_included = True
                earliest_payment.penalty_amount_paid = penalty.amount
                penalty.save(username=username)

            # Validate payment amount against expected amount
            if payment_amount not in [
                earliest_payment.expected_amount,
                total_expected_amount,
            ]:
                logger.error(
                    f"Wrong amount entered: {payment_amount}. Expected: {earliest_payment.expected_amount} or {total_expected_amount}"
                )
                return JsonResponse(
                    {"errors": f"Invalid amount. Expected {total_expected_amount}."},
                    status=400,
                )

            # Create json_ext data from the bank details
            bank_encode_id = f"BanksType:{bank.id}"
            json_ext_data = {
                "bank": {
                    "id": base64_encode(bank_encode_id),
                    "code": bank.code,
                    "name": bank.name,
                    "erpId": bank.erp_id,
                    "jsonExt": None,  # Assuming this is still None as per your example
                    "journauxId": bank.journaux_id,
                    "altLangName": bank.alt_lang_name,
                    "dateCreated": (
                        bank.date_created.strftime("%Y-%m-%d %H:%M:%S")
                        if bank.date_created
                        else None
                    ),
                    "dateUpdated": (
                        bank.date_updated.strftime("%Y-%m-%d %H:%M:%S")
                        if bank.date_updated
                        else None
                    ),
                },
                "amount": int(payment_amount),
                "receiptNo": payment_reference,
                "journauxId": bank.journaux_id,
                "payment_method_id": TIPL_PAYMENT_METHOD_ID,
            }

            # Update the earliest payment
            earliest_payment.received_amount = earliest_payment.expected_amount
            earliest_payment.status = Payment.STATUS_APPROVED
            earliest_payment.matched_date = payment_date
            earliest_payment.received_amount_transaction = [json_ext_data]
            earliest_payment.save()

            logger.info(
                f"Payment updated for contract: {earliest_contract.code}, Amount: {earliest_payment.expected_amount}"
            )

        except Exception as e:
            logger.error(f"Error during payment processing: {str(e)}", exc_info=True)
            return JsonResponse(
                {"errors": "Internal server error during payment processing."},
                status=500,
            )

        return JsonResponse(
            {
                "success": f"Payment and penalty updated successfully for period {period}.",
                "payment_reference": payment_reference,
                "mmp_identifier": mmp_identifier,
                "payment_date": payment_date.strftime("%Y-%m-%d"),
            },
            status=200,
        )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return JsonResponse({"errors": "An unexpected error occurred."}, status=500)


@api_view(["GET"])
@permission_classes(
    [
        check_user_with_rights(
            PolicyholderConfig.gql_query_policyholder_perms,
        )
    ]
)
def erp_sync_policy_holders(request):
    sync_policyholders_to_erp.delay()
    return JsonResponse({"message": "Policyholders sync started"}, status=200)


@api_view(["GET"])
def verify_user_and_update_password(request):
    user_id = request.GET.get("user_id")
    token = request.GET.get("token")
    password = request.GET.get("password")
    logger.info(f"------------------------ user_id {user_id}")
    logger.info(f"------------------------ token {token}")
    logger.info(f"------------------------ password {password}")

    i_user = InteractiveUser.objects.filter(
        uuid=user_id, password_reset_token=token
    ).first()

    if not i_user:
        return JsonResponse({"message": "Invalid user or token"}, status=400)

    # string tag and sql injection password
    if not re.match(r"^[a-zA-Z0-9]+$", password):
        return JsonResponse({"message": "Invalid password"}, status=400)

    i_user.is_verified = True
    i_user.password = password
    i_user.password_reset_token = None
    i_user.save()

    return JsonResponse({"message": "Policyholders sync started"}, status=200)
