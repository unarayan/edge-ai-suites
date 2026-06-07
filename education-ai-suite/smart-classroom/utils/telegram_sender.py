"""
telegram_sender.py
------------------
Sends session data packages to a Telegram group so that OpenClaw (Linux)
can answer the following queries from the shared chat:

  Q1 – "What topics did we cover in today's class?"
  Q2 – "How engaged were the students today?"
  Q3 – "My child was absent — what did they miss?"
  Q4 – "Which students participated the most today?"

Package A  (sent after content-segmentation completes)  →  answers Q1, Q3
  Files: session_meta.json, summary.md, topics.json, mindmap.mmd

Package B+C  (sent when VA pipeline stops)  →  answers Q2, Q4
  Files: engagement_report.json, participation_report.json

Activation: set  telegram.enabled: true  in config.yaml
"""

import json
import logging
import os
import threading
from datetime import datetime

import requests

logger = logging.getLogger(__name__)


# ── Singleton ─────────────────────────────────────────────────────────────────

_sender_instance = None


def get_sender():
    """Return the configured TelegramSender singleton, or None if disabled."""
    global _sender_instance
    if _sender_instance is not None:
        return _sender_instance
    try:
        from utils.config_loader import config  # lazy import avoids circular refs
        tg = getattr(config, "telegram", None)
        if tg and getattr(tg, "enabled", False):
            _sender_instance = TelegramSender(
                bot_token=tg.bot_token,
                chat_id=str(tg.chat_id),
                class_name=getattr(tg, "class_name", "Smart Classroom"),
            )
            logger.info("[Telegram] Sender initialised.")
    except Exception as exc:
        logger.error(f"[Telegram] Failed to initialise sender: {exc}")
    return _sender_instance


# ── Core class ────────────────────────────────────────────────────────────────

