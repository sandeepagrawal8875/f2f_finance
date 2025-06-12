from rest_framework import serializers
from django.contrib.auth import get_user_model
from phonenumber_field.serializerfields import PhoneNumberField
from .models import UserProfile, FinancialDetails, Loan, EMI, UserActivity, PaymentRequest, Transaction, Notification, KYC, OTP

User = get_user_model()

class PhoneSerializer(serializers.Serializer):
    phone = PhoneNumberField()

class OTPVerifySerializer(serializers.Serializer):
    phone = PhoneNumberField()
    otp_code = serializers.CharField(max_length=6)

class CurrentUserSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source='profile.first_name',read_only=True) 
    last_name = serializers.CharField(source='profile.last_name',read_only=True)
    photo = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'phone', 'first_name', 'last_name', 'photo']
    
    def get_photo(self, obj):
        if hasattr(obj, 'profile') and obj.profile.photo:
            return obj.profile.photo.url
        return None


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['first_name', 'last_name', 'gender', 'photo', 'email', 'is_email_verified', 'address', 'city', 'state', 'country']


class FinancialDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialDetails
        fields = ['upi_id', 'pan_number', 'account_number', 'ifsc_code', 'pan_card_image', 'qr_code_image', 'is_upi_id_verified']
        read_only_fields = ['is_upi_id_verified']


class PublicUserProfileSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(source='user.phone', read_only=True)
    
    class Meta:
        model = UserProfile
        fields = ['first_name', 'last_name', 'gender', 'photo', 'phone', 'email', 'is_email_verified', 'address', 'city', 'state', 'country']


class PublicUserFinancialSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialDetails
        fields = ['upi_id', 'is_upi_id_verified', 'qr_code_image', 'account_number', 'ifsc_code']


class LoanRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loan
        fields = [
            'id', 'lender', 'requested_amount', 'repayment_mode', 'emi_tenure_months',
            'emi_start_date', 'onetime_repayment_date', 'borrower_comments'
        ]

    def validate(self, data):
        mode = data.get('repayment_mode')
        if mode == 'EMI' and not data.get('emi_start_date'):
            raise serializers.ValidationError("EMI start date required.")
        if mode == 'ONETIME' and not data.get('onetime_repayment_date'):
            raise serializers.ValidationError("One-time repayment date required.")
        return data

class UserMinimalSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source='profile.first_name', read_only=True)
    last_name = serializers.CharField(source='profile.last_name', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'phone', 'first_name', 'last_name']

class LenderLoanRequestSerializer(serializers.ModelSerializer):
    borrower = UserMinimalSerializer()

    class Meta:
        model = Loan
        fields = '__all__'


class BorrowerLoanRequestSerializer(serializers.ModelSerializer):
    lender = UserMinimalSerializer()

    class Meta:
        model = Loan
        fields = '__all__'


# class LenderLoanOfferSerializer(serializers.ModelSerializer):
#     lender_decision = serializers.CharField(
#         max_length=20,
#         choices=[
#             ('APPROVED', 'Approved'),
#             ('REJECTED', 'Rejected'),
#         ],
#         default='REJECTED'
#     )

#     class Meta:
#         model = Loan
#         fields = ['lender_decision', 'principal_amount', 'interest_rate', 'lender_remarks']


class LenderLoanOfferSerializer(serializers.ModelSerializer):
    lender_decision = serializers.ChoiceField(
        choices=[('APPROVED', 'Approved'), ('REJECTED', 'Rejected')],
        required=True
    )
    principal_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    interest_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    lender_remarks = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Loan
        fields = ['lender_decision', 'principal_amount', 'interest_rate', 'lender_remarks']


class UserActivitySerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = UserActivity
        fields = ['id', 'activity', 'created_at', 'is_read', 'actor_name']

    def get_actor_name(self, obj):
        if obj.actor:
            return f"{obj.actor.profile.first_name} {obj.actor.profile.last_name}"
        return None


class LoanStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loan
        fields = []  # we handle status transitions in views manually


class EMISerializer(serializers.ModelSerializer):
    class Meta:
        model = EMI
        fields = '__all__'


class PaymentRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentRequest
        fields = '__all__'


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = '__all__'


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'


class KYCSerializer(serializers.ModelSerializer):
    class Meta:
        model = KYC
        fields = '__all__'


