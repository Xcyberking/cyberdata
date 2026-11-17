import re,math,os,requests
from concurrent.futures import ThreadPoolExecutor,as_completed
from storage import get_s3,bucket_name
CHUNK=int(os.getenv("TRANSFER_PART_SIZE_MB","64"))*1024*1024
WORKERS=max(1,min(4,int(os.getenv("TRANSFER_WORKERS","2"))))
def extract_id(url):
 m=re.search(r"/file/d/([A-Za-z0-9_-]+)",url) or re.search(r"[?&]id=([A-Za-z0-9_-]+)",url)
 if not m:raise ValueError("Google Drive link se file ID nahi mila")
 return m.group(1)
def fetch_range(url,start,end):
 with requests.get(url,headers={"Range":f"bytes={start}-{end}"},stream=True,timeout=(30,180)) as r:
  if r.status_code not in (200,206):raise RuntimeError(f"Drive HTTP {r.status_code}")
  b=r.content
  if len(b)!=end-start+1:raise RuntimeError("Drive byte-range response mismatch; link permission/range support check karein")
  return b
def start_transfer(jid,drive_url,key,jobs,lock):
 upload_id=None
 def upd(**kw):
  with lock:jobs[jid].update(kw)
 try:
  url=f"https://drive.google.com/uc?export=download&id={extract_id(drive_url)}"
  with requests.get(url,headers={"Range":"bytes=0-0"},stream=True,timeout=(30,90)) as p:
   if p.status_code not in (200,206):raise RuntimeError(f"Drive probe HTTP {p.status_code}")
   cr=p.headers.get("Content-Range","")
   if "/" not in cr:raise RuntimeError("Drive size/range metadata unavailable. File may need authenticated Drive API or confirmation.")
   total=int(cr.rsplit("/",1)[1])
  s3=get_s3()
  upload_id=s3.create_multipart_upload(Bucket=bucket_name(),Key=key,ContentType="application/json")["UploadId"]
  count=math.ceil(total/CHUNK)
  upd(status="running",total_bytes=total,uploaded_bytes=0,total_parts=count,message="Streaming Drive bytes to Hugging Face")
  parts=[];done=0
  def part(n):
   a=(n-1)*CHUNK;b=min(total-1,a+CHUNK-1);body=fetch_range(url,a,b)
   x=s3.upload_part(Bucket=bucket_name(),Key=key,UploadId=upload_id,PartNumber=n,Body=body)
   return {"PartNumber":n,"ETag":x["ETag"],"size":len(body)}
  with ThreadPoolExecutor(max_workers=WORKERS) as pool:
   fs=[pool.submit(part,n) for n in range(1,count+1)]
   for f in as_completed(fs):
    x=f.result();parts.append({"PartNumber":x["PartNumber"],"ETag":x["ETag"]});done+=x["size"]
    upd(uploaded_bytes=done,progress=round(done*100/total,2),message=f"Uploaded part {len(parts)}/{count}")
  s3.complete_multipart_upload(Bucket=bucket_name(),Key=key,UploadId=upload_id,MultipartUpload={"Parts":sorted(parts,key=lambda x:x["PartNumber"])})
  upd(status="completed",progress=100,uploaded_bytes=total,message="Transfer complete")
 except Exception as e:
  if upload_id:
   try:get_s3().abort_multipart_upload(Bucket=bucket_name(),Key=key,UploadId=upload_id)
   except Exception:pass
  upd(status="failed",message=str(e))
