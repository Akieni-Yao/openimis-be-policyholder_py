import json
import logging
import random
import math
import io
import calendar
from datetime import datetime
from django.utils import timezone

import pandas as pd
from django.http import JsonResponse, FileResponse, HttpResponse

from rest_framework.decorators import permission_classes, api_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from insuree.dms_utils import create_openKm_folder_for_bulkupload, send_mail_to_temp_insuree_with_pdf
from insuree.gql_mutations import temp_generate_employee_camu_registration_number
from insuree.models import Insuree, Gender, Family
from location.models import Location
from policyholder.apps import PolicyholderConfig
from policyholder.models import PolicyHolder, PolicyHolderInsuree, PolicyHolderContributionPlan
from contribution_plan.models import ContributionPlanBundleDetails
from workflow.workflow_stage import insuree_add_to_workflow
from insuree.abis_api import create_abis_insuree

logger = logging.getLogger(__name__)

HEADER_INSUREE_CAMU_NO = 'camu_number'
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
    HEADER_FAMILY_HEAD,
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
    HEADER_INCOME,
    HEADER_EMAIL,
    HEADER_EMPLOYER_NUMBER,
    HEADER_EMPLOYER_PERCENTAGE,
    HEADER_EMPLOYER_SHARE,
    HEADER_EMPLOYEE_PERCENTAGE,
    HEADER_EMPLOYEE_SHARE,
    HEADER_TOTAL_SHARE,
    HEADER_DELETE,
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
    village = (Location.objects.filter(validity_to__isnull=True,
                                       type="V",
                                       code=village_code)
               .first())
    return village


def get_or_create_family_from_line(line, village: Location, audit_user_id: int,enrolment_type):
    head_id = line[HEADER_FAMILY_HEAD]
    family = None
    if head_id:
        family = (Family.objects.filter(validity_to__isnull=True,
                                        head_insuree__chf_id=head_id,
                                        location=village)
                  .first())
    created = False

    if not family and not head_id:
        family = Family.objects.create(
            head_insuree_id=1,  # dummy
            location=village,
            audit_user_id=audit_user_id,
            status="PRE_REGISTERED",
            json_ext={"enrolmentType": map_enrolment_type_to_category(enrolment_type)}
        )
        created = True

    return family, created


def generate_available_chf_id(gender, village, dob, insureeEnrolmentType):
    data = {
        "gender_id": gender.upper(),
        "json_ext": {
            "insureelocations": {"parent": {"parent": {"parent": {"code": village.parent.parent.parent.code}}}}},
        "dob": dob,
        "insureeEnrolmentType": map_enrolment_type_to_category(insureeEnrolmentType)
    }
    return temp_generate_employee_camu_registration_number(None, data)


def get_or_create_insuree_from_line(line, family: Family, is_family_created: bool, audit_user_id: int, location=None, core_user_id=None,enrolment_type=None):
    id = line[HEADER_INSUREE_ID]
    camu_num = line[HEADER_INSUREE_CAMU_NO]
    insuree = None
    if id:
        insuree = (Insuree.objects.filter(validity_to__isnull=True, chf_id=id).first())
    if not insuree and camu_num:
        insuree = (Insuree.objects.filter(validity_to__isnull=True, camu_number=camu_num).first())

    created = False
    # if insuree:
    #     json_ext = insuree.json_ext
    #     json_ext['employeeNumber'] = line[HEADER_EMPLOYER_NUMBER]
    #     insuree.json_ext = json_ext
    #     insuree.save()
        
    if not insuree:
        insuree_dob = line[HEADER_INSUREE_DOB]
        if not isinstance(insuree_dob, datetime):
            datetime_obj = datetime.strptime(insuree_dob, "%d/%m/%Y")
            line[HEADER_INSUREE_DOB] = timezone.make_aware(datetime_obj).date()            
        
        insuree_id = generate_available_chf_id(
            line[HEADER_INSUREE_GENDER],
            location if location else family.location,
            line[HEADER_INSUREE_DOB],
            enrolment_type
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
            marital=mapping_marital_status(line[HEADER_CIVILITY]),
            email=line[HEADER_EMAIL],
            json_ext={
                "insureeEnrolmentType": map_enrolment_type_to_category(enrolment_type),
                "insureelocations": response_data,
                "BirthPlace": line[HEADER_BIRTH_LOCATION_CODE],
                "insureeaddress": line[HEADER_ADDRESS]
            }
        )
        created = True

    return insuree, created


