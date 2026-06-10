"""
scp_sender.py
-------------
Sends session data packages to a remote Linux machine via SCP (OpenSSH).

Used as an alternative to telegram_sender when the Windows machine cannot
reach Telegram's MTProto servers (e.g. corporate proxy filtering raw IPs).

Package A  (sent after content-segmentation completes)
  Files: session_meta.json, summary.md, topics.json, mindmap.mmd
  Answers: Q1 (topics covered) and Q3 (absentee catch-up)

Package B+C  (sent when VA pipeline stops)
  Files: engagement_report.json, participation_report.json
  Answers: Q2 (engagement) and Q4 (most active students)

Activation: set  scp_sender.enabled: true  in config.yaml.

Requirements:
  • OpenSSH client installed (scp / ssh executables on PATH)
  • Windows machine's public key added to ~/.ssh/authorized_keys on the
    remote Linux machine (so no password prompt appears)
  • SSH host alias configured in ~/.ssh/config  OR  host/user in config.yaml
"""

import json
import logging
import os
import subprocess
import threading
from datetime import datetime

logger = logging.getLogger(__name__)


# ── Singleton ──────────────────────────────────────────────────────────────────

_sender_instance = None


def get_scp_sender():
    """Return the configured SCPSender singleton, or None if disabled."""
    global _sender_instance
    if _sender_instance is not None:
        return _sender_instance
    try:
        from utils.config_loader import config  # lazy import avoids circular refs
        cfg = getattr(config, "scp_sender", None)
        if cfg and getattr(cfg, "enabled", False):
            _sender_instance = SCPSender(
                host=str(cfg.host),
                username=getattr(cfg, "username", "") or "",
                identity_file=getattr(cfg, "identity_file", "") or "",
                remote_base_path=str(cfg.remote_base_path),
                class_name=getattr(cfg, "class_name", "Smart Classroom"),
            )
            logger.info("[SCP] Sender initialised.")
    except Exception as exc:
        logger.error(f"[SCP] Failed to initialise sender: {exc}")
    return _sender_instance


# ── Core class ─────────────────────────────────────────────────────────────────

class SCPSender:
    def __init__(self, host: str, username: str, identity_file: str,
                 remote_base_path: str, class_name: str):
        self._host = host
        self._username = username
        self._identity_file = identity_file
        self._remote_base_path = remote_base_path.rstrip("/")
        self._class_name = class_name

    # ── Subprocess helpers ─────────────────────────────────────────────────────

    def _remote_host(self) -> str:
        """Return  user@host  or just  host  depending on config."""
        return f"{self._username}@{self._host}" if self._username else self._host

    def _ssh_options(self) -> list:
        """Common SSH options shared by both ssh and scp commands."""
        opts = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
        if self._identity_file:
            opts = ["-i", self._identity_file] + opts
        return opts

    def _run(self, cmd: list, description: str):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                logger.error(
                    f"[SCP] {description} failed (rc={result.returncode}): "
                    f"{result.stderr.strip()}"
                )
            else:
                logger.info(f"[SCP] {description} succeeded.")
        except subprocess.TimeoutExpired:
            logger.error(f"[SCP] {description} timed out after 120 s.")
        except FileNotFoundError:
            logger.error(
                "[SCP] ssh/scp executable not found. "
                "Ensure the OpenSSH client is installed and on PATH."
            )
        except Exception as exc:
            logger.error(f"[SCP] {description} error: {exc}")

    def _mkdir_remote(self, remote_dir: str):
        """Create the session directory on the remote host."""
        cmd = ["ssh"] + self._ssh_options() + [
            self._remote_host(), f"mkdir -p '{remote_dir}'"
        ]
        self._run(cmd, f"mkdir -p {remote_dir}")

    def _copy_files(self, local_files: list, remote_dir: str):
        """SCP a list of local files to remote_dir/. Missing files are skipped."""
        existing = [f for f in local_files if os.path.exists(f)]
        missing  = set(local_files) - set(existing)
        for f in missing:
            logger.warning(f"[SCP] File not found, skipping: {f}")
        if not existing:
            logger.warning("[SCP] No files to copy.")
            return
        cmd = (
            ["scp"]
            + self._ssh_options()
            + existing
            + [f"{self._remote_host()}:{remote_dir}/"]
        )
        self._run(cmd, f"copy {len(existing)} file(s) → {remote_dir}/")

    # ── Package A — Session Content ────────────────────────────────────────────

    def send_content_package(self, session_id: str, session_dir: str):
        """Build session_meta.json then SCP Package A files to the remote host."""
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
                "Q1_topics_covered":   (
                    "Read topics.json for the timestamped list; "
                    "read ## Session Outline in summary.md for human-readable form."
                ),
                "Q3_absentee_catchup": (
                    "summary.md contains the full lesson content. "
                    "topics.json gives a timed breakdown the student can use for self-study."
                ),
            },
        }

        meta_path = os.path.join(session_dir, "session_meta.json")
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)

        remote_dir = f"{self._remote_base_path}/{session_id}"
        self._mkdir_remote(remote_dir)

        files = [
            os.path.join(session_dir, fname)
            for fname in ("session_meta.json", "summary.md", "topics.json", "mindmap.mmd")
        ]
        self._copy_files(files, remote_dir)
        logger.info(f"[SCP] Package A sent for session {session_id}")

    def send_content_package_async(self, session_id: str, session_dir: str):
        """Non-blocking wrapper — does not delay the API response."""
        threading.Thread(
            target=self.send_content_package,
            args=(session_id, session_dir),
            daemon=True,
        ).start()

    # ── Package B+C — Engagement & Participation ───────────────────────────────

    def send_engagement_package(self, session_id: str, session_dir: str,
                                va_posture_file: str = None):
        """Build engagement / participation JSON files then SCP them."""
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

        remote_dir = f"{self._remote_base_path}/{session_id}"
        self._mkdir_remote(remote_dir)
        self._copy_files([eng_path, part_path], remote_dir)
        logger.info(f"[SCP] Package B+C sent for session {session_id}")

    def send_engagement_package_async(self, session_id: str, session_dir: str,
                                      va_posture_file: str = None):
        """Non-blocking wrapper — does not delay the API response."""
        threading.Thread(
            target=self.send_engagement_package,
            args=(session_id, session_dir, va_posture_file),
            daemon=True,
        ).start()

    # ── Engagement data builder ────────────────────────────────────────────────

    def _build_engagement_data(self, session_id: str, date_str: str,
                                session_dir: str, va_posture_file: str):
        """Assemble engagement and participation dicts from existing session files."""

        # ── Audio stats from transcription.txt ────────────────────────────────
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

        # ── Video stats from front_posture.txt (GVA JSON-lines) ───────────────
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
                logger.warning(f"[SCP] Could not parse posture file: {exc}")

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
