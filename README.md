# CyberData

Railway-hosted Google Drive JSON → Hugging Face Storage Bucket transfer service.

## Features
- Mobile dashboard, health endpoint, and admin-key protected transfer controls.
- HTTP byte-range Drive downloads and multipart S3-compatible uploads.
- SQLite transfer metadata and per-part ETag checkpoints.
- Startup recovery: queued/running jobs reconcile saved parts with Hugging Face and upload missing chunks.
- Status/progress, object metadata, and 15-minute presigned download URL APIs.

## Deploy
1. Create a Hugging Face Storage Bucket and generate its S3 access/secret credentials.
2. Attach a Railway persistent Volume mounted at **/data**. Without this, restart-safe SQLite checkpoints are not durable.
3. Set Railway variables from .env.example. Never commit real credentials.
4. Deploy this repo. Keep one web process/replica to avoid duplicate job orchestrators.
5. Configure bucket visibility separately in Hugging Face.

## Variables
HF_NAMESPACE, HF_BUCKET_NAME, HF_S3_ACCESS_KEY, HF_S3_SECRET_KEY, ADMIN_API_KEY, APP_SECRET, DATABASE_PATH=/data/cyberdata.sqlite, TRANSFER_PART_SIZE_MB=64, TRANSFER_WORKERS=2.

## API
- GET /health
- POST /api/transfer/start (JSON {"drive_url":"...","object_key":"data.json"}, header X-Admin-Key)
- GET /api/transfer/<job_id>
- POST /api/transfer/<job_id>/resume (header X-Admin-Key)
- GET /api/data?key=data.json
- GET /api/data/download-url?key=data.json

## Limits and safety
- This transfers the original JSON bytes; it does not parse/index records inside the huge JSON document.
- Google Drive link mode requires HTTP 206 byte-range support and a stable downloadable file. Drive confirmation pages, restricted access, quota limits, or anti-abuse responses may require authenticated Drive API integration. The worker refuses full-file responses to avoid buffering hundreds of GB.
- Resuming requires the original Drive file to remain accessible and unchanged.
- Check Hugging Face bucket storage limits/pricing, Railway outbound bandwidth/runtime charges, and Drive quotas before a 446 GB transfer. Public storage is not guaranteed free. Publish only data you own or have permission to share and that contains no private/sensitive information.
- Record-level search requires a separate streaming JSON parser/index with a known JSON schema and a database.
