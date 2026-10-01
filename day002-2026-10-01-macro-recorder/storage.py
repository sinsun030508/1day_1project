"""매크로를 macros/ 폴더에 JSON으로 저장한다."""

import json
import re
from datetime import datetime
from pathlib import Path

MACRO_DIR = Path(__file__).parent / "macros"


def _safe_name(name):
    cleaned = re.sub(r'[\\/:*?"<>|]', "_", name).strip() or "macro"
    return cleaned[:50]


def save(name, events):
    MACRO_DIR.mkdir(exist_ok=True)
    path = MACRO_DIR / f"{_safe_name(name)}.json"
    data = {
        "name": name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "duration": round(sum(e.get("dt", 0) for e in events), 2),
        "events": events,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["name"], data["events"]


def list_macros():
    """[(이름, 경로, 이벤트 수, 길이(초))] — 최근 저장 순."""
    if not MACRO_DIR.exists():
        return []
    items = []
    for path in sorted(MACRO_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            items.append((data.get("name", path.stem), path, len(data.get("events", [])), data.get("duration", 0)))
        except (json.JSONDecodeError, OSError):
            continue  # 깨진 파일은 목록에서 건너뛴다
    return items


def delete(path):
    Path(path).unlink(missing_ok=True)
