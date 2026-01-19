"""
Utility functions for policyholder insuree imports.
Shared between views.py (synchronous) and tasks.py (asynchronous) imports.
"""
import json
import logging
import math
from datetime import datetime, timedelta

from django.utils import timezone
from insuree.models import Family, Gender, Insuree
from location.models import Location
from policyholder.models import PolicyHolder, PolicyHolderInsuree, CategoryChange
from policyholder.constants import (
    CC_PENDING, CC_WAITING_FOR_DOCUMENT, CC_PROCESSING, CC_WAITING_FOR_APPROVAL
)

from contract.utils import map_enrolment_type_to_category
from insuree.gql_mutations import temp_generate_employee_camu_registration_number
from policyholder.dms_utils import (
    create_folder_for_cat_chnage_req,
    send_notification_to_head,
)

logger = logging.getLogger(__name__)

# --- Constants ---
MINIMUM_AGE_LIMIT = 18
MINIMUM_AGE_LIMIT_FOR_STUDENTS = 16

HEADER_INSUREE_CAMU_NO = "camu_number"
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
HEADER_EMAIL = "email"
HEADER_INCOME = "income"
HEADER_EMPLOYER_NUMBER = "employer_number"
HEADER_DELETE = "Delete"

HEADERS = [
    HEADER_INSUREE_CAMU_NO,
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
    HEADER_EMAIL,
    HEADER_DELETE,
]

GENDERS = {
    "F": Gender.objects.get(code="F"),
    "M": Gender.objects.get(code="M"),
}


class LocationEncoder(json.JSONEncoder):
    """JSON encoder for Location objects."""
    def default(self, obj):
        if isinstance(obj, Location):
            return {
                "id": obj.id,
                "uuid": obj.uuid,
                "type": obj.type,
                "code": obj.code,
                "name": obj.name,
                "parent": self.default(obj.parent) if obj.parent else None,
            }
        return super().default(obj)


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


def get_village_from_line(line):
    village_code = line.get(HEADER_FAMILY_LOCATION_CODE)
    return Location.objects.filter(
        validity_to__isnull=True, type="V", code=village_code
    ).first()


def get_or_create_family_from_line(line, audit_user_id, enrolment_type, insuree, village):
    family = Family.objects.filter(
        validity_to__isnull=True, head_insuree=insuree
    ).first()

    if family:
        return family, True

    if not village:
        return None, False

    family = Family.objects.create(
        head_insuree=insuree,
        location=village,
        audit_user_id=audit_user_id,
        status="PRE_REGISTERED",
        address=line.get(HEADER_ADDRESS),
        json_ext={"enrolmentType": map_enrolment_type_to_category(enrolment_type)},
    )

    if family:
        insurees = Insuree.objects.filter(id=insuree.id).first()
        insurees.family = family
        insurees.head = True
        insurees.save()
        return family, True

    return None, False


def get_or_create_insuree_from_line(
    line,
    village,
    audit_user_id,
    user_obj,
    core_user_id=None,
    enrolment_type=None,
):
    """
    Get or create Insuree from line data.
    """
    from insuree.abis_api import create_abis_insuree
    from insuree.dms_utils import create_openKm_folder_for_bulkupload
    from workflow.workflow_stage import insuree_add_to_workflow

    id_val = line.get(HEADER_INSUREE_ID)
    camu_num = line.get(HEADER_INSUREE_CAMU_NO)
    insuree = None

    if id_val:
        insuree = Insuree.objects.filter(validity_to__isnull=True, chf_id=id_val).first()

    if not insuree and camu_num:
        insuree = Insuree.objects.filter(validity_to__isnull=True, camu_number=camu_num).first()

    if insuree:
        age = (datetime.now().date() - insuree.dob) // timedelta(days=365.25)
        current_minimum_age = MINIMUM_AGE_LIMIT
        if enrolment_type == "Etudiants":
            current_minimum_age = MINIMUM_AGE_LIMIT_FOR_STUDENTS

        if age < current_minimum_age:
            return insuree, f"L'assuré doit être âgé d'au moins {current_minimum_age} ans."
        return insuree, None

    # Create new insuree
    insuree_dob = line.get(HEADER_INSUREE_DOB)
    if not isinstance(insuree_dob, datetime):
        try:
            if isinstance(insuree_dob, str):
                datetime_obj = datetime.strptime(insuree_dob, "%d/%m/%Y")
            else:
                datetime_obj = datetime.combine(insuree_dob, datetime.min.time())
            line[HEADER_INSUREE_DOB] = timezone.make_aware(datetime_obj).date()
        except (ValueError, TypeError):
            # Logic to handle bad date should happen before calling this function
            pass

    insuree_id = generate_available_chf_id(
        line.get(HEADER_INSUREE_GENDER),
        village,
        line.get(HEADER_INSUREE_DOB),
        enrolment_type,
    )

    current_village = village
    response_string = json.dumps(current_village, cls=LocationEncoder)
    response_data = json.loads(response_string)
    
    insuree = Insuree.objects.create(
        other_names=line.get(HEADER_INSUREE_OTHER_NAMES),
        last_name=line.get(HEADER_INSUREE_LAST_NAME),
        dob=line.get(HEADER_INSUREE_DOB),
        audit_user_id=audit_user_id,
        card_issued=False,
        chf_id=insuree_id,
        gender=GENDERS.get(line.get(HEADER_INSUREE_GENDER)),
        head=False,
        current_village=current_village,
        current_address=line.get(HEADER_ADDRESS),
        phone=line.get(HEADER_PHONE),
        created_by=core_user_id,
        modified_by=core_user_id,
        marital=mapping_marital_status(line.get(HEADER_CIVILITY)),
        email=line.get(HEADER_EMAIL),
        json_ext={
            "insureeEnrolmentType": map_enrolment_type_to_category(enrolment_type),
            "insureelocations": response_data,
            "BirthPlace": line.get(HEADER_BIRTH_LOCATION_CODE),
            "insureeaddress": line.get(HEADER_ADDRESS),
        },
    )

    try:
        # UPDATED: Use the passed user_obj, do not rely on request
        if user_obj:
            create_openKm_folder_for_bulkupload(user_obj, insuree)
        
        insuree_add_to_workflow(None, insuree.id, "INSUREE_ENROLLMENT", "Pre_Register")
        create_abis_insuree(None, insuree)
    except Exception as e:
        logger.error(f"insuree bulk upload error for abis or workflow : {e}")

    if insuree:
        return insuree, None

    return None, "Impossible de créer ou de trouver l'assuré."


