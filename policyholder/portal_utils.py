
from dotenv import load_dotenv
import os

from datetime import datetime, timedelta
import logging

import graphene
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from gitdb.utils.encoding import force_text

from core.models import InteractiveUser

logger = logging.getLogger(__name__)
load_dotenv()

PORTAL_SUBSCRIBER_URL = os.getenv("PORTAL_SUBSCRIBER_URL", "https://dev-ims.akieni.tech")


def send_verification_email(user):
    token = default_token_generator.make_token(user)
    logger.info(f"Token generated: {token}")

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    logger.info(f"User ID encoded: {uid}")

    timestamp = int(datetime.now().timestamp())
    e_timestamp = urlsafe_base64_encode(force_bytes(timestamp))
    logger.info(f"Timestamp: {timestamp}")

    verification_url = f"{settings.BACKEND_URL}/api/policyholder/verify-email/{uid}/{token}/{e_timestamp}/"
    logger.info(f"Verification URL: {verification_url}")

    subject = "Verify your email"

    message = f"Hi {user.last_name}, Please click the link below to verify your email:\n\n{verification_url}"
    logger.info("Sending verification email...")

    html_message = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Email Verification</title>
    </head>
    <body>
        <p>Hi {last_name},</p>
        <p>Please click the link below to verify your email:</p>
        <a href="{verification_url}">Verify Email</a>
    </body>
    </html>
    """.format(last_name=user.last_name, verification_url=verification_url)

    send_mail(
        subject,
        message,
        settings.EMAIL_HOST_USER,
        [user.email],
        html_message=html_message,
    )
    logger.info("Verification email sent.")


def send_password_reset_email(user):
    token = user.password_reset_token
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    domain = get_current_site(None).domain
    reset_url = f"http://{domain}/reset-password/{uid}/{token}/"

    subject = "Password Reset Request"
    message = render_to_string(
        "password_reset_email.html",
        {
            "user": user,
            "reset_url": reset_url,
        },
    )
    send_mail(subject, message, "from@example.com", [user.email])


class ForgotPassword(graphene.Mutation):
    class Arguments:
        email = graphene.String(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, email):
        try:
            user = InteractiveUser.objects.get(email=email)
        except InteractiveUser.DoesNotExist:
            return ForgotPassword(success=False, message="User does not exist.")

        # Generate password reset token
        user.password_reset_token = default_token_generator.make_token(user)
        user.password_reset_token_created_at = timezone.now()
        user.save()

        # Send password reset email
        send_password_reset_email(user)
        return ForgotPassword(success=True, message="Password reset email sent.")


class ResetPassword(graphene.Mutation):
    class Arguments:
        uidb64 = graphene.String(required=True)
        token = graphene.String(required=True)
        new_password = graphene.String(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, uidb64, token, new_password):
        try:
            uid = force_text(urlsafe_base64_decode(uidb64))
            user = InteractiveUser.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, InteractiveUser.DoesNotExist):
            user = None

        if user is not None and default_token_generator.check_token(user, token):
            # Check token expiration (e.g., 15 minutes)
            token_expiration = (
                user.password_reset_token_created_at + timezone.timedelta(minutes=15)
            )
            if timezone.now() <= token_expiration:
                user.set_password(new_password)
                user.save()
                return ResetPassword(
                    success=True, message="Password reset successfully."
                )
            else:
                return ResetPassword(
                    success=False, message="Password reset link expired."
                )
        else:
            return ResetPassword(success=False, message="Invalid password reset link.")


def make_portal_reset_password_link(user, token):
    i_user = user.i_user
    if not token:
        raise ValueError("Token is required.")
    uid = urlsafe_base64_encode(force_bytes(i_user.pk))
    expiration_time = datetime.now() + timedelta(hours=24)  # Expiring in 24 hours
    timestamp = int(expiration_time.timestamp())
    e_timestamp = urlsafe_base64_encode(force_bytes(timestamp))
    verification_url = f"{settings.BACKEND_URL}/api/policyholder/portal-reset/{uid}/{token}/{e_timestamp}/"
    return verification_url


def send_approved_or_rejected_email(user, subject, message):
    body_message = f"Hi {user['last_name']}, {message}"
    logger.info("Sending approved or rejected email...")

    html_message = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Email Verification</title>
    </head>
    <body>
        <p>Hi {last_name},</p>
        <p>{message}</p>
    </body>
    </html>
    """.format(last_name=user["last_name"], message=message)

    send_mail(
        subject,
        body_message,
        settings.EMAIL_HOST_USER,
        [user["email"]],
        html_message=html_message,
    )
    logger.info("Verification email sent.")


def send_verification_and_new_password_email(user, token, username):
    # uid = urlsafe_base64_encode(force_bytes(user.pk))
    uid = user.uuid
    logger.info(f"User ID encoded: {uid}")

    # timestamp = int(datetime.now().timestamp())
    # e_timestamp = urlsafe_base64_encode(force_bytes(timestamp))
    # logger.info(f"Timestamp: {timestamp}")

    verification_url = f"{PORTAL_SUBSCRIBER_URL}/portal/verify-user-and-update-password?user_id={uid}&token={token}&username={username}"

    logger.info(f"Verification URL: {verification_url}")

    subject = "Verify your email and update your password"

    message = f"Hi {user.last_name}, Please click the link below to verify your email:\n\n{verification_url}"
    logger.info("Sending verification email...")

    html_message = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Email Verification</title>
    </head>
    <body>
        <p>Hi {last_name},</p>
        <p>Please click the link below to verify your email:</p>
        <a href="{verification_url}">Verify Email</a>
    </body>
    </html>
    """.format(last_name=user.last_name, verification_url=verification_url)

    send_mail(
        subject,
        message,
        settings.EMAIL_HOST_USER,
        [user.email],
        html_message=html_message,
    )
    logger.info("Verification email sent.")
