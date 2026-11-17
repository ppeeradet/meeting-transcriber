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
- GitHub Pages Browser Edition ถอดเสียงบนอุปกรณ์ด้วย Transformers.js โดยไม่เชื่อมต่อ Dell backend

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

GitHub Pages (`docs/`) เป็น Browser Edition แยกจาก Dell backend โดยสมบูรณ์ ประมวลผลไฟล์ที่ผู้ใช้เลือกบนอุปกรณ์ด้วย Transformers.js/Whisper และไม่อัปโหลดไฟล์หรือ transcript ไปยัง Dell ผู้ใช้ดาวน์โหลดผลลัพธ์เป็น TXT, SRT และเอกสาร Word-compatible `.doc` ได้ โดยหน้าเว็บระบุชัดว่า `.doc` นี้เป็น HTML ที่ Word เปิดได้ ไม่ใช่ DOCX จริง การดาวน์โหลดจาก URL, Media Converter, Media Library, Transcript Editor และ DOCX จริงใช้ผ่าน Home Portal เท่านั้น

## ทดสอบ

```powershell
python -m unittest discover -s tests -v
```

ผลที่รันจริงและรายการที่ยังรอทดสอบบันทึกไว้ใน [TESTING.md](TESTING.md) เพื่อไม่ให้การทดสอบด้วย viewport หรือ mock ถูกกล่าวอ้างว่าเป็นการทดสอบบนอุปกรณ์จริง

ตรวจไฟล์รายงานด้วย Microsoft Word ที่ติดตั้งบน Dell และส่งออก PDF สำหรับตรวจหน้ากระดาษ:

```powershell
.\scripts\verify-docx-msword.ps1 -DocumentPath .\data\jobs\<job-id>\meeting_report.docx
```

