import json
import logging

import requests
from django.conf import settings
from django.core.mail import EmailMessage
from django.http import JsonResponse, Http404

from core.utils import generate_qr
from insuree.dms_utils import CNSS_CREATE_FOLDER_API_URL, get_headers_with_token
from insuree.reports.code_converstion_for_report import convert_activity_data
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
                     "village":policyholder.locations.name if policyholder.locations else "",
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
