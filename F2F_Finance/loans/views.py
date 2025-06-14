#Python Libraries
import json
import random
from decimal import Decimal

#Rest Libraries
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

#Django Libraries
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Sum, Max
# from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404, redirect

#razorpay Libraries
import razorpay

#Our App Libraries
from .models import (User, OTP, UserActivity, UserProfile, FinancialDetails, Loan, EMI, PaymentRequest,
                      Transaction, Notification, KYC)
from .serializers import (
                        CurrentUserSerializer, UserProfileSerializer, FinancialDetailsSerializer,
                        PublicUserProfileSerializer, PublicUserFinancialSerializer,
                        LoanRequestSerializer,LenderLoanRequestSerializer, 
                        BorrowerLoanRequestSerializer, LenderLoanOfferSerializer, UserActivitySerializer, EMISerializer,
                        PaymentRequestSerializer, TransactionSerializer, NotificationSerializer,
                        KYCSerializer, PhoneSerializer, OTPVerifySerializer
                    )
from .notifications import (send_status_update, send_pdf_agreement, trigger_voice_call, 
                            send_emi_reminder)
from .razorpay_utils import create_razorpay_order, transfer_funds_to_user


User = get_user_model()

def send_otp(phone, otp):
    # Replace this with actual SMS gateway logic
    print(f"[DEV] OTP sent to {phone}: {otp}")

