from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0017_staff_certifications"),
    ]

    operations = [
        # 1. Update StaffCertification.certification_type choices with new types
        migrations.AlterField(
            model_name="staffcertification",
            name="certification_type",
            field=models.CharField(
                choices=[
                    ("IB_CAT1", "IB Category 1 Workshop"),
                    ("IB_CAT2", "IB Category 2 Workshop"),
                    ("IB_CAT3", "IB Category 3 Workshop"),
                    ("IB_LEADER", "IB Leadership Workshop"),
                    ("FIRST_AID", "First Aid Certification"),
                    ("POCSO", "POCSO Awareness Training"),
                    ("POSH", "POSH (Sexual Harassment Prevention)"),
                    ("FIRE_SAFETY", "Fire Safety Training"),
                    ("CHILD_SAFEGUARDING", "Child Safeguarding"),
                    ("CWSN", "Children with Special Needs Training"),
                    ("CPR", "CPR Certification"),
                    ("MENTAL_HEALTH", "Mental Health First Aid"),
                    ("ANTI_BULLYING", "Anti-Bullying Training"),
                    ("BACKGROUND_CHECK", "Background / Police Verification"),
                    ("TEACHING_LICENSE", "Teaching License"),
                    ("SUBJECT_CERT", "Subject Specialization Certificate"),
                    ("DIGITAL_LITERACY", "Digital Literacy / EdTech Training"),
                    ("GOOGLE_CERT", "Google Certified Educator"),
                    ("NEP_TRAINING", "NEP 2020 Training"),
                    ("OTHER", "Other"),
                ],
                max_length=30,
            ),
        ),
        # 2. Update ComplianceItem.category choices to add IB Programme Requirements
        migrations.AlterField(
            model_name="complianceitem",
            name="category",
            field=models.CharField(
                choices=[
                    ("SAFETY", "Safety & Infrastructure"),
                    ("BOARD", "Board & Government"),
                    ("NEP", "NEP 2020 Alignment"),
                    ("FINANCIAL", "Financial & Fee Regulation"),
                    ("DATA", "Data & Privacy"),
                    ("IB", "IB Programme Requirements"),
                    ("OTHER", "Other"),
                ],
                max_length=20,
            ),
        ),
        # 3. Add unique_together on ComplianceItem (tenant, name, category)
        migrations.AlterUniqueTogether(
            name="complianceitem",
            unique_together={("tenant", "name", "category")},
        ),
    ]