class TelegramSender:
    def __init__(self, bot_token: str, chat_id: str, class_name: str):
        self._base = f"https://api.telegram.org/bot{bot_token}"
        self._chat_id = str(chat_id)
        self._class_name = class_name

    # ── Low-level helpers ─────────────────────────────────────────────────────

    def _send_message(self, text: str):
        try:
            resp = requests.post(
                f"{self._base}/sendMessage",
                json={"chat_id": self._chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.error(f"[Telegram] sendMessage failed: {exc}")

    def _send_file(self, file_path: str, caption: str = ""):
        try:
            with open(file_path, "rb") as fh:
                resp = requests.post(
                    f"{self._base}/sendDocument",
                    data={"chat_id": self._chat_id, "caption": caption},
                    files={"document": (os.path.basename(file_path), fh)},
                    timeout=30,
                )
            resp.raise_for_status()
        except Exception as exc:
            logger.error(f"[Telegram] sendDocument failed for {file_path}: {exc}")

    # ── Package A — Session Content ───────────────────────────────────────────

    def send_content_package(self, session_id: str, session_dir: str):
        """
        Triggered after content-segmentation completes.

        Answers:
          Q1 – topics covered  →  topics.json  +  Session Outline in summary.md
          Q3 – absentee pack   →  full summary.md  +  topics.json

        Files sent: session_meta.json, summary.md, topics.json, mindmap.mmd
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        time_str = datetime.now().strftime("%H:%M")

        meta = {
            "schema": "smart_classroom_session_v1",
            "package": "content",
            "session_id": session_id,
            "class_name": self._class_name,
            "date": date_str,
            "time": time_str,
            "files": {
                "summary": "summary.md",
                "topics":  "topics.json",
                "mindmap": "mindmap.mmd",
            },
            "openclaw_hints": {
                "Q1_topics_covered":   "Read topics.json for the timestamped list; read ## Session Outline in summary.md for human-readable form.",
                "Q3_absentee_catchup": "summary.md contains the full lesson content. topics.json gives a timed breakdown the student can use for self-study.",
            },
        }

        meta_path = os.path.join(session_dir, "session_meta.json")
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)

        self._send_message(
            f"*Session Content Ready*\n"
            f"Class: {self._class_name}\n"
            f"Session: `{session_id}`\n"
            f"Date: {date_str}  |  Time: {time_str}\n\n"
            f"_Provides data for Q1 (topics covered) and Q3 (absentee catch-up)_"
        )

        for fname, caption in [
            ("session_meta.json", "Envelope — load this first (Q1 / Q3)"),
            ("summary.md",        "Q1 / Q3 — Lesson summary with key takeaways and session outline"),
            ("topics.json",       "Q1 / Q3 — Timestamped topic segments"),
            ("mindmap.mmd",       "Q1     — Mind map of lesson concepts (Mermaid format)"),
        ]:
            path = os.path.join(session_dir, fname)
            if os.path.exists(path):
                self._send_file(path, caption)
            else:
                logger.warning(f"[Telegram] Package A: {fname} not found, skipping")

        logger.info(f"[Telegram] Package A sent for session {session_id}")

    # ── Package B+C — Engagement & Participation ──────────────────────────────

    def send_engagement_package(self, session_id: str, session_dir: str,
                                va_posture_file: str = None):
        """
        Triggered when the VA pipeline stops.

        Answers:
          Q2 – engagement    →  engagement_report.json
          Q4 – participation →  participation_report.json

        Audio stats are derived from transcription.txt (TEACHER:/STUDENT: labels).
        Video stats are derived from front_posture.txt (GVA metadata JSON-lines).
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        engagement, participation = self._build_engagement_data(
            session_id, date_str, session_dir, va_posture_file
        )

        eng_path  = os.path.join(session_dir, "engagement_report.json")
        part_path = os.path.join(session_dir, "participation_report.json")

        with open(eng_path, "w", encoding="utf-8") as fh:
            json.dump(engagement, fh, indent=2)
        with open(part_path, "w", encoding="utf-8") as fh:
            json.dump(participation, fh, indent=2)

        self._send_message(
            f"*Engagement & Participation Ready*\n"
            f"Class: {self._class_name}\n"
            f"Session: `{session_id}`\n"
            f"Date: {date_str}\n\n"
            f"_Provides data for Q2 (engagement) and Q4 (participation / hand raises)_"
        )
        self._send_file(eng_path,  "Q2 — Engagement report (talk time, attendance, hand raises)")
        self._send_file(part_path, "Q4 — Per-student participation ranked by hand raises")

        logger.info(f"[Telegram] Packages B+C sent for session {session_id}")

    # ── Data builders ─────────────────────────────────────────────────────────

    def _build_engagement_data(self, session_id: str, date_str: str,
                                session_dir: str, va_posture_file: str):
        """Assemble engagement and participation dicts from existing session files."""

        # ── Audio stats from transcription.txt ──────────────────────────────
        teacher_pct, student_pct, q_count = 0, 0, 0
        tx_path = os.path.join(session_dir, "transcription.txt")
        if os.path.exists(tx_path):
            teacher_chars = 0
            student_chars = 0
            with open(tx_path, encoding="utf-8") as fh:
                for line in fh:
                    stripped = line.strip()
                    upper = stripped.upper()
                    if upper.startswith("TEACHER:"):
                        teacher_chars += len(stripped)
                    elif "STUDENT" in upper:
                        student_chars += len(stripped)
                        if "?" in stripped:
                            q_count += 1
            total = teacher_chars + student_chars or 1
            teacher_pct = round(teacher_chars / total * 100)
            student_pct = 100 - teacher_pct

        # ── Video stats from front_posture.txt (GVA JSON-lines) ─────────────
        avg_students = 0
        total_hand_raises = 0
        student_raise_counts: dict = {}

        if va_posture_file and os.path.exists(va_posture_file):
            person_counts = []
            try:
                with open(va_posture_file, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            objects = entry.get("objects", [])
                            person_counts.append(len(objects))
                            for obj in objects:
                                sid = str(obj.get("id", "unknown"))
                                label = obj.get("detection", {}).get("label", "")
                                if "raise_up" in label.lower():
                                    student_raise_counts[sid] = (
                                        student_raise_counts.get(sid, 0) + 1
                                    )
                        except (json.JSONDecodeError, KeyError):
                            continue

                avg_students = (
                    int(sum(person_counts) / len(person_counts)) if person_counts else 0
                )
                total_hand_raises = sum(student_raise_counts.values())
            except Exception as exc:
                logger.warning(f"[Telegram] Could not parse posture file: {exc}")

        sorted_students = sorted(
            student_raise_counts.items(), key=lambda x: x[1], reverse=True
        )
        most_active = [sid for sid, _ in sorted_students[:3]]

        engagement = {
            "schema": "smart_classroom_engagement_v1",
            "package": "engagement",
            "session_id": session_id,
            "class_name": self._class_name,
            "date": date_str,
            "openclaw_hints": {
                "Q2_engagement_summary": (
                    "audio.teacher_talk_time_pct shows how much the teacher spoke vs students. "
                    "video.total_hand_raises and video.avg_students_present indicate class energy. "
                    "audio.questions_asked_by_students reflects verbal interaction."
                ),
                "Q4_most_active_students": most_active,
            },
            "audio": {
                "teacher_talk_time_pct":       teacher_pct,
                "student_talk_time_pct":       student_pct,
                "questions_asked_by_students": q_count,
            },
            "video": {
                "avg_students_present": avg_students,
                "total_hand_raises":    total_hand_raises,
                "most_active_students": most_active,
            },
        }

        participation = {
            "schema": "smart_classroom_participation_v1",
            "package": "participation",
            "session_id": session_id,
            "class_name": self._class_name,
            "date": date_str,
            "openclaw_hints": {
                "Q4_participation_ranking": (
                    "students list is sorted by hand_raises descending. "
                    "Use this to identify the most and least active students."
                ),
            },
            "students": [
                {"student_id": sid, "hand_raises": count, "present": True}
                for sid, count in sorted_students
            ],
        }

        return engagement, participation

    # ── Async fire-and-forget wrappers ────────────────────────────────────────

    def send_content_package_async(self, session_id: str, session_dir: str):
        """Non-blocking wrapper — does not delay the API response."""
        threading.Thread(
            target=self.send_content_package,
            args=(session_id, session_dir),
            daemon=True,
        ).start()

    def send_engagement_package_async(self, session_id: str, session_dir: str,
                                      va_posture_file: str = None):
        """Non-blocking wrapper — does not delay the API response."""
        threading.Thread(
            target=self.send_engagement_package,
            args=(session_id, session_dir, va_posture_file),
            daemon=True,
        ).start()


# ── __main__ test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Fill in before running ↓
    BOT_TOKEN  = "YOUR_BOT_TOKEN_HERE"
    CHAT_ID    = "YOUR_CHAT_ID_HERE"
    CLASS_NAME = "Test Class"

    # Folder that already contains summary.md
    TEST_SESSION_DIR = r"C:\path\to\your\session\output\folder"
    TEST_SESSION_ID  = "test_session_001"

    sender = TelegramSender(BOT_TOKEN, CHAT_ID, CLASS_NAME)

    print("1. Sending text message...")
    sender._send_message(
        f"*Test message from SmartClassroom*\nSession: `{TEST_SESSION_ID}`"
    )
    print("   OK")

    summary_path = os.path.join(TEST_SESSION_DIR, "summary.md")
    if not os.path.exists(summary_path):
        print(f"ERROR: summary.md not found at {summary_path}")
        sys.exit(1)

    print("2. Sending summary.md as document...")
    sender._send_file(summary_path, "Lesson summary (test)")
    print("   OK")

    print("3. Sending full Package A (content package)...")
    sender.send_content_package(TEST_SESSION_ID, TEST_SESSION_DIR)
    print("   OK — check your Telegram group")