@csrf_exempt
def razorpay_webhook(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON payload'}, status=status.HTTP_400_BAD_REQUEST)

    event = payload.get('event')

    razorpay_order_id = payload.get("payload", {}).get("payment", {}).get("entity", {}).get("order_id")
    razorpay_payment_id = payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id")
    metadata = payload.get("payload", {}).get("payment", {}).get("entity", {}).get("notes", {})

    if not razorpay_order_id or not razorpay_payment_id:
        return JsonResponse({'error': 'Missing order_id or payment_id'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        loan = Loan.objects.get(razorpay_order_id=razorpay_order_id)
    except Loan.DoesNotExist:
        return JsonResponse({'error': 'Loan not found for this Razorpay order'}, status=status.HTTP_400_BAD_REQUEST)

    if loan.status == 'ONGOING':
        return JsonResponse({'message': 'Loan already active'}, status=status.HTTP_200_OK)

    # Check if transaction already exists and marked completed
    transaction = Transaction.objects.filter(loan=loan, razorpay_order_id=razorpay_order_id).first()
    
    # If already completed, skip
    if transaction and transaction.status == "COMPLETED":
        return Response({"detail": "Transaction already processed"}, status=status.HTTP_200_OK)

    # Otherwise update or create transaction record
    if event == "payment.captured":
        if transaction:
            transaction.status = "COMPLETED"
            transaction.razorpay_payment_id = razorpay_payment_id
            transaction.completed_at = timezone.now()
            transaction.metadata = metadata or transaction.metadata
            transaction.save() 
        else:
            # Fallback case: transaction does not exist — create one
            Transaction.objects.create(
                loan=loan,
                sender=loan.lender,
                receiver=None,
                amount=loan.principal_amount,
                payment_platform="RAZORPAY",
                transaction_type="LOAN_PAYMENT",
                status="COMPLETED",
                razorpay_order_id=razorpay_order_id,
                razorpay_payment_id=razorpay_payment_id,
                metadata=metadata,
                initiated_at=timezone.now(),
                completed_at=timezone.now(),
            )

        if transaction.loan:
            loan.is_funded_by_lender = True
            loan.funded_at = timezone.now()
            loan.save()

        # Handle full loan approval
        if loan.principal_amount == loan.requested_amount and loan.status == 'APPROVED':
            borrower_upi = loan.borrower.financialdetails.upi_id
            if borrower_upi:
                transfer_funds_to_user(
                    to_user=loan.borrower,
                    upi_id=borrower_upi,
                    amount=loan.principal_amount,
                    loan=loan
                )
                loan.status = 'ONGOING'
                loan.save()
                send_status_update(loan, loan.status)
                return JsonResponse({'message': 'Full amount paid to borrower'}, status=status.HTTP_200_OK)
            else:
                return Response({"detail": "Borrower UPI ID not found"}, status=status.HTTP_400_BAD_REQUEST)

        # Handle partial loan logic
        elif loan.principal_amount < loan.requested_amount:
            if loan.status == "PARTIAL_APPROVED":
                # Wait for borrower decision
                return Response({"detail": "Partial payment received, awaiting borrower decision"}, status=status.HTTP_200_OK)
            elif loan.status == "PARTIAL_LOAN_ACCEPTED":
                borrower_upi = loan.borrower.financialdetails.upi_id
                if borrower_upi:
                    transfer_funds_to_user(
                        to_user=loan.borrower,
                        upi_id=borrower_upi,
                        amount=loan.principal_amount,
                        loan=loan
                    )
                    loan.status = "ONGOING"
                    loan.save()
                    send_status_update(loan, loan.status)
                    return Response({"detail": "Partial loan accepted, payout successful, status updated to ONGOING"}, status=status.HTTP_200_OK)
                else:
                    return Response({"detail": "Borrower UPI ID not found"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Failure webhook
    elif event == "payment.failed":
        transaction.status = 'FAILED'
        transaction.razorpay_payment_id = razorpay_payment_id
        transaction.failed_at = timezone.now()
        transaction.save()
        return JsonResponse({'message': 'Transaction marked as FAILED'}, status=status.HTTP_200_OK)

    return Response({"detail": "No action required for this loan at current status"}, status=status.HTTP_200_OK)


class SendOTPView(APIView):
    def post(self, request):
        serializer = PhoneSerializer(data=request.data)
        if serializer.is_valid():
            phone = serializer.validated_data['phone']
            otp_code = f"{random.randint(100000, 999999)}"

            # Save or update OTP
            OTP.objects.update_or_create(
                phone=phone,
                defaults={'otp_code': otp_code, 'created_at': timezone.now()}
            )

            send_otp(phone, otp_code)
            return Response({"message": "OTP sent"}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyOTPView(APIView):
    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        if serializer.is_valid():
            phone = serializer.validated_data['phone']
            otp_code = serializer.validated_data['otp_code']

            try:
                otp_record = OTP.objects.get(phone=phone, otp_code=otp_code)
                if otp_record.is_expired():
                    return Response({"error": "OTP expired"}, status=status.HTTP_400_BAD_REQUEST)

                user, created = User.objects.get_or_create(phone=phone)
                user.is_phone_verified = True
                user.save()

                otp_record.delete()

                refresh = RefreshToken.for_user(user)
                return Response({
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                    "user_id": user.id
                }, status=status.HTTP_200_OK)

            except OTP.DoesNotExist:
                return Response({"error": "Invalid OTP"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = CurrentUserSerializer(request.user)
        return Response(serializer.data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"msg": "Successfully logged out."}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({"error": "Invalid refresh token or already logged out."}, status=status.HTTP_400_BAD_REQUEST)


class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user.profile)
        return Response(serializer.data)

    def patch(self, request):
        serializer = UserProfileSerializer(request.user.profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class UserFinancialDetailsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = FinancialDetailsSerializer(request.user.financial_details)
        return Response(serializer.data)

    def patch(self, request):
        serializer = FinancialDetailsSerializer(request.user.financial_details, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PublicUserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            user_profile = UserProfile.objects.get(user=user)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        except UserProfile.DoesNotExist:
            return Response({'error': 'User profile not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = PublicUserProfileSerializer(user_profile)
        return Response(serializer.data)


class PublicUserFinancialView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            financial_details = FinancialDetails.objects.get(user=user)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        except FinancialDetails.DoesNotExist:
            return Response({'error': 'Financial detail not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = PublicUserFinancialSerializer(financial_details)
        return Response(serializer.data)


class LoanRequestCreateView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        serializer = LoanRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        lender = serializer.validated_data.get("lender")
        borrower = request.user

        if lender==borrower:
            return Response({'error':'Self loan request does not make sence.'},status=status.HTTP_400_BAD_REQUEST)

        repayment_mode = serializer.validated_data.get("repayment_mode")
        
        if repayment_mode=="ONETIME":
            loan = serializer.save(borrower=request.user,emi_start_date=None,emi_tenure_months=0)
            send_status_update(loan, "PENDING")
            return Response({"msg": "Loan request submitted."}, status=status.HTTP_201_CREATED)
        elif repayment_mode=="EMI":
            loan = serializer.save(borrower=request.user,onetime_repayment_date=None)
            send_status_update(loan, "PENDING")
            return Response({"msg": "Loan request submitted."}, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LenderLoanRequestListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        loans = Loan.objects.filter(lender=request.user,status='PENDING').order_by('-created_at')
        serializer = LenderLoanRequestSerializer(loans, many=True)
        return Response(serializer.data)


class LenderLoanRequestDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            loan = Loan.objects.get(pk=pk,lender=request.user,status='PENDING')
        except Loan.DoesNotExist:
            return Response({"error": "Loan not found or already processed."}, status=status.HTTP_404_NOT_FOUND)
        serializer = LenderLoanRequestSerializer(loan)
        return Response(serializer.data)


class BorrowerLoanRequestListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        loans = Loan.objects.filter(borrower=request.user,status='PENDING').order_by('-created_at')
        serializer = BorrowerLoanRequestSerializer(loans, many=True)
        return Response(serializer.data)


class BorrowerLoanRequestDetailView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        try:
            loan = Loan.objects.get(pk=pk, borrower=request.user, status='PENDING')
        except Loan.DoesNotExist:
            return Response({"error": "Loan not found or already processed."}, status=status.HTTP_404_NOT_FOUND)

        serializer = BorrowerLoanRequestSerializer(loan)
        return Response(serializer.data)


# Loan status Workflow
# | Step | Action                                         | Trigger                                 | Status Update                                 |
# | ---- | ---------------------------------------------- | --------------------------------------- | --------------------------------------------- |
# | 1    | Borrower requests loan                         | LoanRequestCreateView                   | `PENDING`                                     |
# | 2    | Lender approves with **full amount**           | LenderLoanOfferView                     | `APPROVED`                                    |
# | 3    | Lender pays via Razorpay                       | Razorpay webhook (`razorpay_webhook`)   | Payout to borrower → Status becomes `ONGOING` |
# | 4    | Lender approves with **partial amount**        | LenderLoanOfferView                     | `PARTIAL_APPROVED`             |
# | 5    | Lender pays partial to platform                | Razorpay webhook                        | Only logs success, no borrower payout yet     |
# | 6    | Borrower accepts loan                          | BorrowerLoanDecisionView                | `PARTIAL_LOAN_ACCEPTED`                       |
# | 7    | Razorpay payout to borrower is triggered again | Call webhook manually or via view logic | Payout done → Status updated to `ONGOING`     |
# | 8    | Borrower rejects loan                          | BorrowerLoanDecisionView                | `CANCELLED` → Refund to lender                |


class LenderLoanOfferView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        try:
            loan = Loan.objects.get(pk=pk, lender=request.user, status='PENDING')
        except Loan.DoesNotExist:
            return Response({"error": "Loan not found or already processed."}, status=status.HTTP_404_NOT_FOUND)

        serializer = LenderLoanOfferSerializer(loan, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        decision = serializer.validated_data['lender_decision']
        principal = serializer.validated_data.get('principal_amount', loan.requested_amount)
        interest = serializer.validated_data.get('interest_rate', loan.interest_rate)
        lender_remarks = serializer.validated_data.get('lender_remarks', '')

        # REJECTED
        if decision == 'REJECTED':
            loan.status = 'REJECTED'
            loan.lender_remarks = lender_remarks
            loan.rejected_at = timezone.now()
            loan.save()
            send_status_update(loan, loan.status)
            return Response({"msg": "Loan rejected successfully."}, status=status.HTTP_200_OK)

        # APPROVED
        if principal > loan.requested_amount:
            return Response({"error": "Approved amount exceeds requested."}, status=status.HTTP_400_BAD_REQUEST)
        
        if not principal or principal <= 0:
            return Response({'error': 'Principal amount must be greater than 0'}, status=status.HTTP_400_BAD_REQUEST)

        if not interest or interest < 0 or interest > 100:
            return Response({'error': 'Interest rate cannot be negative or higher than 100%'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Initiate Razorpay order for lender payment

        lender_upi_id = loan.lender.financial_details.upi_id
        if not lender_upi_id:
            return Response({'error': 'Lender UPI ID not configured'}, status=status.HTTP_400_BAD_REQUEST)

        razorpay_order = create_razorpay_order(amount=principal, upi_id=lender_upi_id)
        loan.razorpay_order_id = razorpay_order['id']
        
        # 2. Update loan
        loan.principal_amount = principal
        loan.interest_rate = interest
        loan.is_interest_rate_modified = (interest != loan.interest_rate)
        loan.lender_remarks = lender_remarks
        loan.status = 'APPROVED' if principal == loan.requested_amount else 'PARTIAL_APPROVED'
        loan.approved_at = timezone.now()
        loan.save()

        # 3. loan transaction initiate
        Transaction.objects.create(
            loan=loan,
            sender=request.user,
            receiver=None,
            amount=principal,
            status='INITIATED',
            payment_platform='RAZORPAY',
            transaction_type='LOAN_PAYMENT',
            payment_order_id=razorpay_order['id']
        )

        send_status_update(loan, loan.status)

        return Response({
            'msg': 'Loan approved. Complete payment via Razorpay link.',
            'status': loan.status,
            'order_id': razorpay_order['id'],
            'payment_url': f"https://rzp.io/i/{razorpay_order['id']}"
        })


class UserActivityListView(APIView): 
    permission_classes = [IsAuthenticated]

    def get(self, request):
        activity = UserActivity.objects.filter(user=request.user).order_by('-created_at')
        serializer = UserActivitySerializer(activity, many=True)
        return Response(serializer.data)


class BorrowerLoanDecisionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        decision = request.data.get('decision')  # "accept" or "cancel"
        try:
            loan = Loan.objects.get(pk=pk, borrower=request.user, status='PARTIAL_APPROVED')
        except Loan.DoesNotExist:
            return Response({'error': 'Loan not found or already processed'}, status=status.HTTP_404_NOT_FOUND)

        if decision == 'accept':
            loan.status = 'PARTIAL_LOAN_ACCEPTED'
            loan.accepted_at = timezone.now()
            loan.save()

            # Send partial payout now
            borrower_upi = loan.borrower.financialdetails.upi_id

            if not borrower_upi:
                return Response({'detail': 'Borrower UPI ID not configured'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                transfer_funds_to_user(
                    to_user=request.user,
                    upi_id=borrower_upi,
                    amount=loan.principal_amount,
                    loan=loan
                )
            except Exception as e:
                return Response({'detail': f'Payout failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            loan.status = 'ONGOING'
            loan.funded_at = timezone.now()
            loan.save()
            send_status_update(loan, loan.status)
            send_pdf_agreement(loan)

            return Response({'message': 'Partial loan accepted and disbursed'}, status=status.HTTP_200_OK)

        elif decision == 'cancel':
            # Refund lender
            try:
                transfer_funds_to_user(
                    to_user=loan.lender,
                    upi_id=loan.lender.financialdetails.upi_id,
                    amount=loan.principal_amount,
                    loan=loan,
                    reverse=True
                )
            except Exception as e:
                return Response({'detail': f'Refund failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            loan.status = 'CANCELLED'
            loan.save()
            send_status_update(loan, 'CANCELLED')
            return Response({'message': 'Loan offer declined. Refund processed.'}, status=status.HTTP_200_OK)

        else:
            return Response({'error': 'Invalid decision. Choose "accept" or "cancel".'}, status=status.HTTP_400_BAD_REQUEST)
        

# User Lender Payments, group by borrowers
class LenderPaymentsSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # group loans by borrower
        lender_loans = Loan.objects.filter(lender=user, status='ONGOING') 

        borrower_data = {}
        for loan in lender_loans:
            borrower = loan.borrower
            borrower_profile = borrower.profile

            if borrower.id not in borrower_data:
                borrower_data[borrower.id] = {
                    'borrower_id':borrower.id,
                    'borrower_phone':str(borrower.phone),
                    'borrower_name':f'{borrower_profile.first_name} {borrower_profile.last_name}',
                    'borrower_photo':borrower_profile.photo.url if borrower_profile.photo else None,
                    'total_lended':0,
                    'amount_recover':0,
                    'last_transaction_date':None,
                    'last_transaction_amount':0,
                }

            borrower_data[borrower.id]['total_lended'] += loan.principal_amount
            recover = Transaction.objects.filter(loan=loan, receiver=user).aggregate(total=Sum('amount'))['total'] or 0
            borrower_data[borrower.id]['amount_recover'] += recover

            last_tx = Transaction.objects.filter(loan=loan).order_by('-created_at').first()
            if last_tx and (
                borrower_data[borrower.id]['last_transaction_date'] is None or
                last_tx.created_at > borrower_data[borrower.id]['last_transaction_date']
            ):
                borrower_data[borrower.id]['last_transaction_date']=last_tx.created_at
                borrower_data[borrower.id]['last_transaction_amount']=last_tx.amount

        result = []
        for data in borrower_data.values():
            data['total_remaining'] = data['total_lended'] - data['amount_recover']  
            result.append(data)
        return Response(result)

# User Borrowed Payments, group by landers 
class BorrowedPaymentsSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # Group loans by lender
        borrowed_loans = Loan.objects.filter(borrower=user, status='ONGOING')

        lender_data = {}
        for loan in borrowed_loans:
            lender = loan.lender
            lender_profile = lender.profile

            if lender.id not in lender_data:
                lender_data[lender.id] = {
                    'lender_id': lender.id,
                    'lender_phone':str(lender.phone),
                    'lender_name': f"{lender_profile.first_name} {lender_profile.last_name}",
                    'lender_photo': lender_profile.photo.url if lender_profile.photo else None,
                    'total_borrowed': 0,
                    'total_paid': 0,
                    'last_transaction_date': None,
                    'last_transaction_amount': 0,
                }

            lender_data[lender.id]['total_borrowed'] += loan.principal_amount
            paid = Transaction.objects.filter(loan=loan, sender=user).aggregate(total=Sum('amount'))['total'] or 0
            lender_data[lender.id]['total_paid'] += paid

            last_tx = Transaction.objects.filter(loan=loan).order_by('-created_at').first()
            if last_tx and (
                lender_data[lender.id]['last_transaction_date'] is None or 
                last_tx.created_at > lender_data[lender.id]['last_transaction_date']
            ):
                lender_data[lender.id]['last_transaction_date'] = last_tx.created_at
                lender_data[lender.id]['last_transaction_amount'] = last_tx.amount if last_tx.sender == user else -last_tx.amount

        result = []
        for data in lender_data.values():
            data['total_remaining'] = data['total_borrowed'] - data['total_paid']
            result.append(data)

        return Response(result)


class PaymentRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        prs = PaymentRequest.objects.filter(sender=request.user) | PaymentRequest.objects.filter(receiver=request.user)
        serializer = PaymentRequestSerializer(prs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = PaymentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(sender=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class TransactionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        txns = Transaction.objects.filter(sender=request.user) | Transaction.objects.filter(receiver=request.user)
        serializer = TransactionSerializer(txns, many=True)
        return Response(serializer.data)


class UserNotificationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifs = Notification.objects.filter(user=request.user)
        serializer = NotificationSerializer(notifs, many=True)
        return Response(serializer.data)


class UserKYCView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = KYCSerializer(request.user.kyc)
        return Response(serializer.data)

    def put(self, request):
        serializer = KYCSerializer(request.user.kyc, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    
# class LenderLoanOfferView(APIView):
#     permission_classes = [IsAuthenticated]

#     def post(self, request, pk):
#         try:
#             loan = Loan.objects.get(pk=pk, lender=request.user, status='PENDING')
#         except Loan.DoesNotExist:
#             return Response({"error": "Loan not found or already processed."}, status=status.HTTP_404_NOT_FOUND)

#         serializer = LenderLoanOfferSerializer(loan, data=request.data, partial=True)
#         if not serializer.is_valid():
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#         lender_decision = serializer.validated_data.get("lender_decision")

#         if lender_decision == "REJECTED":
#             loan = serializer.save(
#                 status='REJECTED',
#                 rejected_at=timezone.now()
#             )
#             send_status_update(loan, "REJECTED")
#             return Response({"msg": "Loan rejected by the lender."})

#         elif lender_decision == "APPROVED":
#             principal = serializer.validated_data.get("principal_amount", loan.principal_amount)
#             if principal > loan.requested_amount:
#                 return Response({"msg": "Principal amount cannot be higher than the requested amount."}, status=status.HTTP_400_BAD_REQUEST)

#             interest_rate = serializer.validated_data.get("interest_rate", loan.interest_rate)
#             is_interest_rate_modified = interest_rate != loan.interest_rate

#             if is_interest_rate_modified or principal != loan.requested_amount:
#                 loan = serializer.save(
#                     is_funded_by_lender=True,
#                     funded_at=timezone.now(),
#                     approved_at=timezone.now(),
#                     is_interest_rate_modified=is_interest_rate_modified,
#                     status='APPROVED'
#                 )
#                 send_status_update(loan, "APPROVED")
#                 return Response({"msg": "Loan offer modified and funded to platform."})
#             else:
#                 loan = serializer.save(
#                     is_funded_by_lender=True,
#                     funded_at=timezone.now(),
#                     approved_at=timezone.now(),
#                     accepted_at=timezone.now(),
#                     status='ONGOING'
#                 )
#                 send_status_update(loan, "ONGOING")
#                 send_pdf_agreement(loan)
#                 return Response({"msg": "Loan accepted and disbursed to borrower."})

#         return Response({"msg": "No valid action taken."})

