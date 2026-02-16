from celery import shared_task
from django.db.models import Q
import logging
from policyholder.models import PolicyHolder, PolicyHolderContributionPlan
import boto3
import os
import sys
from django.conf import settings

logger = logging.getLogger(__name__)


class Utils:
    @staticmethod
    def get_policyholders_missing_erp():
        return PolicyHolder.objects.filter(
            Q(erp_partner_id__isnull=True) | Q(erp_partner_access_id__isnull=True),
            is_deleted=False,
        )


def aws_ses_service(RECIPIENT_EMAIL, subject, message, html_message=None):
    # Configuration
    AWS_EKS_ROLE_ARN = os.environ.get("AWS_EKS_ROLE_ARN")
    AWS_SES_ROLE_ARN = os.environ.get("AWS_SES_ROLE_ARN")
    AWS_REGION = os.environ.get("AWS_REGION")
    token_file = os.environ.get("AWS_WEB_IDENTITY_TOKEN_FILE")

    SENDER_EMAIL = settings.EMAIL_HOST_USER
    # RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL")
    # token_file = os.environ.get("AWS_WEB_IDENTITY_TOKEN_FILE")

    if not token_file:
        print(
            "Error: AWS_WEB_IDENTITY_TOKEN_FILE not found. Is your ServiceAccount annotated?"
        )

    with open(token_file, "r") as f:
        web_identity_token = f.read()

    # Step 1: Assume EKS Role
    print(f"--- Step 1: Assuming Local Role {AWS_EKS_ROLE_ARN} ---")
    sts_client = boto3.client("sts", region_name=AWS_REGION)

    try:
        response_b = sts_client.assume_role_with_web_identity(
            RoleArn=AWS_EKS_ROLE_ARN,
            RoleSessionName="EKSLocalSession",
            WebIdentityToken=web_identity_token,
        )
    except Exception as e:
        print(f"Failed to assume EKS Account role: {e}")
        return

    creds_b = response_b["Credentials"]

    # Step 2: Assume SES Account Role
    print(f"--- Step 2: Assuming Worker Role {AWS_SES_ROLE_ARN} ---")

    sts_account_a = boto3.client(
        "sts",
        aws_access_key_id=creds_b["AccessKeyId"],
        aws_secret_access_key=creds_b["SecretAccessKey"],
        aws_session_token=creds_b["SessionToken"],
        region_name=AWS_REGION,
    )

    try:
        response_a = sts_account_a.assume_role(
            RoleArn=AWS_SES_ROLE_ARN, RoleSessionName="CrossAccountSESSession"
        )
    except Exception as e:
        print(f"Failed to assume SES Account role: {e}")
        return

    creds_a = response_a["Credentials"]
    print("Successfully assumed Role in SES Account!")

    # Step 3: Create SES Client with SES Account credentials
    ses_client = boto3.client(
        "ses",
        aws_access_key_id=creds_a["AccessKeyId"],
        aws_secret_access_key=creds_a["SecretAccessKey"],
        aws_session_token=creds_a["SessionToken"],
        region_name=AWS_REGION,
    )

    # Step 4: Send Email
    print("--- Sending Test Email ---")

    try:
        response = ses_client.send_email(
            Source=SENDER_EMAIL,
            Destination={"ToAddresses": [RECIPIENT_EMAIL]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {
                        "Data": message,
                        "Charset": "UTF-8",
                    },
                    "Html": {
                        "Data": html_message,
                        "Charset": "UTF-8",
                    },
                },
            },
        )

        print("Email sent successfully!")
        print("Message ID:", response["MessageId"])

    except Exception as e:
        print(f"Email sending failed: {e}")
