from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserProfile, FinancialDetails, Loan, EMI, PaymentRequest, Transaction, Notification, KYC, OTP

admin.site.register(User)
admin.site.register(OTP)
admin.site.register(UserProfile)
admin.site.register(FinancialDetails)
admin.site.register(Loan)
admin.site.register(EMI)
admin.site.register(PaymentRequest)
admin.site.register(Transaction)
admin.site.register(Notification)
admin.site.register(KYC)
