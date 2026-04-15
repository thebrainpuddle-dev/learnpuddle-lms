# apps/tenants/accreditation_urls.py

from django.urls import path
from . import accreditation_views

urlpatterns = [
    path('accreditations/', accreditation_views.accreditation_list, name='accreditation_list'),
    path('accreditations/create/', accreditation_views.accreditation_create, name='accreditation_create'),
    path('accreditations/<uuid:pk>/update/', accreditation_views.accreditation_update, name='accreditation_update'),
    path('accreditations/<uuid:pk>/delete/', accreditation_views.accreditation_delete, name='accreditation_delete'),
    path('accreditations/<uuid:accreditation_pk>/milestones/', accreditation_views.milestone_list_create, name='milestone_list_create'),
    path('accreditations/<uuid:accreditation_pk>/milestones/<uuid:pk>/', accreditation_views.milestone_update_delete, name='milestone_update_delete'),
    path('rankings/', accreditation_views.ranking_list, name='ranking_list'),
    path('rankings/create/', accreditation_views.ranking_create, name='ranking_create'),
    path('rankings/<uuid:pk>/update/', accreditation_views.ranking_update, name='ranking_update'),
    path('rankings/<uuid:pk>/delete/', accreditation_views.ranking_delete, name='ranking_delete'),
    # Compliance
    path('compliance/', accreditation_views.compliance_list, name='compliance_list'),
    path('compliance/create/', accreditation_views.compliance_create, name='compliance_create'),
    path('compliance/<uuid:pk>/update/', accreditation_views.compliance_update, name='compliance_update'),
    path('compliance/<uuid:pk>/delete/', accreditation_views.compliance_delete, name='compliance_delete'),

    # Staff Certifications / PD Tracker
    path('staff-certifications/', accreditation_views.staff_certifications_list, name='staff_certifications_list'),
    path('staff-certifications/create/', accreditation_views.staff_certification_create, name='staff_certification_create'),
    path('staff-certifications/bulk-create/', accreditation_views.staff_certification_bulk_create, name='staff_certification_bulk_create'),
    path('staff-certifications/<uuid:pk>/update/', accreditation_views.staff_certification_update, name='staff_certification_update'),
    path('staff-certifications/<uuid:pk>/delete/', accreditation_views.staff_certification_delete, name='staff_certification_delete'),
]
