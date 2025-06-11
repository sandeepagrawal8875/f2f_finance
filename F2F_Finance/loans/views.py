#Python Libraries
import random

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

#Our App Libraries
from .models import (User, OTP, UserProfile, FinancialDetails, Loan, EMI, PaymentRequest,
                      Transaction, Notification, KYC)
from .serializers import (
    CurrentUserSerializer, UserProfileSerializer, FinancialDetailsSerializer,
    PublicUserProfileSerializer, PublicUserFinancialSerializer,
    LoanRequestSerializer,LenderLoanRequestSerializer, 
    BorrowerLoanRequestSerializer, LenderLoanOfferSerializer, EMISerializer,
    PaymentRequestSerializer, TransactionSerializer, NotificationSerializer,
    KYCSerializer, PhoneSerializer, OTPVerifySerializer
)
from .notifications import (send_status_update, send_pdf_agreement, trigger_voice_call, 
                            send_emi_reminder)


User = get_user_model()

def send_otp(phone, otp):
    # Replace this with actual SMS gateway logic
    print(f"[DEV] OTP sent to {phone}: {otp}")


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
                    return Response({"error": "OTP expired"}, status=400)

                user, created = User.objects.get_or_create(phone=phone)
                user.is_phone_verified = True
                user.save()

                otp_record.delete()

                refresh = RefreshToken.for_user(user)
                return Response({
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                    "user_id": user.id
                }, status=200)

            except OTP.DoesNotExist:
                return Response({"error": "Invalid OTP"}, status=400)
        return Response(serializer.errors, status=400)


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
            return Response({'error': 'User not found'}, status=404)
        except UserProfile.DoesNotExist:
            return Response({'error': 'User profile not found'}, status=404)

        serializer = PublicUserProfileSerializer(user_profile)
        return Response(serializer.data)


class PublicUserFinancialView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            financial_details = FinancialDetails.objects.get(user=user)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)
        except FinancialDetails.DoesNotExist:
            return Response({'error': 'Financial detail not found'}, status=404)

        serializer = PublicUserFinancialSerializer(financial_details)
        return Response(serializer.data)


class LoanRequestCreateView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        serializer = LoanRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        
        repayment_mode = serializer.validated_data.get("repayment_mode")
        
        if repayment_mode=="ONETIME":
            loan = serializer.save(borrower=request.user,emi_start_date=None,emi_tenure_months=0)
            send_status_update(loan, "PENDING")
            return Response({"msg": "Loan request submitted."}, status=201)
        elif repayment_mode=="EMI":
            loan = serializer.save(borrower=request.user,onetime_repayment_date=None)
            send_status_update(loan, "PENDING")
            return Response({"msg": "Loan request submitted."}, status=201)

        return Response(serializer.errors, status=400)


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
            return Response({"error": "Loan not found or already processed."}, status=404)
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
            return Response({"error": "Loan not found or already processed."}, status=404)

        serializer = BorrowerLoanRequestSerializer(loan)
        return Response(serializer.data)


class LenderLoanOfferView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, pk):
        try:
            loan = Loan.objects.get(pk=pk, lender=request.user, status='PENDING')
        except Loan.DoesNotExist:
            return Response({"error": "Loan not found or already processed."}, status=404)

        serializer = LenderLoanOfferSerializer(loan, data=request.data, partial=True)

        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        
        # Checking Principal amount and requested amount
        principal = serializer.validated_data.get("principal_amount",loan.principal_amount)
        if principal > loan.requested_amount:
            return Response({"msg": "Principal amount cannot be higher than the requested amount."}, status=400)
        
        interest_rate = serializer.validated_data.get("interest_rate",loan.interest_rate)
        is_interest_rate_modified = True if interest_rate!=0 else False

        if is_interest_rate_modified or principal != loan.requested_amount:
            loan = serializer.save(
                    is_funded_by_lender=True,
                    funded_at=timezone.now(),
                    approved_at=timezone.now(),
                    is_interest_rate_modified=is_interest_rate_modified,
                    status='APPROVED'
                )
            send_status_update(loan, "APPROVED")
            return Response({"msg": "Loan offer modified and funded to platform."})
        else:
            loan = serializer.save(
                    is_funded_by_lender=True,
                    funded_at=timezone.now(),
                    approved_at=timezone.now(),
                    status='ONGOING',
                    accepted_at = timezone.now()
                )
            send_status_update(loan, "ONGOING")
            send_pdf_agreement(loan)
            return Response({"msg": "Loan accepted and disbursed to borrower."})


class BorrowerLoanDecisionView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, pk):
        decision = request.data.get("accept")  # True or False
        try:
            loan = Loan.objects.get(pk=pk, borrower=request.user, status='APPROVED')
        except Loan.DoesNotExist:
            return Response({"error": "Loan not found or already processed."}, status=404)

        if decision:
            loan.status = "ONGOING"
            loan.accepted_at = timezone.now()
            loan.save()
            send_status_update(loan, "ONGOING")
            send_pdf_agreement(loan)
            return Response({"msg": "Loan accepted and disbursed to borrower."})
        else:
            loan.status = "CANCELLED"
            loan.cancelled_by_borrower_at = timezone.now()
            loan.save()
            send_status_update(loan, "CANCELLED")
            return Response({"msg": "Loan declined by borrower and returned to lender."})


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

            last_tx = Transaction.objects.filter(loan=loan).order_by('-timestamp').first()
            if last_tx and (
                borrower_data[borrower.id]['last_transaction_date'] is None or
                last_tx.timestamp > borrower_data[borrower.id]['last_transaction_date']
            ):
                borrower_data[borrower.id]['last_transaction_date']=last_tx.timestamp
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

            last_tx = Transaction.objects.filter(loan=loan).order_by('-timestamp').first()
            if last_tx and (
                lender_data[lender.id]['last_transaction_date'] is None or 
                last_tx.timestamp > lender_data[lender.id]['last_transaction_date']
            ):
                lender_data[lender.id]['last_transaction_date'] = last_tx.timestamp
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
    
