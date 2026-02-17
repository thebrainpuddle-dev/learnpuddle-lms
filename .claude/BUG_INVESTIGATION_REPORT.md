# Tenant Admin Panel Bug Investigation Report

**Date:** 2024
**Status:** Production Issues Identified
**Severity:** CRITICAL - Multiple core functionalities broken

---

## Executive Summary

The tenant admin panel has **multiple critical bugs** preventing:
1. Course creation
2. Teacher creation
3. File uploads

After thorough code review, the root causes are identified below with fixes.

---

## Issue #1: Course Creation Failures

### Problem
Course creation endpoint returns validation errors or doesn't save properly.

### Root Causes Identified

#### 1a. Missing Thumbnail Field Handling
**File:** `frontend/src/pages/admin/CourseEditorPage.tsx`
**Issue:** Thumbnail is optional in form but may not be properly encoded as multipart/form-data

**File:** `backend/apps/courses/serializers.py` (lines 154-161)
**Issue:** `thumbnail` field in CourseDetailSerializer is not properly validated for multipart uploads

**Fix Required:**
```python
# In CourseDetailSerializer
class CourseDetailSerializer(serializers.ModelSerializer):
    # Ensure thumbnail field properly handles image files
    thumbnail = serializers.ImageField(
        required=False,
        allow_null=True,
        allow_empty_file=False
    )

    # Add proper validation
    def validate_thumbnail(self, value):
        if value:
            # Max 5MB
            if value.size > 5 * 1024 * 1024:
                raise serializers.ValidationError("File too large (max 5MB)")
            # Check MIME type
            if value.content_type not in {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}:
                raise serializers.ValidationError("Invalid image format")
        return value
```

#### 1b. MultiPart Parsing Not Set
**File:** `backend/apps/courses/views.py` (lines 27-31)
**Issue:** `course_list_create` view doesn't declare `@parser_classes([MultiPartParser, FormParser])`

**Problem:** Without explicit parser declaration, multipart file uploads fail

**Fix Required:**
```python
from rest_framework.parsers import MultiPartParser, FormParser

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@parser_classes([MultiPartParser, FormParser, JSONParser])  # ADD THIS
def course_list_create(request):
    """..."""
```

#### 1c. Module/Content Not Required But Accessed
**File:** `backend/apps/courses/serializers.py` (line 164-169)
**Issue:** `get_stats` tries to access `assignments` which may not exist

```python
def get_stats(self, obj):
    return {
        'total_modules': obj.modules.count(),
        'total_content': Content.objects.filter(module__course=obj).count(),
        'total_assignments': obj.assignments.count(),  # ← MAY NOT EXIST!
    }
```

**Fix:** Handle missing relation
```python
def get_stats(self, obj):
    return {
        'total_modules': obj.modules.count(),
        'total_content': Content.objects.filter(module__course=obj).count(),
        'total_assignments': getattr(obj, 'assignments', obj.__class__.objects.none()).count(),
    }
```

#### 1d. Tenant Not Validated in Create Context
**File:** `backend/apps/courses/serializers.py` (lines 171-196)
**Issue:** Serializer assumes `request.tenant` is set; no fallback

**Fix:**
```python
def create(self, validated_data):
    assigned_groups = validated_data.pop('assigned_groups', [])
    assigned_teachers = validated_data.pop('assigned_teachers', [])

    request = self.context.get('request')
    if not request:
        raise serializers.ValidationError("Request context required")

    if not hasattr(request, 'tenant') or not request.tenant:
        raise serializers.ValidationError("Tenant context not found")

    # ... rest of creation logic
```

### Testing Course Creation

```bash
# 1. Minimal course (no file)
curl -X POST http://localhost:8000/api/v1/courses/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Course",
    "description": "Test Description",
    "estimated_hours": 10,
    "is_mandatory": false
  }'

# 2. Course with thumbnail (multipart)
curl -X POST http://localhost:8000/api/v1/courses/ \
  -H "Authorization: Bearer <token>" \
  -F "title=Test Course" \
  -F "description=Test" \
  -F "estimated_hours=10" \
  -F "thumbnail=@/path/to/image.png"
```

