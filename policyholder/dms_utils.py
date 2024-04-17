import json
import logging

import requests
from django.conf import settings
from django.core.mail import EmailMessage
from django.http import JsonResponse, Http404

from core.utils import generate_qr
from insuree.dms_utils import CNSS_CREATE_FOLDER_API_URL, get_headers_with_token
from insuree.models import Insuree
from insuree.reports.code_converstion_for_report import convert_activity_data
from location.models import Location
from policyholder.models import PolicyHolderInsuree, PolicyHolderContributionPlan
from report.apps import ReportConfig
from report.services import get_report_definition, generate_report

logger = logging.getLogger(__name__)


def create_policyholder_openkmfolder(data):
    camu_code = data['code']
    body_data = {
        "fileNumber": camu_code,
        "metaData": {
            "folder_type": "IMMATRICULATION EMPLOYEUR"
        }
    }
    try:
        headers = get_headers_with_token()
        response = requests.post(CNSS_CREATE_FOLDER_API_URL, json=body_data, headers=headers, verify=False)
        response.raise_for_status()  # Raise an exception for non-2xx responses
        # Process the response JSON or data
        response_data = response.json()
        print(response_data)
        return JsonResponse(response_data)
    except requests.exceptions.RequestException as e:
        # Handle connection errors or other exceptions
        return JsonResponse({"error": str(e)}, status=500)


# email template at the time of policyholder create we have to send
policyholder_body = """
Monsieur/Madame,


La demande d’immatriculation de votre entreprise a été prise en compte. Vous voudriez bien trouver en attaché votre attestation d’immatriculation au format PDF.

Cordialement,


Pour toute information, vous pouvez contacter votre téléconseiller CAMU au numéro 400
Ce courriel a été envoyé automatiquement à partir d’une adresse de messagerie système. Prière de ne pas répondre.

"""


def generate_pdf_for_policyholder(policyholder, report_name):
    # Get report configuration
    report_config = ReportConfig.get_report(report_name)
    if not report_config:
        raise Http404("Report does not exist")

    # Get report definition
    report_definition = get_report_definition(
        report_name, report_config["default_report"]
    )
    template_dict = json.loads(report_definition)

    # Format date and retrieve necessary data from policyholder
    formatted_date = policyholder.date_created.strftime('%d-%m-%Y')
    activity_code = policyholder.json_ext.get('jsonExt', {}).get('activityCode')
    converted_activity_code = convert_activity_data(activity_code)
    legal_form = str(policyholder.legal_form)
    coverted_legal_form = get_french_value(legal_form)

    # Generate QR code based on policyholder data
    data_to_encode = (
        f"Raison sociale: {policyholder.trade_name}, "
        f"CAMU Code: {policyholder.code}, "
        f"Date d’impression du document: {formatted_date}"
    )
    generated_qr_string = generate_qr(data_to_encode)
    final_img = 'data:image/png;base64,' + generated_qr_string if generated_qr_string else ""

    # Prepare data for the report
    data = {"data": {"email": policyholder.email if hasattr(policyholder, 'email') else "",
                     "camucode": policyholder.code if hasattr(policyholder, 'code') else "",
                     "activitycode": converted_activity_code if converted_activity_code else "",
                     "regdate": str(formatted_date),
                     "tradename": policyholder.trade_name if hasattr(policyholder, 'trade_name') else "",
                     "shortname": policyholder.json_ext['jsonExt']['shortName'] if hasattr(policyholder,
                                                                                           'json_ext') and 'jsonExt' in policyholder.json_ext and 'shortName' in
                                                                                   policyholder.json_ext[
                                                                                       'jsonExt'] else "",
                     "contactname": policyholder.contact_name['contactName'] if hasattr(policyholder,
                                                                                        'contact_name') and 'contactName' in policyholder.contact_name else "",
                     "RCCM": policyholder.json_ext['jsonExt']['rccm'] if hasattr(policyholder,
                                                                                 'json_ext') and 'jsonExt' in policyholder.json_ext and 'rccm' in
                                                                         policyholder.json_ext['jsonExt'] else "",
                     "NIU": policyholder.json_ext['jsonExt']['niu'] if hasattr(policyholder,
                                                                               'json_ext') and 'jsonExt' in policyholder.json_ext and 'niu' in
                                                                       policyholder.json_ext['jsonExt'] else "",
                     "mainactivity": policyholder.json_ext['jsonExt']['mainActivity'] if hasattr(policyholder,
                                                                                                 'json_ext') and 'jsonExt' in policyholder.json_ext and 'mainActivity' in
                                                                                         policyholder.json_ext[
                                                                                             'jsonExt'] else "",
                     "mailbox": policyholder.fax if hasattr(policyholder, 'fax') else "",
                     "legalform": coverted_legal_form if coverted_legal_form else "",
                     "phone": str(policyholder.phone) if hasattr(policyholder, 'phone') else "",
                     "address": policyholder.address['address'], "city": policyholder.locations.parent.parent.name,
                     "muncipality": policyholder.locations.parent.name if policyholder.locations else "",
                     "village": policyholder.locations.name if policyholder.locations else "",
                     "qrcode": final_img}}
    if final_img:
        elements = template_dict.get("docElements")
        for e in elements:
            if "source" in e.keys():
                if e["source"] == "${data.qrcode}":
                    e["image"] = final_img
                    e.pop("source")
                    # e["source"] = ""
                    break
    pdf = generate_report(report_name, template_dict, data)
    return pdf


