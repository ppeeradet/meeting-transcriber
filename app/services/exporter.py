from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def timestamp(seconds: float, separator: str = ",") -> str:
    milliseconds = max(0, round(float(seconds) * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}{separator}{millis:03}"


def export_transcript(
    output_dir: Path,
    title: str,
    source: str,
    language: str,
    rows: list[dict[str, Any]],
    generated_at: str,
) -> list[str]:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt

    output_dir.mkdir(parents=True, exist_ok=True)
    normalized = [
        {"start": float(row["start"]), "end": float(row["end"]), "text": str(row["text"]).strip()}
        for row in rows
    ]
    txt = [f"[{timestamp(row['start'], '.')}] {row['text']}" for row in normalized]
    srt: list[str] = []
    vtt = ["WEBVTT", ""]
    markdown = [f"# {title}", "", f"- ต้นทาง: {source}", f"- ภาษา: {language}", f"- สร้างเมื่อ: {generated_at}", "", "## ถอดเสียง", ""]
    for index, row in enumerate(normalized, 1):
        start = timestamp(row["start"])
        end = timestamp(row["end"])
        srt.extend([str(index), f"{start} --> {end}", row["text"], ""])
        vtt.extend([f"{timestamp(row['start'], '.')} --> {timestamp(row['end'], '.')}", row["text"], ""])
        markdown.append(f"**[{timestamp(row['start'], '.')}]** {row['text']}")

    (output_dir / "transcript.txt").write_text("\n".join(txt), encoding="utf-8")
    (output_dir / "transcript.srt").write_text("\n".join(srt), encoding="utf-8")
    (output_dir / "transcript.vtt").write_text("\n".join(vtt), encoding="utf-8")
    (output_dir / "transcript.md").write_text("\n\n".join(markdown), encoding="utf-8")
    (output_dir / "transcript.json").write_text(
        json.dumps({"language": language, "segments": normalized}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    transcript = Document()
    section = transcript.sections[0]
    section.top_margin = section.bottom_margin = Inches(0.7)
    heading = transcript.add_heading(title, 0)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    transcript.add_paragraph(f"ต้นทาง: {source}")
    transcript.add_paragraph(f"ภาษา: {language} | สร้างเมื่อ: {generated_at}")
    transcript.add_heading("ถอดเสียงฉบับเต็ม", level=1)
    for row in normalized:
        paragraph = transcript.add_paragraph()
        time_run = paragraph.add_run(f"[{timestamp(row['start'], '.')}] ")
        time_run.bold = True
        time_run.font.size = Pt(9)
        paragraph.add_run(row["text"])
    transcript.save(output_dir / "transcript_full.docx")

    report = Document()
    report.sections[0].top_margin = report.sections[0].bottom_margin = Inches(0.7)
    report_heading = report.add_heading("รายงานการประชุม", 0)
    report_heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    notice = report.add_paragraph("ฉบับรอตรวจทาน — ประเด็นด้านล่างค้นหาจากคำสำคัญและยังไม่ได้ตรวจสอบความถูกต้องโดยบุคคล")
    notice.runs[0].bold = True
    table = report.add_table(rows=5, cols=2)
    table.style = "Table Grid"
    metadata = [
        ("ชื่อการประชุม", title), ("วันและเวลา", "กรุณาตรวจสอบ/กรอกข้อมูล"),
        ("สถานที่/ช่องทาง", source), ("ประธาน/ผู้จัด", "กรุณาตรวจสอบ/กรอกข้อมูล"),
        ("ผู้เข้าร่วม", "กรุณาตรวจสอบ/กรอกข้อมูล"),
    ]
    for row, (label, value) in zip(table.rows, metadata):
        row.cells[0].text = label
        row.cells[1].text = value
    decisions = [row["text"] for row in normalized if any(key in row["text"] for key in ("มติ", "ตกลง", "สรุปว่า"))]
    actions = [row["text"] for row in normalized if any(key in row["text"] for key in ("มอบหมาย", "ดำเนินการ", "รับผิดชอบ", "ภายใน", "กำหนด"))]
    for heading_text, items in (("วาระและประเด็นสำคัญ", []), ("มติที่ประชุม (รอตรวจทาน)", decisions), ("งานที่มอบหมาย (รอตรวจทาน)", actions)):
        report.add_heading(heading_text, level=1)
        if items:
            for item in items:
                report.add_paragraph(item, style="List Bullet")
        else:
            report.add_paragraph("กรุณาตรวจสอบและสรุปจากถอดเสียงฉบับเต็ม")
    report.add_heading("ภาคผนวก: ถอดเสียงพร้อมเวลา", level=1)
    for row in normalized:
        report.add_paragraph(f"[{timestamp(row['start'], '.')}] {row['text']}")
    report.save(output_dir / "meeting_report.docx")
    return ["transcript.txt", "transcript.srt", "transcript.vtt", "transcript.md", "transcript.json", "transcript_full.docx", "meeting_report.docx"]
