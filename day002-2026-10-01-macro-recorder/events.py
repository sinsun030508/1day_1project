"""매크로 이벤트의 직렬화 규칙.

이벤트는 딕셔너리 하나로 표현하고, ``dt``는 바로 앞 이벤트로부터 흐른 초다.
    {"dt": 0.12, "type": "click", "x": 100, "y": 200, "button": "left", "pressed": True}
"""

from pynput import keyboard

MOVE = "move"
CLICK = "click"
SCROLL = "scroll"
KEY_PRESS = "key_press"
KEY_RELEASE = "key_release"


def key_to_dict(key):
    """pynput 키 객체를 JSON에 담을 수 있는 형태로 바꾼다."""
    if isinstance(key, keyboard.Key):
        return {"kind": "special", "value": key.name}
    if key.char is not None:
        return {"kind": "char", "value": key.char}
    return {"kind": "vk", "value": key.vk}


def dict_to_key(data):
    """key_to_dict의 역변환."""
    kind, value = data["kind"], data["value"]
    if kind == "special":
        return getattr(keyboard.Key, value)
    if kind == "char":
        return value
    return keyboard.KeyCode.from_vk(value)


def key_vk(key):
    """pynput 키 객체의 가상 키 코드. 전역 단축키와 비교할 때 쓴다."""
    vk = getattr(key, "vk", None)
    if vk is None and hasattr(key, "value"):
        vk = getattr(key.value, "vk", None)
    return vk


def describe(event):
    """목록에 보여줄 한 줄 설명."""
    t = event["type"]
    if t == MOVE:
        return f"이동 → ({event['x']}, {event['y']})"
    if t == CLICK:
        action = "누름" if event["pressed"] else "뗌"
        name = {"left": "왼쪽", "right": "오른쪽", "middle": "가운데"}.get(event["button"], event["button"])
        return f"{name} 버튼 {action} ({event['x']}, {event['y']})"
    if t == SCROLL:
        return f"스크롤 {event['dy']:+d} ({event['x']}, {event['y']})"
    if t in (KEY_PRESS, KEY_RELEASE):
        key = event["key"]
        label = key["value"] if key["kind"] != "vk" else f"vk{key['value']}"
        return f"키 {label} {'누름' if t == KEY_PRESS else '뗌'}"
    return t
