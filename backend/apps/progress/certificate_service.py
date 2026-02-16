# apps/progress/certificate_service.py
"""
Certificate generation service using ReportLab.

Generates PDF certificates for teachers who have completed courses.
Includes tenant branding (logo, colors) and completion details.
"""

import io
from datetime import datetime
from typing import Optional

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.enums import TA_CENTER


def hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color to RGB tuple (0-1 range for ReportLab)."""
    hex_color = hex_color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return (r / 255.0, g / 255.0, b / 255.0)


def generate_certificate_pdf(
    teacher_name: str,
    course_title: str,
    completion_date: datetime,
    tenant_name: str,
    tenant_logo_path: Optional[str] = None,
    primary_color: str = "#1F4788",
    certificate_id: Optional[str] = None,
) -> io.BytesIO:
    """
    Generate a PDF certificate for course completion.
    
    Args:
        teacher_name: Full name of the teacher
        course_title: Title of the completed course
        completion_date: Date when course was completed
        tenant_name: Name of the school/institution
        tenant_logo_path: Optional path to tenant logo image
        primary_color: Hex color for branding accents
        certificate_id: Optional unique certificate identifier
    
    Returns:
        BytesIO buffer containing the PDF data
    """
    buffer = io.BytesIO()
    
    # Use landscape A4 for certificate
    page_width, page_height = landscape(A4)
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=50,
        leftMargin=50,
        topMargin=40,
        bottomMargin=40,
    )
    
    # Convert primary color
    rgb_primary = hex_to_rgb(primary_color)
    primary_reportlab = colors.Color(*rgb_primary)
    
    # Create styles
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CertificateTitle',
        parent=styles['Heading1'],
        fontSize=36,
        textColor=primary_reportlab,
        alignment=TA_CENTER,
        spaceAfter=20,
        fontName='Helvetica-Bold',
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=14,
        textColor=colors.gray,
        alignment=TA_CENTER,
        spaceAfter=30,
    )
    
    presenter_style = ParagraphStyle(
        'Presenter',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.gray,
        alignment=TA_CENTER,
        spaceAfter=10,
    )
    
    name_style = ParagraphStyle(
        'RecipientName',
        parent=styles['Heading1'],
        fontSize=32,
        textColor=colors.black,
        alignment=TA_CENTER,
        spaceAfter=20,
        fontName='Helvetica-Bold',
    )
    
    course_style = ParagraphStyle(
        'CourseName',
        parent=styles['Normal'],
        fontSize=18,
        textColor=primary_reportlab,
        alignment=TA_CENTER,
        spaceAfter=30,
        fontName='Helvetica-Bold',
    )
    
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.black,
        alignment=TA_CENTER,
        spaceAfter=10,
    )
    
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.gray,
        alignment=TA_CENTER,
    )
    
    # Build document content
    elements = []
    
    # Add decorative border
    elements.append(Spacer(1, 20))
    
    # Tenant logo (if available)
    if tenant_logo_path:
        try:
            logo = Image(tenant_logo_path, width=1.5*inch, height=1.5*inch)
            logo.hAlign = 'CENTER'
            elements.append(logo)
            elements.append(Spacer(1, 20))
        except Exception:
            pass  # Skip logo if there's an error loading it
    
    # Certificate title
    elements.append(Paragraph("Certificate of Completion", title_style))
    
    # Subtitle
    elements.append(Paragraph("This is to certify that", subtitle_style))
    
    # Recipient name
    elements.append(Paragraph(teacher_name, name_style))
    
    # Course completion text
    elements.append(Paragraph("has successfully completed the course", body_style))
    
    # Course title
    elements.append(Paragraph(f'"{course_title}"', course_style))
    
    # Completion date
    formatted_date = completion_date.strftime("%B %d, %Y")
    elements.append(Paragraph(f"Completed on {formatted_date}", body_style))
    
    elements.append(Spacer(1, 40))
    
    # Presented by
    elements.append(Paragraph(f"Presented by {tenant_name}", presenter_style))
    
    # Footer with certificate ID
    elements.append(Spacer(1, 30))
    if certificate_id:
        elements.append(Paragraph(f"Certificate ID: {certificate_id}", footer_style))
    
    # Platform branding
    platform_name = getattr(settings, 'PLATFORM_NAME', 'Brain LMS')
    elements.append(Paragraph(f"Powered by {platform_name}", footer_style))
    
    # Build PDF
    doc.build(elements)
    
    buffer.seek(0)
    return buffer


def get_certificate_filename(teacher_name: str, course_title: str) -> str:
    """Generate a clean filename for the certificate."""
    # Clean names for filename
    clean_teacher = "".join(c if c.isalnum() or c in (' ', '-', '_') else '' for c in teacher_name)
    clean_course = "".join(c if c.isalnum() or c in (' ', '-', '_') else '' for c in course_title)
    
    clean_teacher = clean_teacher.replace(' ', '_')[:30]
    clean_course = clean_course.replace(' ', '_')[:30]
    
    return f"certificate_{clean_teacher}_{clean_course}.pdf"
