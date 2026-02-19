# Digital Ocean Spaces - Storage Structure

This document describes the storage path structure used by LearnPuddle LMS for media files in Digital Ocean Spaces.

## Bucket Name
- **Bucket**: `learnpuddle-media`
- **Origin Endpoint**: `https://sgp1.digitaloceanspaces.com/learnpuddle-media/`
- **CDN Endpoint**: `https://learnpuddle-media.sgp1.cdn.digitaloceanspaces.com/`

---

## Folder Structure

### 1. Course Thumbnails
**Path**: `course_thumbnails/tenant/{tenant_id}/{uuid}.{ext}`

Example: `course_thumbnails/tenant/88e163b6-a90b-4bdc-8335-847385a6ac37/c60fc89d8d0f4993820861acc0e633d3.png`

- Used for course cover images uploaded via admin portal
- Supported formats: jpg, jpeg, png, webp, gif

### 2. Learning Path Thumbnails
**Path**: `learning_path_thumbnails/tenant/{tenant_id}/{uuid}.{ext}`

- Used for learning path cover images
- Same format as course thumbnails

### 3. Profile Pictures
**Path**: `profile_pictures/tenant/{tenant_id_or_global}/{user_id}.{ext}`

Example: `profile_pictures/tenant/88e163b6-a90b-4bdc-8335-847385a6ac37/f98de6c4-3e15-4521-99b0-4c58f8dd9716.png`

- User profile images
- Uses `global` for super admins without a tenant

### 4. Tenant Logos
**Path**: `tenant_logos/tenant/{tenant_id}/{uuid}.{ext}`

Example: `tenant_logos/tenant/88e163b6-a90b-4bdc-8335-847385a6ac37/a1b2c3d4e5f6.png`

- School/tenant branding logos

### 5. Media Library
**Path**: `media_library/tenant/{tenant_id}/{type}/{uuid}.{ext}`

Examples:
- `media_library/tenant/88e163b6-a90b-4bdc-8335-847385a6ac37/videos/abc123.mp4`
- `media_library/tenant/88e163b6-a90b-4bdc-8335-847385a6ac37/documents/def456.pdf`

- Assets uploaded via Media Library (admin section)
- Subfolders: `videos/`, `documents/`

### 6. Course Content - Videos (Processed)
**Path**: `course_content/tenant/{tenant_id}/videos/{content_id}/`

Structure under each content_id:
```
course_content/tenant/{tenant_id}/videos/{content_id}/
├── source.mp4          # Original uploaded video
├── hls/
│   ├── master.m3u8     # HLS playlist
│   └── seg_*.ts        # HLS segments
├── thumb.jpg           # Auto-generated thumbnail
└── captions.vtt        # Auto-generated subtitles (if available)
```

Example:
```
course_content/tenant/88e163b6-a90b-4bdc-8335-847385a6ac37/videos/b5ec945f-fa3e-4d7b-beca-0255af3337bb/
├── source.mp4
├── hls/
│   ├── master.m3u8
│   ├── seg_00000.ts
│   ├── seg_00001.ts
│   └── ...
├── thumb.jpg
└── captions.vtt
```

### 7. Course Content - Documents
**Path**: `course_content/tenant/{tenant_id}/documents/{content_id}/{uuid}.{ext}`

Example: `course_content/tenant/88e163b6-a90b-4bdc-8335-847385a6ac37/documents/cfa131a6/abc123.pdf`

- PDFs, docs, presentations attached to course content

### 8. Previews (Future Use)
**Path**: `previews/tenant/{tenant_id}/{type}/{uuid}.{ext}`

- Reserved for thumbnail previews of media assets
- Subfolders: `videos/`, `documents/`

---

## DO Spaces Configuration Required

### CORS Configuration
Add this CORS configuration to your DO Spaces bucket via the DigitalOcean control panel:

**Settings → CORS Configurations → Add:**

| Field | Value |
|-------|-------|
| Origin | `https://*.learnpuddle.com` |
| Allowed Methods | GET, HEAD, OPTIONS |
| Allowed Headers | * |
| Max Age | 3600 |

For development, add another rule:
| Field | Value |
|-------|-------|
| Origin | `http://localhost:3000` |
| Allowed Methods | GET, HEAD, OPTIONS |
| Allowed Headers | * |
| Max Age | 3600 |

### Access Control
- Files are stored as **PRIVATE** by default
- All URLs are **pre-signed** with temporary credentials (4-24 hour expiry)
- No public access required

---

## Migration Notes

### Old Paths (Pre-refactor)
If you have files at these legacy paths, they may need migration:

| Old Path | New Path |
|----------|----------|
| `media_assets/YYYY/MM/{filename}` | `media_library/tenant/{tenant_id}/documents/{uuid}.ext` |
| `tenant/{tenant_id}/uploads/content-file/{uuid}.ext` | `course_content/tenant/{tenant_id}/documents/{content_id}/{uuid}.ext` |
| `tenant/{tenant_id}/videos/{content_id}/...` | `course_content/tenant/{tenant_id}/videos/{content_id}/...` |
| `course_thumbnails/{filename}` | `course_thumbnails/tenant/{tenant_id}/{uuid}.ext` |

### Cleanup Script (Manual)
To clean up legacy paths after migration, you can safely delete:
```
tenant/{tenant_id}/uploads/          # Old content-file uploads
media_assets/YYYY/MM/                # Old media library format (without tenant)
```

**Always backup before deleting!**

---

## URL Signing

All file URLs returned by the API are pre-signed S3 URLs:
- Course thumbnails: 24-hour expiry
- Media library files: 1-hour expiry
- Video HLS streams: 4-hour expiry
- Documents: 4-hour expiry

Example signed URL:
```
https://sgp1.digitaloceanspaces.com/learnpuddle-media/course_content/tenant/xxx/videos/yyy/hls/master.m3u8?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=...&X-Amz-Date=...&X-Amz-Expires=14400&X-Amz-SignedHeaders=host&X-Amz-Signature=...
```

---

## Troubleshooting

### NoSuchKey Error
- File doesn't exist at the specified path
- Check if file was uploaded with old path format
- Verify tenant_id and content_id are correct

### 403 Forbidden on OPTIONS
- CORS not configured on DO Spaces
- Follow CORS Configuration section above

### 403 Forbidden on GET (without signed URL)
- Trying to access private file without signing
- All URLs must go through API which generates signed URLs

### Document "This content is blocked"
- Browser blocking iframe embed (X-Frame-Options)
- Solution: Use "Open in new tab" instead of iframe embedding
