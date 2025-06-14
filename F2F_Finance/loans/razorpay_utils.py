import razorpay
from django.conf import settings
from django.utils import timezone
from .models import Transaction

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

def create_razorpay_order(amount, upi_id, sender, loan):
    order = client.order.create({
        "amount": int(amount * 100),
        "currency": "INR",
        "payment_capture": 1,
        "notes": {
            "type": "Loan Funding",
            "upi_id": upi_id
        }
    })

    # Log INITIATED transaction
    txn = Transaction.objects.create(
        loan=loan,
        sender=sender,
        receiver=None,
        amount=amount,
        status='INITIATED',
        payment_platform='RAZORPAY',
        transaction_type='LOAN_PAYMENT',
        razorpay_order_id=order['id'],
        reference_id=f"Loan#{loan.id}-Funding",
        initiated_at=timezone.now(),
        metadata=order
    )
    return order, txn


def transfer_funds_to_user(to_user, upi_id, amount, loan, reverse=False):
    payout_note = "Loan Transfer" if not reverse else "Refund to Lender"
    
    payout = client.payout.create({
        "account_number": settings.RAZORPAY_ACCOUNT_NUMBER,
        "fund_account": {
            "account_type": "vpa",
            "vpa": {"address": upi_id},
            "contact": {
                "name": f"{to_user.profile.first_name} {to_user.profile.last_name}",
                "type": "customer",
                "email": to_user.profile.email or '',
                "contact": str(to_user.phone)
            }
        },
        "amount": int(amount * 100),
        "currency": "INR",
        "mode": "UPI",
        "purpose": "payout",
        "queue_if_low_balance": True,
        "reference_id": f"Loan#{loan.id}",
        "narration": payout_note
    })

    # Log transaction
    Transaction.objects.create(
        loan=loan,
        sender=None,
        receiver=to_user,
        amount=amount,
        status='COMPLETED',
        payment_platform='RAZORPAY',
        transaction_type='PAYOUT' if not reverse else 'REFUND',
        reference_id=f"Payout-Loan#{loan.id}",
        metadata=payout,
        completed_at=timezone.now()
    )
