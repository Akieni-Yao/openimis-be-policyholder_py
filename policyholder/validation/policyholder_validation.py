from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import QuerySet

from policyholder.models import PolicyHolder
from policyholder.constants import LEGAL_FORM_CHOICES, ACTIVITY_CODE_CHOICES


class PolicyHolderValidation:
    UNIQUE_DISPLAY_NAME_VALIDATION_ERROR = "Display name '{} {}' already in use"
    MISSING_MANDATORY_FIELD = "Field '{}' is mandatory"
    INVALID_EMAIL = "Invalid email address"
    INVALID_LEGAL_FORM = "Invalid legal form"
    INVALID_ACTIVITY_CODE = "Invalid activity code"

    @classmethod
    def validate_create(cls, user, **data):
        cls.validate_mandatory_fields(data, is_validation_required=True)
        cls.validate_types(data)

        code = data.get('code', None)
        trade_name = data.get('trade_name', None)
        if not cls.__unique_display_name(code, trade_name):
            raise ValidationError(cls.UNIQUE_DISPLAY_NAME_VALIDATION_ERROR.format(code, trade_name))

    @classmethod
    def validate_update(cls, user, **data):
        existing = PolicyHolder.objects.filter(id=data['id']).first()
        is_validation_required = data.get('is_validation_required', False)
        cls.validate_mandatory_fields(data, existing_instance=existing, is_validation_required=is_validation_required)
        cls.validate_types(data)

        code = data.get('code', existing.code)  # New or current
        trade_name = data.get('trade_name', existing.trade_name)  # New or current
        duplicated = PolicyHolder.objects.filter(code=code, trade_name=trade_name).exclude(id=data['id']).exists()

        if duplicated:
            raise ValidationError(cls.UNIQUE_DISPLAY_NAME_VALIDATION_ERROR.format(code, trade_name))

    @classmethod
    def validate_mandatory_fields(cls, data, existing_instance=None, is_validation_required=False):
        mandatory_fields = [
            'trade_name', 'email', 'phone', 'legal_form', 'activity_code', 'date_valid_from'
        ]

        is_update = existing_instance is not None
        if not is_update:
            mandatory_fields.remove('email') 

        strict_validation = not is_update or is_validation_required
        errors = []

        for field in mandatory_fields:
            if field in data:
                if not data[field]:
                    errors.append(cls.MISSING_MANDATORY_FIELD.format(field))
            elif strict_validation:
                if is_update and existing_instance:
                    existing_value = getattr(existing_instance, field, None)
                    if not existing_value:
                        errors.append(cls.MISSING_MANDATORY_FIELD.format(field))
                else:
                    errors.append(cls.MISSING_MANDATORY_FIELD.format(field))

        if 'locations_id' in data:
            if not data['locations_id']:
                errors.append(cls.MISSING_MANDATORY_FIELD.format('locations'))
        elif 'locations' in data:
            if not data['locations']:
                errors.append(cls.MISSING_MANDATORY_FIELD.format('locations'))
        elif strict_validation:
            if is_update and existing_instance:
                if not existing_instance.locations:
                    errors.append(cls.MISSING_MANDATORY_FIELD.format('locations'))
            else:
                errors.append(cls.MISSING_MANDATORY_FIELD.format('locations'))
        
        if errors:
            raise ValidationError(errors)

    @classmethod
    def validate_types(cls, data):
        errors = []
        if data.get('email'):
            try:
                validate_email(data['email'])
            except ValidationError:
                errors.append(cls.INVALID_EMAIL)

        if data.get('legal_form'):
            try:
                val = int(data['legal_form'])
                if val not in LEGAL_FORM_CHOICES:
                    errors.append(cls.INVALID_LEGAL_FORM)
            except (ValueError, TypeError):
                errors.append(cls.INVALID_LEGAL_FORM)

        if data.get('activity_code'):
            try:
                val = int(data['activity_code'])
                if val not in ACTIVITY_CODE_CHOICES:
                    errors.append(cls.INVALID_ACTIVITY_CODE)
            except (ValueError, TypeError):
                errors.append(cls.INVALID_ACTIVITY_CODE)
        
        if errors:
            raise ValidationError(errors)

    @classmethod
    def __unique_display_name(cls, code, trade_name):
        return not PolicyHolder.objects.filter(code=code, trade_name=trade_name).exists()