# --- Moved Helper Functions ---

def request_number_cc():
    try:
        current_date = datetime.now()
        number = current_date.strftime("%m%d%H%M%S")
        return "CC{}".format(number)
    except Exception as e:
        logger.info(f"Error in generating request number: {e}")
        return None


def create_dependent_category_change(
    user, code, insuree, old_category, new_category, policy_holder, request_type, status, income=None, employer_number=None
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
    logger.info(f"CategoryChange request created for Insuree {insuree} for {request_type.lower()} request")


def check_for_category_change_request(user, line, policy_holder, enrolment_type):
    try:
        insuree_id = line.get(HEADER_INSUREE_ID, "")
        camu_num = line.get(HEADER_INSUREE_CAMU_NO, "")
        income = line.get(HEADER_INCOME, "")
        employer_number = line.get(HEADER_EMPLOYER_NUMBER, "")
        insuree = None

        if insuree_id:
            insuree = Insuree.objects.filter(validity_to__isnull=True, chf_id=insuree_id).first()

        if not insuree and camu_num:
            insuree = Insuree.objects.filter(validity_to__isnull=True, camu_number=camu_num).first()

        if insuree:
            new_category = map_enrolment_type_to_category(enrolment_type)
            code = request_number_cc()
            old_category = insuree.json_ext.get("insureeEnrolmentType", "")
            
            if code and insuree.family:
                if insuree.head:
                    if new_category != old_category:
                        existing_request = CategoryChange.objects.filter(
                            insuree=insuree,
                            status__in=[CC_PENDING, CC_WAITING_FOR_DOCUMENT, CC_PROCESSING, CC_WAITING_FOR_APPROVAL],
                        ).first()

                        if not existing_request:
                            create_dependent_category_change(
                                user, code, insuree, old_category, new_category, policy_holder,
                                "SELF_HEAD_REQ", CC_WAITING_FOR_DOCUMENT, income, employer_number
                            )
                        return True
                    else:
                        return False
                else:
                    create_dependent_category_change(
                        user, code, insuree, old_category, new_category, policy_holder,
                        "DEPENDENT_REQ", CC_WAITING_FOR_DOCUMENT, income, employer_number
                    )
                    if new_category == "students":
                        send_notification_to_head(insuree)
                    return True
            else:
                create_dependent_category_change(
                    user, code, insuree, old_category, new_category, policy_holder,
                    "INDIVIDUAL_REQ", CC_WAITING_FOR_DOCUMENT, income, employer_number
                )
                return True
        return False
    except Exception as e:
        logger.info(f"Error in check_for_category_change_request: {e}")
        return False


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


def mapping_marital_status(marital, value=None):
    mapping = {
        "Veuf/veuve": "W",
        "Célibataire": "S",
        "Divorcé": "D",
        "Marié": "M",
    }
    if value and marital is None:
        return list(mapping.keys())[list(mapping.values()).index(value)]
    elif marital in mapping:
        return mapping[marital]
    else:
        return ""

def validating_insuree_on_name_dob(line, policy_holder):
    insuree_dob = line.get(HEADER_INSUREE_DOB)
    if not isinstance(insuree_dob, datetime):
        try:
            datetime_obj = datetime.strptime(insuree_dob, "%d/%m/%Y")
            line[HEADER_INSUREE_DOB] = timezone.make_aware(datetime_obj).date()
        except:
            pass

    insuree = Insuree.objects.filter(
        other_names=line.get(HEADER_INSUREE_OTHER_NAMES),
        last_name=line.get(HEADER_INSUREE_LAST_NAME),
        dob=line.get(HEADER_INSUREE_DOB),
        validity_to__isnull=True,
        legacy_id__isnull=True,
    ).first()

    return bool(insuree)

def get_policy_holder_from_code(ph_code: str):
    return PolicyHolder.objects.filter(code=ph_code, is_deleted=False).first()

def soft_delete_insuree(line, policy_holder_code, user_id):
    id_val = line.get(HEADER_INSUREE_ID)
    camu_num = line.get(HEADER_INSUREE_CAMU_NO)
    insuree = None
    if id_val:
        insuree = Insuree.objects.filter(validity_to__isnull=True, chf_id=id_val).first()
    if not insuree:
        insuree = Insuree.objects.filter(validity_to__isnull=True, camu_number=camu_num).first()
        
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