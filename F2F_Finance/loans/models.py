from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager

# ----------------------------------
# USER MODEL & MANAGER
# ----------------------------------

class CustomUserManager(BaseUserManager):
    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError("Phone number is required.")
        user = self.model(phone=phone, **extra_fields)
        user.set_unusable_password()  # OTP-based auth
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(phone, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    phone = PhoneNumberField(unique=True, region='IN')  # 'IN' for India
    is_phone_verified = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return str(self.phone)


# ----------------------------------
# OTP MODEL
# ----------------------------------

class OTP(models.Model):
    phone = PhoneNumberField(region='IN')
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(minutes=5)


# ----------------------------------
# USER PROFILE (Extended Info)
# ----------------------------------

class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')

    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    gender = models.CharField(max_length=10, choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')])
    photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)

    email = models.EmailField(blank=True, null=True, unique=True)
    is_email_verified = models.BooleanField(default=False)

    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=50, blank=True, null=True)
    state = models.CharField(max_length=50, blank=True, null=True)
    country = models.CharField(max_length=50, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    last_modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of {self.user.phone}"


# ----------------------------------
# FINANCIAL DETAILS
# ----------------------------------

class FinancialDetails(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='financial_details')

    upi_id = models.CharField(max_length=50, blank=True, null=True)
    pan_number = models.CharField(max_length=20, blank=True, null=True)
    account_number = models.CharField(max_length=30, blank=True, null=True)
    ifsc_code = models.CharField(max_length=15, blank=True, null=True)

    pan_card_image = models.ImageField(upload_to='kyc_pan_docs/', blank=True, null=True)
    qr_code_image = models.ImageField(upload_to='kyc_qr_code/', blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    last_modified_at = models.DateTimeField(auto_now=True)

    is_upi_id_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"Financial Info for {self.user.phone}"


# ----------------------------------
# LOAN MODEL
# ----------------------------------

class Loan(models.Model):
    lender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='loans_given')
    borrower = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='loans_taken')

    requested_amount = models.DecimalField(max_digits=12, decimal_places=2)
    principal_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Annual interest rate in %")
    f2f_interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="f2f default interest rate in %")
    repayment_mode = models.CharField(max_length=50, choices=[
        ('ONETIME','One Time'),
        ('EMI','EMI')
    ])
    emi_start_date = models.DateField(null=True, blank=True, help_text="For EMI mode, stores 1st of the given month")
    onetime_repayment_date = models.DateField(null=True, blank=True, help_text="Exact date for one-time repayment")
    emi_tenure_months = models.PositiveIntegerField(help_text="Tenure in months", null=True, blank=True)

    principal_repaid = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    outstanding_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    status = models.CharField(
        max_length=20,
        choices=[
            ('PENDING', 'Pending'),            # Awaiting lender decision
            ('APPROVED', 'Approved'),          # Lender has funded the loan to platform
            ('REJECTED', 'Rejected'),          # Rejected by lender
            ('CANCELLED', 'Cancelled'),        # Cancelled by borrower before approval or acceptance
            ('ONGOING', 'Ongoing'),            # Borrower accepted and received funds
            ('COMPLETED', 'Completed'),        # Paid off
            ('DEFAULTED', 'Defaulted'),        # Missed payments
            ('CLOSED_EARLY', 'Closed Early')   # Paid off early
        ],
        default='PENDING'
    )

    # Dates and Actions Tracking
    approved_at = models.DateTimeField(null=True, blank=True)  # Set only when lender funds to platform
    rejected_at = models.DateTimeField(null=True, blank=True)
    cancelled_by_borrower_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)  # When borrower accepts the funded loan
    closed_at = models.DateField(null=True, blank=True)

    is_prepayment_allowed = models.BooleanField(default=True)
    is_interest_rate_modified = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    borrower_comments = models.TextField(null=True, blank=True)
    lender_remarks = models.TextField(blank=True, null=True)

    # Platform Escrow Management
    is_funded_by_lender = models.BooleanField(default=False)  # Indicates lender has sent money to platform
    funded_at = models.DateTimeField(null=True, blank=True)   # Timestamp when money was sent to platform

    def __str__(self):
        return f"Loan #{self.id} - Borrower: {self.borrower.phone}"

    def repayment_start_date(self):
        if self.repayment_mode == 'EMI':
            return self.emi_start_date
        return self.onetime_repayment_date


# ----------------------------------
# EMI / REPAYMENT TRACKER
# ----------------------------------

class EMI(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='emis')

    emi_number = models.PositiveIntegerField(help_text="1 for first EMI, 2 for second, and so on")
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    principal_component = models.DecimalField(max_digits=10, decimal_places=2)
    interest_component = models.DecimalField(max_digits=10, decimal_places=2)

    is_paid = models.BooleanField(default=False)
    payment_date = models.DateField(blank=True, null=True)
    penalty = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    
    payment_method = models.CharField(
        max_length=20,
        choices=[
            ('UPI', 'UPI'),
            ('BANK_TRANSFER', 'Bank Transfer'),
        ],
        blank=True,
        null=True
    )

    status = models.CharField(
        max_length=20,
        choices=[
        ('PENDING', 'Pending'),
        ('PAID', 'Paid'),
        ('MISSED', 'Missed'),
        ('LATE', 'Late Payment'),
        ],
        default='PENDING'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    last_modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"EMI {self.emi_number} for Loan #{self.loan.id}"

# ----------------------------------
# PAYMENT REQUESTS
# ----------------------------------

class PaymentRequest(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payment_requests_sent')
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payment_requests_received')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    purpose = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected')
    ], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment request of ₹{self.amount} from {self.sender.phone} to {self.receiver.phone}"


# ----------------------------------
# TRANSACTION LOG
# ----------------------------------

class Transaction(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='transactions_sent')
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='transactions_received')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    purpose = models.TextField(blank=True, null=True)
    loan = models.ForeignKey(Loan, on_delete=models.SET_NULL, null=True, blank=True)
    payment_request = models.ForeignKey(PaymentRequest, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transaction of ₹{self.amount} on {self.timestamp}"


# ----------------------------------
# NOTIFICATIONS
# ----------------------------------

class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"Notification for {self.user.phone}"


# ----------------------------------
# DOCUMENT VERIFICATION
# ----------------------------------

class KYC(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='kyc')
    pan_card_image = models.ImageField(upload_to='kyc_docs/', blank=True, null=True)
    qr_code_image = models.ImageField(upload_to='kyc_qr/', blank=True, null=True)
    verified = models.BooleanField(default=False)

    def __str__(self):
        return f"KYC for {self.user.phone}"
