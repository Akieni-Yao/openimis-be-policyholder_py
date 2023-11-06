import json

import requests
from django.conf import settings
from django.core.mail import EmailMessage
from django.http import JsonResponse, Http404
from insuree.dms_utils import CNSS_CREATE_FOLDER_API_URL, get_headers_with_token
from report.apps import ReportConfig
from report.services import get_report_definition, generate_report


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
Cher {trade_name},



Nous vous remercions de votre Immatriculation. Veuillez trouver ci-joint le
Certificat d’immatriculation. Pour toute question ou assistance
supplémentaire, n'hésitez pas à nous contacter au numéro suivant Phone de
la CAMU



Cordialement.

"""


def generate_pdf_for_policyholder(policyholder, report_name):
    report_config = ReportConfig.get_report(report_name)
    if not report_config:
        raise Http404("Poll does not exist")
    report_definition = get_report_definition(
        report_name, report_config["default_report"]
    )
    template_dict = json.loads(report_definition)
    formatted_date = policyholder.date_created.strftime('%Y-%m-%d')
    data = {"data": {"email": policyholder.email if hasattr(policyholder, 'email') else "",
                     "camucode": policyholder.code if hasattr(policyholder, 'code') else "",
                     "activitycode": policyholder.json_ext['jsonExt']['activityCode'] if hasattr(policyholder,
                                                                                                 'json_ext') and 'jsonExt' in policyholder.json_ext and 'activityCode' in
                                                                                         policyholder.json_ext[
                                                                                             'jsonExt'] else "",
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
                     "legalform": str(policyholder.legal_form) if hasattr(policyholder, 'legal_form') else "",
                     "phone": str(policyholder.phone) if hasattr(policyholder, 'phone') else "",
                     "address": policyholder.address['address'],
                     "city": policyholder.locations.parent.parent.name}}

    pdf = generate_report(report_name, template_dict, data)
    return pdf


def send_mail_to_policyholder_with_pdf(policyholder, report_name):
    subject = "Certificat d’Immatriculation"
    email_body = policyholder_body.format(trade_name=policyholder.trade_name)
    pdf = generate_pdf_for_policyholder(policyholder, report_name)
    email_message = EmailMessage(subject, email_body, settings.EMAIL_HOST_USER, [policyholder.email])
    email_message.attach('report.pdf', pdf, "application/pdf")
    email_message.send()