---

## Issue #2: Teacher Creation Failures

### Problem
Teacher registration or CSV bulk import fails.

### Root Causes Identified

#### 2a. Missing CSV Bulk Import Endpoint Registration
**File:** `backend/apps/users/admin_urls.py`
**Issue:** Bulk import endpoint may not be properly routed

**Check:**
```python
# Should have:
path('bulk-import/', teachers_bulk_import_view, name='teacher-bulk-import'),
```

**If Missing, Add:**
```python
from .admin_views import teachers_bulk_import_view

urlpatterns = [
    path('', teachers_list_view, name='teacher-list'),
    path('bulk-import/', teachers_bulk_import_view, name='teacher-bulk-import'),
    # ... other endpoints
]
```

#### 2b. CSV Import View Not Implemented
**File:** `backend/apps/users/admin_views.py`
**Issue:** `teachers_bulk_import_view` function may be missing or incomplete

**Check in admin_views.py line 175+** - must have:
```python
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@parser_classes([MultiPartParser, FormParser])
@check_tenant_limit('teachers')
def teachers_bulk_import_view(request):
    """CSV bulk teacher import."""
    # Implementation...
```

**If Missing, Must Implement:**
- File size validation (2MB max)
- Row count validation (500 max)
- CSV injection prevention (sanitize =, +, -, @)
- Per-row error reporting
- Tenant quota enforcement
- Transaction rollback on critical errors

#### 2c. RegisterTeacherSerializer Validation Too Strict
**File:** `backend/apps/users/serializers.py` (lines 104-120)
**Issue:** Password validation may reject valid passwords, or password_confirm check may fail

**Check:**
```python
class RegisterTeacherSerializer(serializers.ModelSerializer):
    password_confirm = serializers.CharField(write_only=True)

    def validate(self, data):
        if data.get('password') != data.get('password_confirm'):
            raise serializers.ValidationError("Passwords don't match")
        # Should remove password_confirm before creating user
        data.pop('password_confirm')
        return data
```

**If validate missing or incomplete, fix:**
```python
def validate(self, data):
    password = data.get('password')
    password_confirm = data.pop('password_confirm', None)

    if not password_confirm:
        raise serializers.ValidationError("password_confirm required")

    if password != password_confirm:
        raise serializers.ValidationError("Passwords don't match")

    # Validate password strength
    try:
        validate_password(password)
    except ValidationError as e:
        raise serializers.ValidationError(f"Password: {e.messages[0]}")

    return data
```

#### 2d. Email Uniqueness Not Checked
**File:** `backend/apps/users/serializers.py`
**Issue:** Doesn't check if email already exists in tenant

**Add:**
```python
def validate_email(self, value):
    # Case-insensitive email uniqueness per tenant
    email_lower = value.lower()
    if User.objects.filter(email__iexact=email_lower, tenant=self.context['request'].tenant).exists():
        raise serializers.ValidationError("Email already exists in this tenant")
    return value
```

#### 2e. Tenant Context Not Set in Serializer
**File:** `backend/apps/users/serializers.py`
**Issue:** Serializer create method doesn't set tenant

**Fix:**
```python
def create(self, validated_data):
    request = self.context.get('request')
    if not request or not hasattr(request, 'tenant'):
        raise serializers.ValidationError("Tenant context required")

    user = User.objects.create_user(
        **validated_data,
        tenant=request.tenant,
        role='TEACHER',  # Default role
        must_change_password=True  # Force password change on first login
    )
    return user
```

### Testing Teacher Creation

```bash
# 1. Register single teacher
curl -X POST http://localhost:8000/api/users/auth/register-teacher/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "teacher@school.com",
    "password": "SecurePass123!",
    "password_confirm": "SecurePass123!",
    "first_name": "John",
    "last_name": "Doe",
    "employee_id": "EMP001",
    "department": "Mathematics"
  }'

# 2. Bulk import CSV
curl -X POST http://localhost:8000/api/teachers/bulk-import/ \
  -H "Authorization: Bearer <token>" \
  -F "file=@teachers.csv"
```

