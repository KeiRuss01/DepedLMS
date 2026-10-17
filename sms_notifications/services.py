import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from accounts.models import User

from .models import SMSNotification


PH_MOBILE_PATTERN = re.compile(r"^\+639\d{9}$")


class TemporarySMSFailure(Exception):
    pass


class PermanentSMSFailure(Exception):
    pass


def normalize_phone_number(phone_number):
    value = str(phone_number or "").strip()
    value = re.sub(r"[\s\-()]", "", value)

    if value.startswith("09"):
        value = "+63" + value[1:]
    elif value.startswith("639"):
        value = "+" + value

    if not PH_MOBILE_PATTERN.fullmatch(value):
        raise ValueError("Invalid Philippine mobile number.")

    return value


def queue_sms(user, message_text, sms_type, reference_id):
    """Queue one SMS. This function never contacts the provider."""
    if not settings.SMS_ENABLED:
        return None, False

    if not user or user.status != User.Status.ACTIVE or not user.phone_number:
        return None, False

    try:
        phone_number = normalize_phone_number(user.phone_number)
    except ValueError:
        return None, False

    message_text = " ".join(str(message_text).split()).strip()[:320]
    if not message_text:
        return None, False

    return SMSNotification.objects.get_or_create(
        user=user,
        sms_type=sms_type,
        reference_id=reference_id,
        defaults={
            "phone_number": phone_number,
            "message_text": message_text,
        },
    )


def send_sms(sms):
    api_key = settings.SMS_API_KEY.strip()
    if not api_key:
        raise ImproperConfigured("SMS_API_KEY is missing from .env.")

    payload = json.dumps(
        {
            "recipient": sms.phone_number,
            "message": sms.message_text,
        }
    ).encode("utf-8")

    request = Request(
        settings.SMS_API_URL,
        data=payload,
        method="POST",
        headers={
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            if 200 <= response.status < 300:
                return body
            if response.status == 429 or response.status >= 500:
                raise TemporarySMSFailure(f"Provider error {response.status}.")
            raise PermanentSMSFailure(f"Request rejected: {response.status}.")
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:300]
        if error.code == 429 or error.code >= 500:
            raise TemporarySMSFailure(
                f"Temporary provider error {error.code}: {body}"
            ) from error
        raise PermanentSMSFailure(
            f"Provider rejected request {error.code}: {body}"
        ) from error
    except (URLError, TimeoutError) as error:
        raise TemporarySMSFailure(str(error)) from error
