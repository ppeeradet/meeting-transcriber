# Meeting Transcriber

เครื่องมือส่วนตัวสำหรับดาวน์โหลดเสียงจาก URL คุณภาพสูง ตั้งชื่อไฟล์ ฝังภาพหน้าปก และถอดเสียงภาษาไทยบน Dell PC โดยไฟล์ทั้งหมดเก็บในเครื่องเท่านั้น

## ความสามารถ

- รับ YouTube/URL ที่ `yt-dlp` รองรับหลายรายการ
- รับไฟล์ในเครื่อง MP3, MP4, M4A, WAV, WEBM, MOV, MKV, AAC, FLAC, OGG, OPUS และ MPEG
- เก็บไฟล์เสียงต้นฉบับและสร้าง MP3 VBR คุณภาพสูง
- ใช้ชื่อคลิปอัตโนมัติหรือกำหนดชื่อเอง
- ดาวน์โหลดและฝังภาพหน้าปกลงใน MP3
- ถอดเสียงด้วย Faster Whisper เป็น TXT, SRT และ JSON พร้อม timestamp
- สร้าง `transcript_full.docx` และ `meeting_report.docx` สำหรับ Microsoft Word
- คิวงานและประวัติแบบ JSON ที่เปิดต่อหลังรีสตาร์ตได้
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
  jobs/<job-id>/
    source.*
    <ชื่อที่กำหนด>.mp3
    thumbnail.jpg
    transcript.txt
    transcript.srt
    transcript.json
```

## ความเป็นส่วนตัว

Backend bind ที่ `127.0.0.1` โดยค่าเริ่มต้น GitHub Pages ไม่มี API และไม่มีไฟล์งาน หากต้องการเข้าจากมือถือให้เพิ่ม route ใน Tailscale Serve ภายหลังโดยไม่แก้ route เดิม

## ทดสอบ

```powershell
python -m unittest discover -s tests -v
```

