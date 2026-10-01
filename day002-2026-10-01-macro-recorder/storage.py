"""매크로를 macros/ 폴더에 JSON으로, 앱 설정을 settings.json으로 저장한다."""

import json
import re
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
MACRO_DIR = BASE_DIR / "macros"
SETTINGS_PATH = BASE_DIR / "settings.json"


def _safe_name(name):
    cleaned = re.sub(r'[\\/:*?"<>|]', "_", name).strip() or "macro"
    return cleaned[:50]


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def save(name, events, hotkey=None):
    MACRO_DIR.mkdir(exist_ok=True)
    path = MACRO_DIR / f"{_safe_name(name)}.json"
    if hotkey is None and path.exists():
        try:
            hotkey = _read(path).get("hotkey")  # 덮어써도 지정한 단축키는 유지
        except (json.JSONDecodeError, OSError):
            hotkey = None
    _write(path, {
        "name": name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "duration": round(sum(e.get("dt", 0) for e in events), 2),
        "hotkey": hotkey,
        "events": events,
    })
    return path


def load(path):
    data = _read(path)
    return data["name"], data["events"]


def set_hotkey(path, hotkey):
    """hotkey: Hotkey.to_dict() 결과 또는 None(해제)."""
    data = _read(path)
    data["hotkey"] = hotkey
    _write(path, data)


def list_macros():
    """[{name, path, count, duration, hotkey}] — 최근 저장 순."""
    if not MACRO_DIR.exists():
        return []
    items = []
    for path in sorted(MACRO_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = _read(path)
        except (json.JSONDecodeError, OSError):
            continue  # 깨진 파일은 목록에서 건너뛴다
        items.append({
            "name": data.get("name", path.stem),
            "path": path,
            "count": len(data.get("events", [])),
            "duration": data.get("duration", 0),
            "hotkey": data.get("hotkey"),
        })
    return items


def delete(path):
    Path(path).unlink(missing_ok=True)


def load_settings(default):
    if not SETTINGS_PATH.exists():
        return dict(default)
    try:
        return {**default, **_read(SETTINGS_PATH)}
    except (json.JSONDecodeError, OSError):
        return dict(default)


def save_settings(settings):
    _write(SETTINGS_PATH, settings)
