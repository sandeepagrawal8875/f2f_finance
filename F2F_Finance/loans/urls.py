from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (SendOTPView, UserActivityListView, VerifyOTPView, CurrentUserView, UserProfileView,LogoutView, UserFinancialDetailsView,
                    PublicUserProfileView,PublicUserFinancialView,
                    LoanRequestCreateView, BorrowerLoanRequestListView, BorrowerLoanRequestDetailView, BorrowerLoanDecisionView, BorrowerLoanDecisionView,
                    LenderLoanRequestListView, LenderLoanRequestDetailView, LenderLoanOfferView,
                    PaymentRequestView, TransactionListView, UserNotificationView, UserKYCView,LenderPaymentsSummaryView,
                    BorrowedPaymentsSummaryView)

urlpatterns = [
    # User auth
    path('auth/otp/send/', SendOTPView.as_view(), name='auth-otp-send'),
    path('auth/otp/verify/', VerifyOTPView.as_view(), name='auth-otp-verify'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),

    # Auth User Profile & User Details urls
    path('account/me/', CurrentUserView.as_view(), name='account-me'),
    path('account/profile/', UserProfileView.as_view(), name='account-profile'),
    path('account/financial/', UserFinancialDetailsView.as_view(), name='account-financial'),
    path('account/kyc/', UserKYCView.as_view(), name='account-kyc'),
    path('account/notifications/', UserNotificationView.as_view(), name='account-notifications'),
    path('account/activity/', UserActivityListView.as_view(), name='account-activity'),

    # Public User Profile and financial-details
    path('users/<int:user_id>/profile/', PublicUserProfileView.as_view(), name='user-profile-public'),
    path('users/<int:user_id>/financial/', PublicUserFinancialView.as_view(), name='user-financial-public'),

    # Loan Requests (Borrower Side)
    path('loans/borrower/request/', LoanRequestCreateView.as_view(), name='loan-request-create'),
    path('loans/borrower/', BorrowerLoanRequestListView.as_view(), name='loan-request-list-borrower'),
    path('loans/<int:pk>/borrower/', BorrowerLoanRequestDetailView.as_view(), name='loan-request-detail-borrower'),
    path('loans/<int:pk>/borrower/decision/', BorrowerLoanDecisionView.as_view(), name='loan-request-decision-borrower'),

    # Loan Offers (Lender Side)
    path('loans/lender/', LenderLoanRequestListView.as_view(), name='loan-request-list-lender'),
    path('loans/<int:pk>/lender/', LenderLoanRequestDetailView.as_view(), name='loan-request-detail-lender'),
    path('loans/<int:pk>/lender/offer/', LenderLoanOfferView.as_view(), name='loan-request-offer-lender'),

    # loan Summary
    path('loans/summary/lended/', LenderPaymentsSummaryView.as_view(), name='loans-summary-lended'),
    path('loans/summary/borrowed/', BorrowedPaymentsSummaryView.as_view(), name='loans-summary-borrowed'),

    # payment
    path('payments/requests/', PaymentRequestView.as_view(), name='payment-requests'),
    path('payments/transactions/', TransactionListView.as_view(), name='payment-transactions'),

]




