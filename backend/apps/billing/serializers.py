from rest_framework import serializers

from .models import SubscriptionPlan, TenantSubscription, PaymentHistory


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'name', 'plan_code', 'description',
            'price_monthly_cents', 'price_yearly_cents', 'currency',
            'is_recommended', 'is_custom_pricing', 'features_json', 'sort_order',
        ]


class TenantSubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)

    class Meta:
        model = TenantSubscription
        fields = [
            'id', 'plan', 'status', 'billing_interval',
            'stripe_customer_id', 'current_period_start', 'current_period_end',
            'cancel_at_period_end', 'canceled_at',
            'trial_start', 'trial_end', 'created_at', 'updated_at',
        ]


class PaymentHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentHistory
        fields = [
            'id', 'amount_cents', 'currency', 'status', 'description',
            'invoice_url', 'invoice_pdf_url',
            'period_start', 'period_end', 'failure_reason', 'created_at',
        ]


class CheckoutSessionSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField()
    interval = serializers.ChoiceField(choices=['month', 'year'])
    success_url = serializers.URLField()
    cancel_url = serializers.URLField()


class PlanChangePreviewSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField()
    interval = serializers.ChoiceField(choices=['month', 'year'])
