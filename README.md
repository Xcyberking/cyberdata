# CyberData

Google Drive JSON to Hugging Face Storage Bucket transfer service for Railway.

## Features
- Flask dashboard and health endpoint.
- Streams Google Drive bytes by HTTP ranges and uploads multipart to an existing Hugging Face Storage Bucket.
- Progress reporting and configurable part size/concurrency.
- Data metadata and 15-minute presigned download URL endpoints.

## Setup
1. Create an existing Hugging Face Storage Bucket.
2. Create a token with bucket write access and generate S3 credentials (access key starts with HFAK).
3. Set Railway variables using .env.example. Never commit real credentials.
4. Deploy on Railway using the included Procfile and railway.json.
5. Set bucket visibility in Hugging Face. Only make it public if you own the data or have permission and it contains no private/sensitive information.

S3 endpoint: https://<HF_NAMESPACE>.s3.hf.co ; region us-east-1; path-style addressing.

## API
- GET /health
- POST /api/transfer/start with JSON body {"drive_url":"...","object_key":"data.json"}
- GET /api/transfer/<job_id>
- GET /api/data?key=data.json
- GET /api/data/download-url?key=data.json

## Important limitations
- This version transfers the original JSON file byte-for-byte; it does not parse/index records inside a giant JSON document.
- Drive link mode requires a downloadable link and HTTP byte-range support. Google Drive confirmation/quota/authentication screens may require an authenticated Drive API integration.
- Job state is in memory. A Railway restart clears job status and interrupts an active transfer; durable multipart checkpoint/resume is not implemented. Do not treat this build as crash-resumable.
- Check Hugging Face storage limits/pricing and Railway outbound bandwidth/runtime costs before attempting 446 GB. Public storage is not guaranteed to be free.
