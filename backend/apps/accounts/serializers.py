from datetime import date

from rest_framework import serializers

from .models import CustomerProfile, EmployeeProfile, Role, User, phone_validator


class CustomerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerProfile
        fields = ["phone", "date_of_birth", "address_line", "city", "state", "postal_code"]
        read_only_fields = ["date_of_birth"]


class EmployeeProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeProfile
        fields = ["employee_id", "department", "phone"]


class UserSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    customer_profile = serializers.SerializerMethodField()
    employee_profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "role", "role_display", "is_active", "is_email_verified",
                  "date_joined", "last_login", "customer_profile", "employee_profile"]
        read_only_fields = fields

    def get_customer_profile(self, obj):
        p = getattr(obj, "customer_profile", None) if obj.role == Role.CUSTOMER else None
        return CustomerProfileSerializer(p).data if p else None

    def get_employee_profile(self, obj):
        p = getattr(obj, "employee_profile", None) if obj.role != Role.CUSTOMER else None
        return EmployeeProfileSerializer(p).data if p else None


class AdminUserSerializer(UserSerializer):
    is_locked = serializers.BooleanField(read_only=True)

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["is_locked", "locked_until", "failed_login_attempts", "deleted_at"]
        read_only_fields = fields


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, min_length=8, max_length=128)
    confirm_password = serializers.CharField(write_only=True)
    full_name = serializers.CharField(min_length=2, max_length=150)
    phone = serializers.CharField(max_length=16, validators=[phone_validator])
    date_of_birth = serializers.DateField()
    address_line = serializers.CharField(max_length=255)
    city = serializers.CharField(max_length=80)
    state = serializers.CharField(max_length=80)
    postal_code = serializers.RegexField(r"^[0-9A-Za-z -]{4,10}$", max_length=10)

    def validate_date_of_birth(self, value):
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 18:
            raise serializers.ValidationError("Policyholders must be at least 18 years old.")
        if age > 120:
            raise serializers.ValidationError("Enter a valid date of birth.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("confirm_password"):
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField()


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, max_length=128)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField()
    new_password = serializers.CharField(min_length=8, max_length=128)


class ProfileUpdateSerializer(serializers.Serializer):
    """Email and date of birth are deliberately absent → cannot be changed (REQ-CUST-003)."""
    full_name = serializers.CharField(min_length=2, max_length=150, required=False)
    phone = serializers.CharField(max_length=16, validators=[phone_validator], required=False)
    address_line = serializers.CharField(max_length=255, required=False)
    city = serializers.CharField(max_length=80, required=False)
    state = serializers.CharField(max_length=80, required=False)
    postal_code = serializers.RegexField(r"^[0-9A-Za-z -]{4,10}$", max_length=10, required=False)

    def validate(self, attrs):
        forbidden = {"email", "date_of_birth"} & set(self.initial_data.keys())
        if forbidden:
            raise serializers.ValidationError({f: "This field cannot be changed." for f in forbidden})
        return attrs


class DeleteAccountSerializer(serializers.Serializer):
    password = serializers.CharField()


class EmployeeCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(min_length=2, max_length=150)
    role = serializers.ChoiceField(choices=[Role.ADJUSTER, Role.SIU, Role.ADMIN])
    employee_id = serializers.RegexField(r"^[A-Z0-9-]{3,20}$", help_text="e.g. EMP-1042")
    department = serializers.CharField(max_length=80, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=16, validators=[phone_validator], required=False, allow_blank=True)