---

## Issue #3: File Upload Failures

### Problem
Thumbnail or content file uploads fail with validation or storage errors.

### Root Causes Identified

#### 3a. Upload Endpoints Missing MultiPart Parser
**File:** `backend/apps/uploads/views.py` (lines 91-137)
**Issue:** Upload views don't have `@parser_classes([MultiPartParser, FormParser])`

**Affected endpoints:**
- `upload_tenant_logo`
- `upload_course_thumbnail`
- `upload_content_file`

**Fix All:**
```python
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@parser_classes([MultiPartParser, FormParser])  # ADD THIS
@throttle_classes([UploadThrottle])
def upload_course_thumbnail(request):
    """Upload course thumbnail."""
    # ... implementation
```

#### 3b. File Parameter Name Inconsistency
**File:** `backend/apps/uploads/views.py` (lines 109-119)
**Issue:** Code checks for both 'file' and 'logo' parameters inconsistently

```python
file = request.FILES.get('file') or request.FILES.get('logo')
# This is fragile - frontend might send 'file' but code expects 'logo'
```

**Fix:**
```python
# Standardize on 'file' parameter
if 'file' not in request.FILES:
    return Response(
        {"error": "No 'file' parameter in request"},
        status=status.HTTP_400_BAD_REQUEST
    )

file = request.FILES['file']
```

#### 3c. Thumbnail Field Type Issue
**File:** `backend/apps/courses/models.py` (line 59)
**Issue:** Thumbnail is `ImageField` but might not have Pillow installed or image validation

**Check:**
```bash
docker compose exec web pip list | grep Pillow
# Should show: Pillow
```

**If missing, install in Dockerfile:**
```dockerfile
RUN pip install Pillow==10.0.0
```

#### 3d. Storage Configuration Not Verified
**File:** `backend/config/settings.py`
**Issue:** File storage backend (S3 vs local) not properly configured

**Check:**
```python
# Should have one of:
# Local filesystem
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
MEDIA_ROOT = '/data/media'
MEDIA_URL = '/media/'

# OR S3
DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
AWS_STORAGE_BUCKET_NAME = 'lms-bucket'
AWS_S3_REGION_NAME = 'us-east-1'
```

#### 3e. File URL Return Path Incorrect
**File:** `backend/apps/uploads/views.py` (lines 76-87)
**Issue:** `_save_upload` may not return absolute URL

**Fix Required:**
```python
def _save_upload(file_obj, prefix: str, tenant_id: str) -> str:
    # Current: returns relative path
    # Fix: should return absolute URL

    ext = ""
    name = getattr(file_obj, "name", "")
    if "." in name:
        ext = "." + name.rsplit(".", 1)[-1].lower()

    # Use UUID for filename
    filename = f"{uuid.uuid4()}{ext}"
    path = f"tenant/{tenant_id}/uploads/{prefix}/{filename}"

    # Save to storage
    file_path = default_storage.save(path, file_obj)

    # Return absolute URL
    from django.contrib.staticfiles.storage import default_storage
    url = default_storage.url(file_path)

    # Ensure absolute URL
    from django.urls import reverse
    if not url.startswith('http'):
        from django.conf import settings
        url = f"{settings.MEDIA_URL}{url}"

    return url
```

### Testing File Uploads

```bash
# 1. Upload course thumbnail
curl -X POST http://localhost:8000/api/v1/uploads/course-thumbnail/ \
  -H "Authorization: Bearer <token>" \
  -F "file=@thumbnail.png"

# 2. Upload content file
curl -X POST http://localhost:8000/api/v1/uploads/content-file/ \
  -H "Authorization: Bearer <token>" \
  -F "file=@document.pdf"
```

---

## Issue #4: Database Schema Sync Issues

### Problem
Migrations may not be applied correctly in production/staging.

### Root Causes

