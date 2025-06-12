
from django.utils.timezone import now
from .models import (User, OTP, UserProfile, FinancialDetails, Loan, EMI, PaymentRequest,
                      Transaction, UserActivity, KYC)

def send_status_update(loan, status):
    borrower = loan.borrower
    lender = loan.lender
    loan_id = loan.id
    principal = loan.principal_amount
    requested_amount = loan.requested_amount
    interest = loan.interest_rate

    borrower_name = f"{borrower.profile.first_name} {borrower.profile.last_name}"
    lender_name = f"{lender.profile.first_name} {lender.profile.last_name}"

    def log(user, actor, message, activity_type):
        UserActivity.objects.create(user=user, actor=actor, activity=message, activity_type=activity_type)

    if status == 'PENDING':
        log(borrower, borrower, f"Your loan request of ₹{requested_amount} has been submitted. Loan Reference ID #{loan_id}.",'INFO')
        log(lender, borrower, f"{borrower_name} has requested a loan of ₹{requested_amount}. Reference ID #{loan_id}.",'INFO')

    elif status == 'APPROVED':
        if loan.is_interest_rate_modified:
            log(borrower, lender, f"Your loan #{loan_id} of ₹{principal} has been approved at {interest}% annual interest by {lender_name}.",'INFO')
            log(lender, lender, f"You approved loan #{loan_id} of ₹{principal} for {borrower_name} with modified interest rate {interest}%.",'INFO')
        else:
            log(borrower, lender, f"Your loan #{loan_id} of ₹{principal} has been approved & funded by {lender_name}.",'INFO')
            log(lender, lender, f"You approved & funded loan #{loan_id} of ₹{principal} for {borrower_name}.",'INFO')

    elif status == 'REJECTED':
        log(borrower, lender, f"Your loan #{loan_id} of ₹{requested_amount} was rejected by {lender_name}.",'INFO')
        log(lender, lender, f"You rejected loan #{loan_id} of ₹{requested_amount} requested by {borrower_name}.",'INFO')

    elif status == 'ONGOING':
        if loan.is_interest_rate_modified:
            log(borrower, borrower, f"You accepted loan #{loan_id} of ₹{principal} from {lender_name} at {interest}% annual interest.",'INFO')
            log(lender, borrower, f"Loan #{loan_id} of ₹{principal} accepted by {borrower_name} at {interest}% annual interest.",'INFO')
        else:
            log(borrower, borrower, f"You accepted loan #{loan_id} of ₹{principal} from {lender_name}.",'INFO')
            log(lender, borrower, f"Loan #{loan_id} of ₹{principal} accepted by {borrower_name}.",'INFO')

    elif status == 'CANCELLED':
        log(borrower, borrower, f"You cancelled loan #{loan_id} of ₹{principal} offered by {lender_name}.",'INFO')
        log(lender, borrower, f"Loan #{loan_id} of ₹{principal} cancelled by {borrower_name}. The amount will be refunded.",'INFO')


def send_emi_reminder(loan):
    # Called by scheduler - logic to send reminders 5 and 1 days before due date
    pass

def trigger_voice_call(loan):
    # Called by scheduler - voice calls 3, 1, 0 days before repayment date
    pass

def send_pdf_agreement(loan):
    # Called when borrower accepts the loan
    pass