def send_mail_to_policyholder_with_pdf(policyholder, report_name):
    subject = "ATTESTATION D'IMMATRICULATION"
    email_body = policyholder_body
    pdf = generate_pdf_for_policyholder(policyholder, report_name)
    email_message = EmailMessage(subject, email_body, settings.EMAIL_HOST_USER, [policyholder.email])
    email_message.attach('ATTESTATION D''IMMATRICULATION.pdf', pdf, "application/pdf")
    email_message.send()


def get_french_value(number):
    legal_form_options = {
        "1": "Association/ Syndicat physique",
        "2": "SA/ SAU/ SAS",
        "3": "Confession religieuse",
        "4": "Collectivité publique",
        "5": "Coopérative/ Société mutualiste/ GIE",
        "6": "Établissement individuel/ EURL",
        "7": "Établissement public",
        "8": "Fondation/ ONG",
        "9": "Organisation Internationale/ Représentation diplo",
        "10": "SARL/ SARLU",
        "11": "Autre à risque limité"
    }

    return legal_form_options.get(number, "")


def create_folder_for_policy_holder_exception(user, policy_holder, ph_exc_code):
    opt_station = None
    try:
        if user and hasattr(user, 'station') and hasattr(
                user.station, 'name'):
            opt_station = user.station.name
    except Exception as exc:
        logger.exception("Failed to get station data. Error: %s", exc)
    body_data = {
        "fileNumber": ph_exc_code,
        "metaData": {
            "folder_type": "POLICY_HOLDER_EXCEPTION"
        },
        "center": opt_station,
        "parent": policy_holder.code
    }
    try:
        headers = get_headers_with_token()
        response = requests.post(CNSS_CREATE_FOLDER_API_URL, json=body_data, headers=headers, verify=False)
        response.raise_for_status()  # Raise an exception for non-2xx responses
        # Process the response JSON or data
        response_data = response.json()
        print(response_data)
        return JsonResponse(response_data)
    except requests.exceptions.RequestException as e:
        # Handle connection errors or other exceptions
        return JsonResponse({"error": str(e)}, status=500)


def create_folder_for_cat_chnage_req(insuree, req_no):
    body_data = {
        "fileNumber": req_no,
        "metaData": {
            "folder_type": "CATEGORY_CHANGE_REQ"
        },
        "parent": insuree.chf_id
    }
    try:
        headers = get_headers_with_token()
        response = requests.post(CNSS_CREATE_FOLDER_API_URL, json=body_data, headers=headers, verify=False)
        response.raise_for_status()  # Raise an exception for non-2xx responses
        # Process the response JSON or data
        response_data = response.json()
        print(response_data)
        return JsonResponse(response_data)
    except requests.exceptions.RequestException as e:
        # Handle connection errors or other exceptions
        return JsonResponse({"error": str(e)}, status=500)


beneficiary_remove_notification = """
Hello {hoi_name},

Your beneficiary {sd_name} with camu number {sd_camu} is removed him/her from the family.

Thank you
"""


def send_beneficiary_remove_notification(old_insuree_obj_id):
    old_insuree_obj = Insuree.objects.filter(id=old_insuree_obj_id).first()
    if old_insuree_obj:
        family_head = Insuree.objects.filter(
            family=old_insuree_obj_id.family,
            head=True,
            legacy_id__isnull=True,
            validity_to__isnull=True
        ).first()
        if family_head and family_head.email:
            hoi_name = "{} {}".format(family_head.last_name, family_head.other_names)
            sd_name = "{} {}".format(old_insuree_obj.last_name, old_insuree_obj.other_names)
            subject = "Removed your Son/Daughter form family because exception period is over."
            email_body = beneficiary_remove_notification.format(
                hoi_name=hoi_name,
                sd_name=sd_name,
                sd_camu=old_insuree_obj.camu_number
            )
            email_message = EmailMessage(
                subject,
                email_body,
                settings.EMAIL_HOST_USER,
                [family_head.email]
            )
            email_message.send()


def get_location_from_insuree(insuree):
    json_data = insuree.json_ext
    location = None
    if json_data:
        code_value = json_data['insureelocations']['code']
        location = Location.objects.filter(validity_to__isnull=True,
                                       type="V",
                                       code=code_value).first()
    return location


def create_phi_for_cat_change(user, cc):
    insuree = cc.insuree
    policy_holder = cc.policy_holder
    json_ext = cc.json_ext
    phi_json_ext = {}
    income = None
    employer_number = None
    phi = PolicyHolderInsuree.objects.filter(insuree=insuree, policy_holder=policy_holder).first()
    ph_cpb = PolicyHolderContributionPlan.objects.filter(policy_holder=policy_holder, is_deleted=False).first()

    if not insuree or not policy_holder:
        logger.error("Insuree or policy holder is null. Aborting...")
        return False

    if not ph_cpb:
        logger.error("No valid contribution plan found for the policy holder. Aborting...")
        return False

    cpb = ph_cpb.contribution_plan_bundle

    if json_ext:
        income = json_ext.get('income', '')
        employer_number = json_ext.get('employer_number', '')

    phi_json_ext["calculation_rule"] = {
        "income": income
    }

    if phi:
        logger.info("PolicyHolderInsuree already exists for the insuree and policy holder.")
        return False
    else:
        try:
            new_phi = PolicyHolderInsuree(
                insuree=insuree,
                policy_holder=policy_holder,
                contribution_plan_bundle=cpb,
                employer_number=employer_number,
                json_ext=phi_json_ext,
            )
            new_phi.save(username=user.username)
            logger.info("PolicyHolderInsuree created successfully.")
            return True
        except Exception as e:
            logger.error(f"Error occurred while creating PolicyHolderInsuree: {str(e)}")
            return False