def get_policy_holder_from_code(ph_code: str):
    return PolicyHolder.objects.filter(code=ph_code, is_deleted=False).first()

def soft_delete_insuree(line, policy_holder_code, user_id):
    id = line[HEADER_INSUREE_ID]
    camu_num = line[HEADER_INSUREE_CAMU_NO]
    insuree = None
    if id:
        insuree = (Insuree.objects.filter(validity_to__isnull=True, chf_id=id).first())
    if not insuree:
        insuree = (Insuree.objects.filter(validity_to__isnull=True, camu_number=camu_num).first())
    if insuree:
        phn = PolicyHolderInsuree.objects.filter(insuree_id=insuree.id, policy_holder__code=policy_holder_code, policy_holder__date_valid_to__isnull=True, 
                                                            policy_holder__is_deleted=False, date_valid_to__isnull=True, 
                                                            is_deleted=False).first()
        if phn:
            PolicyHolderInsuree.objects.filter(id=phn.id).update(is_deleted=True, date_valid_to=datetime.now())
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
    df.columns = [col.strip() for col in df.columns]
    org_columns = df.columns
    # Renaming the headers
    rename_columns = {
        "CAMU Number": HEADER_INSUREE_CAMU_NO,
        "Prénom": HEADER_INSUREE_OTHER_NAMES,
        "Nom": HEADER_INSUREE_LAST_NAME,
        "Tempoprary CAMU Number": HEADER_INSUREE_ID,
        "Date de naissance": HEADER_INSUREE_DOB,
        "Lieu de naissance": HEADER_BIRTH_LOCATION_CODE,
        "Sexe": HEADER_INSUREE_GENDER,
        "Civilité": HEADER_CIVILITY,
        "Téléphone": HEADER_PHONE,
        "Adresse": HEADER_ADDRESS,
        "Village": HEADER_FAMILY_LOCATION_CODE,
        "ID Famille": HEADER_FAMILY_HEAD,
        "Email": HEADER_EMAIL,
        "Matricule":HEADER_EMPLOYER_NUMBER,
        "Salaire Brut": HEADER_INCOME,
        "Part Patronale %": HEADER_EMPLOYER_PERCENTAGE,
        "Part Patronale": HEADER_EMPLOYER_SHARE,
        "Part Salariale %": HEADER_EMPLOYEE_PERCENTAGE,
        "Part Salariale": HEADER_EMPLOYEE_SHARE,
        "Cotisation total": HEADER_TOTAL_SHARE,
        "Delete": HEADER_DELETE,
    }

    df.rename(columns=rename_columns, inplace=True)

    errors = []
    logger.debug("Importing %s lines", len(df))
    
    # For output excel with error and success message
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    processed_data = pd.DataFrame()

    for index, line in df.iterrows():  # for each line in the Excel file

        total_lines += 1
        clean_line(line)
        logger.debug("Importing line %s: %s", total_lines, line)
        
        
        validation_errors = validate_line(line)
        if validation_errors:
            errors.append(f"Error line {total_lines} - validation issues ({validation_errors})")
            logger.debug(f"Error line {total_lines} - validation issues ({validation_errors})")
            total_validation_errors += 1
            
            # Adding error in output excel
            row_data = line.tolist()
            row_data.extend(["Failed", validation_errors])
            processed_data = processed_data.append(pd.Series(row_data), ignore_index=True)
            continue
        
        if line[HEADER_DELETE] and line[HEADER_DELETE].lower() == "yes":
            is_deleted = soft_delete_insuree(line, policy_holder_code, user_id)
            if is_deleted:
                continue

        village = get_village_from_line(line)
        if not village:
            errors.append(f"Error line {total_lines} - unknown village ({line[HEADER_FAMILY_LOCATION_CODE]})")
            logger.debug(f"Error line {total_lines} - unknown village ({line[HEADER_FAMILY_LOCATION_CODE]})")
            total_locations_not_found += 1
            
            # Adding error in output excel
            row_data = line.tolist()
            row_data.extend(["Failed", f"unknown village - {line[HEADER_FAMILY_LOCATION_CODE]}"])
            processed_data = processed_data.append(pd.Series(row_data), ignore_index=True)
            continue
        
        try:
            ph_cpb = PolicyHolderContributionPlan.objects.filter(policy_holder=policy_holder, is_deleted=False).first()
            if not ph_cpb:
                errors.append(
                    f"Error line {total_lines} - No contribution plan bundle with ({policy_holder.trade_name})")
                logger.debug(
                    f"Error line {total_lines} - No contribution plan bundle with ({policy_holder.trade_name})")
                total_contribution_plan_not_found += 1
                
                # Adding error in output excel
                row_data = line.tolist()
                row_data.extend(["Failed", f"No contribution plan bundle with - {policy_holder.trade_name}"])
                processed_data = processed_data.append(pd.Series(row_data), ignore_index=True)
                continue

            cpb = ph_cpb.contribution_plan_bundle
            if not cpb:
                errors.append(
                    f"Error line {total_lines} - unknown contribution plan bundle ({ph_cpb.contribution_plan_bundle})")
                logger.debug(
                    f"Error line {total_lines} - unknown contribution plan bundle ({ph_cpb.contribution_plan_bundle})")
                total_locations_not_found += 1
                
                # Adding error in output excel
                row_data = line.tolist()
                row_data.extend(["Failed", f"unknown contribution plan bundle - {ph_cpb.contribution_plan_bundle}"])
                processed_data = processed_data.append(pd.Series(row_data), ignore_index=True)
                continue

            enrolment_type = cpb.name
        except Exception as e:
            logger.error(f"Error occurred while retrieving Contribution Plan Bundle: {e}")
            enrolment_type = None
        family, family_created = get_or_create_family_from_line(line, village, user_id,enrolment_type)
        logger.debug("family_created: %s", family_created)
        if family_created:
            total_families_created += 1
        elif not family_created and family is None:
            # Adding error in output excel
            row_data = line.tolist()
            row_data.extend(["Failed", "unknown Family Head ID."])
            processed_data = processed_data.append(pd.Series(row_data), ignore_index=True)
            continue

        insuree, insuree_created = get_or_create_insuree_from_line(line, family, family_created, user_id, None, core_user_id,enrolment_type)
        logger.debug("insuree_created: %s", insuree_created)
        if insuree_created:
            total_insurees_created += 1
            try:
                logger.info("====  policyholder  ====  import_phi  ====  create_openKm_folder_for_bulkupload  ====  Start")
                user = request.user
                create_openKm_folder_for_bulkupload(user,insuree)
                logger.info("====  policyholder  ====  import_phi  ====  create_openKm_folder_for_bulkupload  ====  End")
            except Exception as e:
                logger.error(f"insuree bulk upload error for dms: {e}")
            try:
                logger.info("====  policyholder  ====  import_phi  ====  insuree_add_to_workflow  ====  Start")
                insuree_add_to_workflow(None, insuree.id, "INSUREE_ENROLLMENT", "Pre_Register")
                logger.info("====  policyholder  ====  import_phi  ====  insuree_add_to_workflow  ====  End")
                logger.info("====  policyholder  ====  import_phi  ====  create_abis_insuree  ====  Start")
                create_abis_insuree(None, insuree)
                logger.info("====  policyholder  ====  import_phi  ====  create_abis_insuree  ====  End")
            except Exception as e:
                logger.error(f"insuree bulk upload error for abis or workflow : {e}")
        elif not insuree_created:
            reason = None
            
            insuree_dob = line[HEADER_INSUREE_DOB]
            if not isinstance(insuree_dob, datetime):
                datetime_obj = datetime.strptime(insuree_dob, "%d/%m/%Y")
                line[HEADER_INSUREE_DOB] = timezone.make_aware(datetime_obj).date()
                    
            if insuree.other_names != line[HEADER_INSUREE_OTHER_NAMES]:
                reason = "Insuree First Name does not match."
            elif insuree.last_name != line[HEADER_INSUREE_LAST_NAME]:
                reason = "Insuree Last Name does not match."
            elif insuree.dob != line[HEADER_INSUREE_DOB]:
                reason = "Insuree DOB does not match."
            elif insuree.gender != GENDERS[line[HEADER_INSUREE_GENDER]]:
                reason = "Insuree Gender does not match."
            elif insuree.marital != mapping_marital_status(line[HEADER_CIVILITY]):
                reason = "Insuree Marital does not match."
                
            if reason:
                # Adding error in output excel
                row_data = line.tolist()
                row_data.extend(["Failed", reason])
                processed_data = processed_data.append(pd.Series(row_data), ignore_index=True)
                continue

        if family_created:
            family.head_insuree = insuree
            family.save()
        phi_json_ext = {}
        if line[HEADER_INCOME]:
            phi_json_ext["calculation_rule"] = {
                "income": line[HEADER_INCOME]
            }
        employer_number = None
        if line[HEADER_INCOME]:
            employer_number = line[HEADER_EMPLOYER_NUMBER]
        # PolicyHolderInsuree is HistoryModel that prevents the use of .objects.update_or_create() :(
        phi = PolicyHolderInsuree.objects.filter(insuree=insuree, policy_holder=policy_holder).first()
        if phi:
            phi._state.adding = True
            if phi.contribution_plan_bundle != cpb or phi.employer_number != employer_number or phi.json_ext != phi_json_ext:
                phi.contribution_plan_bundle = cpb
                phi.employer_number = employer_number
                # phi.json_ext = {**phi.json_ext, **phi_json_ext} if phi.json_ext else phi_json_ext
                phi.json_ext = phi_json_ext
                phi.save(username=request.user.username)
                total_phi_updated += 1
        else:
            phi = PolicyHolderInsuree(
                insuree=insuree,
                policy_holder=policy_holder,
                contribution_plan_bundle=cpb,
                json_ext=phi_json_ext,
                employer_number=employer_number
            )
            total_phi_created += 1
            phi.save(username=request.user.username)
        
        # Adding success entry in output Excel
        row_data = line.tolist()
        row_data.extend(["Success", ""])
        processed_data = processed_data.append(pd.Series(row_data), ignore_index=True)

        try:
            logger.info("---------------   if insuree have email   -------------------")
            if insuree.email:
                insuree_enrolment_type = insuree.json_ext['insureeEnrolmentType'].lower()
                send_mail_to_temp_insuree_with_pdf(insuree, insuree_enrolment_type)
                logger.info("---------------  email is sent   -------------------")
        except Exception as e:
            logger.error(f"Fail to send auto mail : {e}")
    
    output_headers = list(org_columns) + ['Status', 'Reason']

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        processed_data.to_excel(writer, sheet_name='Processed Data', index=False, header=output_headers)
        
    output.seek(0)
    response = HttpResponse(output.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=import_results.xlsx'
    
    # result = {
    #     "total_lines": total_lines,
    #     "total_insurees_created": total_insurees_created,
    #     "total_families_created": total_families_created,
    #     "total_phi_created": total_phi_created,
    #     "total_phi_updated": total_phi_updated,
    #     "total_errors": total_locations_not_found + total_contribution_plan_not_found,
    #     "total_locations_not_found": total_locations_not_found,
    #     "total_contribution_plan_not_found": total_contribution_plan_not_found,
    #     "total_validation_errors": total_validation_errors,
    #     "errors": errors,
    # }
    # logger.info("Import of PolicyHolderInsurees done")
    # return JsonResponse(data=result)
    return response



def export_phi(request, policy_holder_code):
    try:
        insuree_ids = PolicyHolderInsuree.objects.filter(policy_holder__code=policy_holder_code, policy_holder__date_valid_to__isnull=True, 
                                                            policy_holder__is_deleted=False, date_valid_to__isnull=True, 
                                                            is_deleted=False).values_list('insuree_id', flat=True).distinct()
        
        queryset = Insuree.objects.filter(validity_to__isnull=True, id__in=insuree_ids, head=True) \
                .select_related('gender', 'current_village', 'family', 'family__location', 'family__location__parent',
                                'family__location__parent__parent', 'family__location__parent__parent__parent')

        data = list(queryset.values('camu_number', 'other_names', 'last_name', 'chf_id', 'gender__code', 'phone', 
                                    'family__location__code', 'family__head_insuree__chf_id', 'email', 'json_ext', 'id', 'dob', 'marital'))

        df = pd.DataFrame(data)
        
        insuree_dob = [dob.strftime("%d/%m/%Y") for dob in df['dob']]
        df.insert(loc=4, column='Date de naissance', value=insuree_dob)

        def extract_birth_place(json_data):
            return json_data.get('BirthPlace', None) if json_data else None
        
        birth_place = [extract_birth_place(json_data) for json_data in df['json_ext']]
        df.insert(loc=5, column='Lieu de naissance', value=birth_place)
        
        def extract_civility(marital):
            return mapping_marital_status(None, marital)
            # return json_data.get('civilQuality', None) if json_data else None
        
        civility = [extract_civility(json_data) for json_data in df['marital']]
        df.insert(loc=7, column='Civilité', value=civility)
        
        def extract_address(json_data):
            return json_data.get('insureeaddress', None) if json_data else None
        
        address = [extract_address(json_data) for json_data in df['json_ext']]
        df.insert(loc=9, column='Adresse', value=address)
        
        def extract_emp_no(insuree_id, policy_holder_code):
            phn_json = PolicyHolderInsuree.objects.filter(insuree_id=insuree_id, policy_holder__code=policy_holder_code, policy_holder__date_valid_to__isnull=True, 
                                                            policy_holder__is_deleted=False, date_valid_to__isnull=True, 
                                                            is_deleted=False).first()
            # return json_data.get('employeeNumber', None) if json_data else None
            if phn_json:
                return phn_json.employer_number
            return None
        
        emp_no = [extract_emp_no(insuree_id, policy_holder_code) for insuree_id in df['id']]
        df.insert(loc=13, column='Matricule', value=emp_no)

        employee_income = dict()
        def extract_income(insuree_id, policy_holder_code):
            phn_json = PolicyHolderInsuree.objects.filter(insuree_id=insuree_id, policy_holder__code=policy_holder_code, policy_holder__date_valid_to__isnull=True, 
                                                            policy_holder__is_deleted=False, date_valid_to__isnull=True, 
                                                            is_deleted=False).first()
            if phn_json:
                json_data = phn_json.json_ext
                if json_data:
                    ei = json_data.get('calculation_rule', None).get('income', None)
                    employee_income.update({insuree_id: ei})
                    return ei
            return None
        
        income = [extract_income(insuree_id, policy_holder_code) for insuree_id in df['id']]
        df.insert(loc=15, column='Salaire Brut', value=income)
        
        conti_plan = None
        ph_cpb = PolicyHolderContributionPlan.objects.filter(policy_holder__code=policy_holder_code, is_deleted=False).first()
        if ph_cpb and ph_cpb.contribution_plan_bundle:
            cpb = ph_cpb.contribution_plan_bundle
            cpbd = ContributionPlanBundleDetails.objects.filter(contribution_plan_bundle=cpb, is_deleted=False).first()
            conti_plan = cpbd.contribution_plan if cpbd else None
        else:
            logger.debug(f"Error line {total_lines} - No contribution plan bundle with ({policy_holder.trade_name})")
        
        employer_contri_per = dict()
        def extract_employer_percentage(insuree_id):
            if conti_plan:
                json_data = conti_plan.json_ext if conti_plan.json_ext else None
                calculation_rule = json_data.get('calculation_rule', None) if json_data else None
                ercp = calculation_rule.get('employerContribution', None) if calculation_rule else None
                employer_contri_per.update({insuree_id: ercp})
                return f"{ercp}%" if ercp else None
            return None
        
        employer_percentage = [extract_employer_percentage(insuree_id) for insuree_id in df['id']]
        df.insert(loc=16, column='Part Patronale %', value=employer_percentage)
        
        employer_contri = dict()
        def extract_employer_share(insuree_id):
            try:
                if employer_contri_per[insuree_id] and employee_income[insuree_id]:
                    erc = round((float(employer_contri_per[insuree_id]) / 100) * float(employee_income[insuree_id]), 2)
                    employer_contri.update({insuree_id: erc})
                    return erc
                return None
            except Exception as e:
                return None
        
        employer_share = [extract_employer_share(insuree_id) for insuree_id in df['id']]
        df.insert(loc=17, column='Part Patronale', value=employer_share)
        
        employee_contri_per = dict()
        def extract_employee_percentage(insuree_id):
            if conti_plan:
                json_data = conti_plan.json_ext if conti_plan.json_ext else None
                calculation_rule = json_data.get('calculation_rule', None) if json_data else None
                eecp = calculation_rule.get('employeeContribution', None) if calculation_rule else None
                employee_contri_per.update({insuree_id: eecp})
                return f"{eecp}%" if eecp else None
            return None
        
        employee_percentage = [extract_employee_percentage(insuree_id) for insuree_id in df['id']]
        df.insert(loc=18, column='Part Salariale %', value=employee_percentage)
        
        employee_contri = dict()
        def extract_employee_share(insuree_id):
            try:
                if employee_income[insuree_id] and employee_contri_per[insuree_id]:
                    eec = round((float(employee_contri_per[insuree_id]) / 100) * float(employee_income[insuree_id]), 2)
                    employee_contri.update({insuree_id: eec})
                    return eec
                return None
            except Exception as e:
                return None
        
        employee_share = [extract_employee_share(insuree_id) for insuree_id in df['id']]
        df.insert(loc=19, column='Part Salariale', value=employee_share)
        
        def extract_total_share(insuree_id):
            try:
                if employee_contri[insuree_id] and employer_contri[insuree_id]:
                    total_contri = employee_contri[insuree_id] + employer_contri[insuree_id]
                    return total_contri
                return None
            except Exception as e:
                return None
        
        total_share = [extract_total_share(insuree_id) for insuree_id in df['id']]
        df.insert(loc=20, column='Cotisation total', value=total_share)
        
        df['Delete'] = ''

        df.rename(columns={'camu_number': 'CAMU Number', 'other_names': 'Prénom', 'last_name': 'Nom', 
                        'chf_id': 'Tempoprary CAMU Number', 'gender__code': 'Sexe', 'phone': 'Téléphone',
                        'family__location__code': 'Village', 'family__head_insuree__chf_id': 'ID Famille', 'email': 'Email'}, inplace=True)

        df.drop(columns=['json_ext', 'id', 'dob', 'marital'], inplace=True)

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="data.xlsx"'

        # Write DataFrame to response as an Excel file
        df.to_excel(response, index=False, header=True)
        # Write DataFrame to response as an csv file
        # df.to_csv(response, index=False, header=True)
        return response
    except Exception as e:
        logger.error("Unexpected error while exporting insurees", exc_info=e)
        return Response({'success': False, 'error': str(e)}, status=500)

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
                "parent": self.default(obj.parent) if obj.parent else None
            }
        return super().default(obj)


