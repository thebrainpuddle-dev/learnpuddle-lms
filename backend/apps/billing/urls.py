from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("plans/", views.plan_list, name="plan_list"),
    path("subscription/", views.subscription_detail, name="subscription_detail"),
    path("checkout/", views.create_checkout, name="create_checkout"),
    path("portal/", views.create_portal, name="create_portal"),
    path("payments/", views.payment_history, name="payment_history"),
    path("preview-change/", views.preview_plan_change, name="preview_plan_change"),
]
