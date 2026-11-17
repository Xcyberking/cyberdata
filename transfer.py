import re,math,os,requests,threading
from concurrent.futures import ThreadPoolExecutor,as_completed
from storage import get_s3,bucket_name
import db
def env_int(name,default,minimum,maximum=None):
 try:value=int(os.getenv(name,str(default)))
 except (TypeError,ValueError):value=default
 value=max(minimum,value)
 return min(maximum,value) if maximum is not None else value
CHUNK=env_int("TRANSFER_PART_SIZE_MB",64,5,512)*1024*1024
WORKERS=env_int("TRANSFER_WORKERS",2,1,4)
active=set();active_lock=threading.Lock()
def extract_id(url):
 m=re.search(r"/file/d/([A-Za-z0-9_-]+)",url) or re.search(r"[?&]id=([A-Za-z0-9_-]+)",url)
 if not m:raise ValueError("Google Drive URL me file ID nahi mila")
 return m.group(1)
def drive_url(url):return "https://drive.google.com/uc?export=download&id="+extract_id(url)
def probe(url):
 with requests.get(url,headers={"Range":"bytes=0-0"},stream=True,timeout=(30,90),allow_redirects=True) as r:
  if r.status_code!=206:raise RuntimeError("Google Drive byte-range support unavailable (HTTP %s). Refusing whole-file buffering."%r.status_code)
  cr=r.headers.get("Content-Range","")
  if not cr.startswith("bytes 0-0/"):raise RuntimeError("Drive Content-Range invalid; check sharing, confirmation page, or Drive API authentication.")
  return int(cr.rsplit("/",1)[1])
def get_range(url,start,end):
 with requests.get(url,headers={"Range":f"bytes={start}-{end}"},stream=True,timeout=(30,300),allow_redirects=True) as r:
  if r.status_code!=206 or not r.headers.get("Content-Range","").startswith(f"bytes {start}-{end}/"):
   raise RuntimeError("Drive did not return the requested byte range")
  chunks=[];size=0
  for chunk in r.iter_content(1024*1024):
   if chunk:chunks.append(chunk);size+=len(chunk)
  if size!=end-start+1:raise RuntimeError("Incomplete Drive range: expected %d bytes, received %d"%(end-start+1,size))
  return b"".join(chunks)
def run_job(jid):
 with active_lock:
  if jid in active:return
  active.add(jid)
 try:
  j=db.get_job(jid)
  if not j:return
  url=drive_url(j["drive_url"]);total=probe(url);key=j["object_key"];s3=get_s3();upload_id=j.get("upload_id")
  if not upload_id:
   upload_id=s3.create_multipart_upload(Bucket=bucket_name(),Key=key,ContentType="application/json")["UploadId"]
   db.update(jid,upload_id=upload_id,total_bytes=total,total_parts=math.ceil(total/CHUNK),status="running")
  elif j.get("total_bytes") and int(j["total_bytes"])!=total:raise RuntimeError("Drive source size changed; start a new job")
  remote={};marker=0
  while True:
   page=s3.list_parts(Bucket=bucket_name(),Key=key,UploadId=upload_id,PartNumberMarker=marker)
   for p in page.get("Parts",[]):remote[p["PartNumber"]]=p
   if not page.get("IsTruncated"):break
   marker=page["NextPartNumberMarker"]
  db.delete_parts_not_in(jid,list(remote.keys()))
  saved={p["part_number"]:p for p in db.get_parts(jid)}
  for n,p in remote.items():
   if n not in saved or saved[n]["etag"]!=p["ETag"]:db.save_part(jid,n,p["ETag"],p["Size"])
  saved={p["part_number"]:p for p in db.get_parts(jid)}
  count=math.ceil(total/CHUNK);done=sum(p["size"] for p in saved.values())
  db.update(jid,status="running",total_bytes=total,total_parts=count,uploaded_bytes=done,progress=round(done*100/total,2),message="Resuming missing chunks")
  def part(n):
   a=(n-1)*CHUNK;b=min(total-1,a+CHUNK-1);body=get_range(url,a,b)
   x=s3.upload_part(Bucket=bucket_name(),Key=key,UploadId=upload_id,PartNumber=n,Body=body)
   db.save_part(jid,n,x["ETag"],len(body))
  missing=[n for n in range(1,count+1) if n not in saved]
  with ThreadPoolExecutor(max_workers=WORKERS) as pool:
   futures=[pool.submit(part,n) for n in missing]
   for f in as_completed(futures):
    f.result();parts=db.get_parts(jid);size=sum(p["size"] for p in parts)
    db.update(jid,uploaded_bytes=size,progress=round(size*100/total,2),message=f"Uploaded {len(parts)}/{count} parts")
  parts=db.get_parts(jid)
  if len(parts)!=count:raise RuntimeError("Multipart parts missing after upload")
  ordered=sorted(parts,key=lambda p:p["part_number"])
  if [p["part_number"] for p in ordered]!=list(range(1,count+1)):
   raise RuntimeError("Multipart part sequence is incomplete; resume the job")
  s3.complete_multipart_upload(Bucket=bucket_name(),Key=key,UploadId=upload_id,MultipartUpload={"Parts":[{"PartNumber":p["part_number"],"ETag":p["etag"]} for p in ordered]})
  db.update(jid,status="completed",progress=100,uploaded_bytes=total,upload_id=None,message="Transfer complete")
 except Exception as e:db.update(jid,status="failed",message=str(e))
 finally:
  with active_lock:active.discard(jid)
def launch(jid):threading.Thread(target=run_job,args=(jid,),daemon=True).start()
def resume_active():
 for j in db.list_active():launch(j["id"])
