"""Windows 전역 단축키(RegisterHotKey).

pynput 리스너와 달리 다른 프로그램이 포커스를 가지고 있어도 확실하게 눌린다.
RegisterHotKey는 등록한 스레드의 메시지 큐로 WM_HOTKEY를 보내므로,
등록·해제·메시지 수신을 모두 이 모듈의 전용 스레드 안에서 처리한다.
"""

import ctypes
import queue
import threading
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.PeekMessageW.restype = wintypes.BOOL

MODS = {"alt": 0x0001, "ctrl": 0x0002, "shift": 0x0004, "win": 0x0008}
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001


class Hotkey:
    """ctrl/alt/shift/win 조합 + 가상 키 코드."""

    def __init__(self, mods, vk, label):
        self.mods = [m for m in ("ctrl", "alt", "shift", "win") if m in mods]
        self.vk = vk
        self.label = label

    def to_dict(self):
        return {"mods": self.mods, "vk": self.vk, "label": self.label}

    @classmethod
    def from_dict(cls, data):
        if not data:
            return None
        return cls(data.get("mods", []), data["vk"], data.get("label", ""))

    @property
    def modifier_flags(self):
        flags = MOD_NOREPEAT
        for mod in self.mods:
            flags |= MODS[mod]
        return flags

    def __eq__(self, other):
        return isinstance(other, Hotkey) and self.vk == other.vk and set(self.mods) == set(other.mods)

    def __repr__(self):
        return f"Hotkey({self.label})"


class HotkeyManager(threading.Thread):
    def __init__(self, on_trigger, on_error=None):
        """on_trigger(name): 단축키가 눌렸을 때. on_error(name, hotkey): 등록 실패(다른 프로그램이 선점)."""
        super().__init__(daemon=True)
        self.on_trigger = on_trigger
        self.on_error = on_error
        self._commands = queue.Queue()
        self._idle = threading.Event()  # stop() 시 대기를 바로 깨우는 용도
        self._running = True
        self._by_id = {}       # hotkey id -> 이름
        self._ids = {}         # 이름 -> hotkey id
        self._next_id = 1

    def set_bindings(self, bindings):
        """{이름: Hotkey | None} 전체를 다시 등록한다."""
        self._commands.put(("rebind", dict(bindings)))

    def stop(self):
        self._running = False
        self._idle.set()

    # ---- 전용 스레드 ----
    def run(self):
        msg = wintypes.MSG()
        while self._running:
            self._handle_commands()
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_HOTKEY:
                    name = self._by_id.get(msg.wParam)
                    if name:
                        self.on_trigger(name)
            self._idle.wait(0.01)
        self._unregister_all()

    def _handle_commands(self):
        while True:
            try:
                command, payload = self._commands.get_nowait()
            except queue.Empty:
                return
            if command == "rebind":
                self._unregister_all()
                for name, hotkey in payload.items():
                    if hotkey:
                        self._register(name, hotkey)

    def _register(self, name, hotkey):
        hotkey_id = self._next_id
        self._next_id += 1
        if user32.RegisterHotKey(None, hotkey_id, hotkey.modifier_flags, hotkey.vk):
            self._by_id[hotkey_id] = name
            self._ids[name] = hotkey_id
        elif self.on_error:
            self.on_error(name, hotkey)

    def _unregister_all(self):
        for hotkey_id in self._by_id:
            user32.UnregisterHotKey(None, hotkey_id)
        self._by_id.clear()
        self._ids.clear()


# ---- Tk 키 이벤트 → Hotkey ----
MODIFIER_KEYSYMS = {"Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Win_L", "Win_R", "Super_L", "Super_R"}

KEYSYM_LABELS = {
    "Escape": "Esc", "space": "Space", "Return": "Enter", "Prior": "PageUp", "Next": "PageDown",
    "BackSpace": "Backspace", "Delete": "Delete", "Insert": "Insert", "Home": "Home", "End": "End",
    "Up": "↑", "Down": "↓", "Left": "←", "Right": "→", "Tab": "Tab",
}


def from_tk_event(event):
    """키 입력 이벤트를 Hotkey로. 조합키만 눌렀으면 None."""
    if event.keysym in MODIFIER_KEYSYMS:
        return None

    mods = []
    if event.state & 0x0004:
        mods.append("ctrl")
    if event.state & 0x20000 or event.state & 0x0008:
        mods.append("alt")
    if event.state & 0x0001:
        mods.append("shift")

    label_key = KEYSYM_LABELS.get(event.keysym, event.keysym.upper() if len(event.keysym) == 1 else event.keysym)
    label = "+".join([m.capitalize() for m in mods] + [label_key])
    return Hotkey(mods, event.keycode, label)
