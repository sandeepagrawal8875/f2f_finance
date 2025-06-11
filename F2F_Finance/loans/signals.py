from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, UserProfile, FinancialDetails

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def create_financial_details(sender, instance, created, **kwargs):
    if created:
        FinancialDetails.objects.create(user=instance)