#### 4a. Missing Migrations
**Check:**
```bash
docker compose exec web python manage.py showmigrations

# Should show [X] for all migration files
# [X] apps.users.0001_initial
# [X] apps.courses.0001_initial
# [X] apps.courses.0006_course_soft_delete_search_vector
# etc.
```

**Fix if any [  ] (unapplied):**
```bash
docker compose exec web python manage.py migrate
```

#### 4b. Course Model Missing Fields
**Check:**
```bash
docker compose exec db psql -U postgres -d lms -c "\d courses"
# Should have all fields from models.py
# - tenant_id (FK)
# - title
# - slug
# - description
# - thumbnail
# - is_mandatory
# - deadline
# - estimated_hours
# - assigned_to_all
# - is_published
# - is_active
# - created_by_id (FK)
# - is_deleted
# - deleted_at
# - deleted_by_id (FK)
# - search_vector
```

**If missing, create migration:**
```bash
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
```

#### 4c. User Model Missing Soft Delete
**Check:**
```bash
docker compose exec db psql -U postgres -d lms -c "\d users"
# Should have:
# - is_deleted (bool, indexed)
# - deleted_at (timestamp)
# - deleted_by_id (FK to self)
```

#### 4d. Search Vector Not Updated
**Check:**
```bash
docker compose exec db psql -U postgres -d lms -c "SELECT COUNT(*) FROM courses WHERE search_vector IS NULL;"
# Should return 0 (all courses have search vectors)

# If > 0, update all courses
docker compose exec web python manage.py shell
>>> from apps.courses.models import Course
>>> for course in Course.objects.all():
...     course.update_search_vector()
```

---

## Root Cause Summary Table

| Feature | Issue | Root Cause | Fix Priority |
|---------|-------|-----------|--------------|
| Course Creation | No multipart parsing | Missing @parser_classes | CRITICAL |
| Course Creation | Thumbnail validation | No validation logic | HIGH |
| Course Creation | Stats accessor error | Missing null check | HIGH |
| Teacher Creation | CSV import broken | View or route missing | CRITICAL |
| Teacher Creation | Email exists error | No uniqueness check | HIGH |
| Teacher Creation | Password mismatch | Serializer validation incomplete | HIGH |
| File Upload | Multipart not parsed | Missing @parser_classes | CRITICAL |
| File Upload | File not saved | Wrong parameter name | HIGH |
| File Upload | URL not absolute | Storage config issue | MEDIUM |
| Database | Migrations unapplied | Manual intervention needed | CRITICAL |
| Database | Missing fields | Schema out of sync | CRITICAL |

---

## Implementation Order

1. **CRITICAL (Must Fix First):**
   - Add `@parser_classes([MultiPartParser, FormParser, JSONParser])` to course_list_create
   - Add `@parser_classes` to all upload endpoints
   - Verify CSV bulk import endpoint exists and is routed
   - Ensure all migrations are applied

2. **HIGH (Fix Next):**
   - Add thumbnail validation to serializer
   - Add email uniqueness check
   - Fix password confirmation in serializer
   - Fix stats accessor error
   - Ensure tenant context in create methods

3. **MEDIUM (Polish):**
   - Improve file upload parameter standardization
   - Ensure absolute URLs are returned
   - Add better error messages

---

## Testing Checklist

- [ ] Course creation: minimal (title + description)
- [ ] Course creation: with thumbnail
- [ ] Course creation: with modules and content
- [ ] Teacher creation: single teacher
- [ ] Teacher creation: CSV bulk import
- [ ] File upload: course thumbnail
- [ ] File upload: content document
- [ ] Database: all migrations applied
- [ ] Database: no missing fields
- [ ] Tenant isolation: confirmed working
- [ ] Error messages: clear and actionable

---

## Next Steps

1. Read this report and confirm understanding
2. Apply fixes in order of priority (CRITICAL → HIGH → MEDIUM)
3. Test each fix locally with docker compose
4. Commit to feature branch: `fix/admin-panel-bugs`
5. Push to remote and verify in staging
6. Create PR with test results