def map_enrolment_type_to_category(enrolment_type):
    # Define the mapping from input values to categories
    enrolment_type_mapping = {
        "Agents de l'Etat": "public_Employees",
        "Salariés du privé": "private_sector_employees",
        "Travailleurs indépendants et professions libérales": "Selfemployed_and_liberal_professions",
        "Pensionnés CRF et CNSS": "CRF_and_CNSS_pensioners",
        "Personnes vulnérables": "vulnerable_Persons",
        "Etudiants": "students",
        "Pensionnés de la CRF et CNSS": "CRF_and_CNSS_pensioners",
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
        logger.info("mapping_marital_status passing value : ", list(mapping.keys())[list(mapping.values()).index(value)])
        return list(mapping.keys())[list(mapping.values()).index(value)]
    elif marital in mapping:
        return mapping[marital]
    else:
        ""

def not_declared_policy_holder(request):
    if request.method == 'GET':
        declared = request.GET.get('declared', None)
        contract_from_date = request.GET.get('from_date', None)
        contract_to_date = request.GET.get('to_date', None)
        camu_code = request.GET.get('camu_code', None)
        trade_name = request.GET.get('trade_name', None)
        department = request.GET.get('department', None)
        
        if declared and declared.lower() == 'true':
            declared = True
        else:
            declared = False
        
        print("declared : ", declared)
        
        from contract.models import Contract
        
        today = datetime.today()
        if contract_from_date:
            contract_from_date = datetime.strptime(contract_from_date, "%Y-%m-%d").date()
        else:
            # if contract_from_date is None or contract_from_date == "":
            contract_from_date = today.replace(day=1)
            contract_from_date = contract_from_date.date()
        print("contract_from_date : ", contract_from_date)
        
        if contract_to_date:
            contract_to_date = datetime.strptime(contract_to_date, "%Y-%m-%d").date()
        else:
            # if contract_to_date is None or contract_to_date == "":
            _, last_day = calendar.monthrange(today.year, today.month)
            contract_to_date = today.replace(day=last_day)
            contract_to_date = contract_to_date.date()
        print("contract_to_date : ", contract_to_date)
            
        if contract_from_date > contract_to_date:
            error = GraphQLError("Dates are not proper!", extensions={"code": 200})
            raise error
        
        contract_list = list(set(Contract.objects.filter(
                date_valid_from__date__gte=contract_from_date, 
                date_valid_to__date__lte=contract_to_date, 
                is_deleted=False).values_list('policy_holder__id', flat=True)))
        print(contract_list)
        ph_object = None
        if declared:
            ph_object = PolicyHolder.objects.filter(id__in=contract_list, is_deleted=False).all()
        else:
            ph_object = PolicyHolder.objects.filter(is_deleted=False).all().exclude(id__in=contract_list)
        
        if camu_code:
            ph_object = ph_object.filter(code=camu_code)
        
        if trade_name:
            ph_object = ph_object.filter(trade_name=trade_name)
        
        if department:
            ph_object = ph_object.filter(locations__parent__parent__parent__uuid=department)
        
        columns = ['code', 'trade_name', 'contact_name', 'phone', 'email']
        
        data_frame = pd.DataFrame.from_records(ph_object.values(*columns))
        data_frame['contact_name'] = data_frame['contact_name'].apply(
            lambda x: x['contactName'] if x is not None else ' ')

        data_frame.rename(columns={'code': 'CAMU Number', 'trade_name': 'Trade Name', 'contact_name': 'Contact Name',
                                   'phone': 'Phone', 'email': 'Email'}, inplace=True)
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename=policyholder.xlsx'

        data_frame.to_excel(response, index=False, engine='openpyxl')
        return response
        
    return True
