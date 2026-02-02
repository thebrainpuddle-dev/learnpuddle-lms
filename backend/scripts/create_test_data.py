#!/usr/bin/env python
"""
Script to create test data for the LMS platform.
Run from the backend directory: python scripts/create_test_data.py
"""

import os
import sys
import django

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.courses.models import TeacherGroup, Course, Module, Content
from datetime import date, timedelta


def create_test_data():
    print("Creating test data...")
    
    # Create tenant
    tenant, created = Tenant.objects.get_or_create(
        slug="abc-school",
        defaults={
            "name": "ABC International School",
            "subdomain": "abc",
            "email": "admin@abcschool.com"
        }
    )
    if created:
        print(f"✅ Created tenant: {tenant.name}")
    else:
        print(f"ℹ️  Tenant already exists: {tenant.name}")
    
    # Create school admin user
    admin, created = User.objects.get_or_create(
        email="schooladmin@abcschool.com",
        defaults={
            "first_name": "School",
            "last_name": "Admin",
            "tenant": tenant,
            "role": "SCHOOL_ADMIN",
            "is_staff": True,
        }
    )
    if created:
        admin.set_password("admin123")
        admin.save()
        print(f"✅ Created admin: {admin.email}")
    else:
        print(f"ℹ️  Admin already exists: {admin.email}")
    
    # Create teacher users
    teachers_data = [
        {"email": "john.doe@abcschool.com", "first_name": "John", "last_name": "Doe", 
         "subjects": ["Mathematics", "Physics"], "grades": ["Grade 9", "Grade 10"]},
        {"email": "jane.smith@abcschool.com", "first_name": "Jane", "last_name": "Smith",
         "subjects": ["English", "Literature"], "grades": ["Grade 9", "Grade 11"]},
        {"email": "bob.wilson@abcschool.com", "first_name": "Bob", "last_name": "Wilson",
         "subjects": ["Chemistry", "Biology"], "grades": ["Grade 10", "Grade 12"]},
    ]
    
    teachers = []
    for data in teachers_data:
        teacher, created = User.objects.get_or_create(
            email=data["email"],
            defaults={
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "tenant": tenant,
                "role": "TEACHER",
                "subjects": data["subjects"],
                "grades": data["grades"],
            }
        )
        if created:
            teacher.set_password("teacher123")
            teacher.save()
            print(f"✅ Created teacher: {teacher.email}")
        else:
            print(f"ℹ️  Teacher already exists: {teacher.email}")
        teachers.append(teacher)
    
    # Create teacher groups
    groups_data = [
        {"name": "Math Teachers", "group_type": "SUBJECT"},
        {"name": "Science Teachers", "group_type": "SUBJECT"},
        {"name": "Grade 9 Teachers", "group_type": "GRADE"},
    ]
    
    groups = []
    for data in groups_data:
        group, created = TeacherGroup.objects.get_or_create(
            tenant=tenant,
            name=data["name"],
            defaults={"group_type": data["group_type"]}
        )
        if created:
            print(f"✅ Created group: {group.name}")
        else:
            print(f"ℹ️  Group already exists: {group.name}")
        groups.append(group)
    
    # Add teachers to groups
    groups[0].members.add(teachers[0])  # John to Math Teachers
    groups[1].members.add(teachers[2])  # Bob to Science Teachers
    groups[2].members.add(teachers[0], teachers[1])  # John and Jane to Grade 9
    
    # Create courses
    courses_data = [
        {
            "title": "Classroom Management 101",
            "description": "Learn effective classroom management techniques for modern educators.",
            "is_mandatory": True,
            "deadline": date.today() + timedelta(days=30),
            "estimated_hours": 5,
        },
        {
            "title": "Digital Tools for Education",
            "description": "Master the essential digital tools for remote and hybrid learning.",
            "is_mandatory": False,
            "deadline": date.today() + timedelta(days=60),
            "estimated_hours": 8,
        },
        {
            "title": "Student Assessment Strategies",
            "description": "Explore various methods for assessing student learning effectively.",
            "is_mandatory": True,
            "deadline": date.today() + timedelta(days=45),
            "estimated_hours": 6,
        },
    ]
    
    for data in courses_data:
        course, created = Course.objects.get_or_create(
            tenant=tenant,
            title=data["title"],
            defaults={
                "description": data["description"],
                "is_mandatory": data["is_mandatory"],
                "deadline": data["deadline"],
                "estimated_hours": data["estimated_hours"],
                "created_by": admin,
                "is_published": True,
                "assigned_to_all": True,
            }
        )
        if created:
            print(f"✅ Created course: {course.title}")
            
            # Create modules for the course
            for i, module_title in enumerate(["Introduction", "Core Concepts", "Practical Applications"], 1):
                module = Module.objects.create(
                    course=course,
                    title=f"{module_title}",
                    description=f"{module_title} for {course.title}",
                    order=i
                )
                
                # Create content for each module
                Content.objects.create(
                    module=module,
                    title=f"{module_title} - Video",
                    content_type="VIDEO",
                    order=1,
                    duration=600,  # 10 minutes
                )
                Content.objects.create(
                    module=module,
                    title=f"{module_title} - Reading Material",
                    content_type="DOCUMENT",
                    order=2,
                )
        else:
            print(f"ℹ️  Course already exists: {course.title}")
    
    print("\n" + "=" * 50)
    print("✅ Test data created successfully!")
    print("=" * 50)
    print("\n📝 Login Credentials:")
    print("-" * 50)
    print(f"Platform Admin: admin@lms.com / admin123")
    print(f"School Admin:   schooladmin@abcschool.com / admin123")
    print(f"Teacher 1:      john.doe@abcschool.com / teacher123")
    print(f"Teacher 2:      jane.smith@abcschool.com / teacher123")
    print(f"Teacher 3:      bob.wilson@abcschool.com / teacher123")
    print("-" * 50)


if __name__ == "__main__":
    create_test_data()
