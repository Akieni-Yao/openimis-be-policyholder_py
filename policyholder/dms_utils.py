import requests
from django.http import JsonResponse
from insuree.dms_utils import CNSS_CREATE_FOLDER_API_URL, get_headers_with_token


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



