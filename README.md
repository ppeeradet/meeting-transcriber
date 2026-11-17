# Personal Media Hub

ศูนย์กลางส่วนตัวสำหรับดาวน์โหลด แปลงไฟล์ จัดการสื่อ และถอดเสียงบน PC โดยไฟล์งานเก็บในเครื่องเท่านั้น

## ความสามารถ

- รับ YouTube/URL ที่ `yt-dlp` รองรับหลายรายการ
- เลือกดาวน์โหลดวิดีโอพร้อมเสียงคุณภาพสูงสุดจาก URL และรวมเป็น MP4
- รับไฟล์ในเครื่อง MP3, MP4, M4A, WAV, WEBM, MOV, MKV, AAC, FLAC, OGG, OPUS และ MPEG
- เก็บไฟล์เสียงต้นฉบับและสร้าง MP3 VBR คุณภาพสูง
- ใช้ชื่อคลิปอัตโนมัติหรือกำหนดชื่อเอง
- ดาวน์โหลดและฝังภาพหน้าปกลงใน MP3
- แปลงไฟล์เสียง/วิดีโอเป็น MP3, WAV, M4A, FLAC หรือ MP4 โดยเก็บต้นฉบับไว้
- ถอดเสียงด้วย Faster Whisper เป็น TXT, SRT และ JSON พร้อม timestamp
- สร้าง `transcript_full.docx` และ `meeting_report.docx` สำหรับ Microsoft Word
- คิวงานและประวัติแบบ SQLite ที่เปิดต่อหลังรีสตาร์ตได้ พร้อมสำเนา JSON ระหว่าง migration
- FastAPI backend + หน้าเว็บ responsive
- GitHub Pages เป็นหน้าแนะนำเท่านั้น ไม่อัปโหลดเสียงหรือ transcript

## เริ่มใช้งาน

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lite.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

เปิด `http://127.0.0.1:8765/` แล้ววาง URL บรรทัดละหนึ่งรายการ

สำหรับถอดเสียง ให้ติดตั้ง `requirements.txt` แทนชุด lite การดาวน์โหลด MP3 ใช้งานได้แม้ยังไม่ติดตั้ง Faster Whisper

## โครงสร้างข้อมูล

```text
data/
  jobs.json
  jobs.json.pre-sqlite.bak
  media_hub.sqlite3
  jobs/<job-id>/
    source.*
    <ชื่อที่กำหนด>.mp3
    thumbnail.jpg
    transcript.txt
    transcript.srt
    transcript.json
```

## ความเป็นส่วนตัว

Backend bind ที่ `127.0.0.1` โดยค่าเริ่มต้น GitHub Pages ไม่มี API และไม่มีไฟล์งาน การเข้าจากมือถือใช้ route ภายใน Tailscale โดยไม่เปิด backend สู่สาธารณะ

การติดตั้งบน Dell ใช้ Tailscale Serve path `/meeting-transcriber` สำหรับ Home Portal เท่านั้น ต้องตรวจ network security ก่อนเลือก deployment mode และห้ามเปิด Public Funnel

GitHub Pages (`docs/`) เป็นระบบแยกที่ประมวลผลบนอุปกรณ์ผู้ใช้ด้วย Transformers.js/Whisper โดยไม่เรียก API ของ Dell และไม่อัปโหลดไฟล์ ผู้ใช้ดาวน์โหลดผลลัพธ์เป็น TXT, SRT และเอกสาร Word-compatible `.doc` ได้ การดาวน์โหลดวิดีโอจาก URL ยังคงใช้ Home Portal เนื่องจากข้อจำกัด cross-origin ของเบราว์เซอร์

## ทดสอบ

```powershell
python -m unittest discover -s tests -v
```

