"""입력하는 동안 맞춤법·띄어쓰기 검사 → 커서 위에 말풍선 (Windows)"""
import ctypes
import ctypes.wintypes as wt
import queue
import re
import threading
import time
import tkinter as tk

import uiautomation as auto
from pynput import keyboard

from spell_fix import check

PAUSE_TITLES = ("League of Legends",)       # 이 창이 앞에 있으면 검사 중지
TRIGGER_KEYS = {keyboard.Key.space, keyboard.Key.enter}
TRIGGER_CHARS = {".", ",", "?", "!"}
HIDE_AFTER_MS = 5000

user32 = ctypes.windll.user32
results = queue.Queue()


# ---------- 화면 정보 읽기 ----------
class GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD),
                ("hwndActive", wt.HWND), ("hwndFocus", wt.HWND),
                ("hwndCapture", wt.HWND), ("hwndMenuOwner", wt.HWND),
                ("hwndMoveSize", wt.HWND), ("hwndCaret", wt.HWND),
                ("rcCaret", wt.RECT)]


def caret_pos():
    """입력 커서 위치 (못 찾으면 마우스 위치)"""
    info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    pt = wt.POINT()
    if user32.GetGUIThreadInfo(0, ctypes.byref(info)) and info.hwndCaret:
        pt.x, pt.y = info.rcCaret.left, info.rcCaret.top
        user32.ClientToScreen(info.hwndCaret, ctypes.byref(pt))
    else:
        user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def paused():
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(user32.GetForegroundWindow(), buf, 256)
    return any(t in buf.value for t in PAUSE_TITLES)


def focused_text():
    """현재 입력창의 글 (UI Automation)"""
    with auto.UIAutomationInitializerInThread():
        ctrl = auto.GetFocusedControl()
        if not ctrl:
            return ""
        if p := ctrl.GetPattern(auto.PatternId.ValuePattern):
            return p.Value or ""
        if p := ctrl.GetPattern(auto.PatternId.TextPattern):
            return p.DocumentRange.GetText(-1) or ""
    return ""


def last_sentence(text):
    lines = text.rstrip().splitlines()
    if not lines:
        return ""
    parts = [s for s in re.split(r"(?<=[.!?])\s+", lines[-1]) if s.strip()]
    return parts[-1].strip()[-200:] if parts else ""


# ---------- 검사 ----------
def inspect():
    time.sleep(0.1)  # 한글 조합(IME) 확정 대기
    if paused():
        return
    try:
        line = last_sentence(focused_text())
    except Exception:
        return
    fixed, changes = check(line) if line else ("", [])
    results.put((fixed, caret_pos()) if changes else None)


def on_press(key):
    if key in TRIGGER_KEYS or getattr(key, "char", None) in TRIGGER_CHARS:
        threading.Thread(target=inspect, daemon=True).start()


# ---------- 말풍선 ----------
root = tk.Tk()
root.overrideredirect(True)
root.attributes("-topmost", True)
label = tk.Label(root, bg="#FFF6C8", fg="#222", font=("맑은 고딕", 11),
                 padx=8, pady=4, relief="solid", bd=1)
label.pack()
root.update()
hwnd = user32.GetParent(root.winfo_id())
# 말풍선이 포커스를 뺏지 않게 (NOACTIVATE + TOOLWINDOW)
user32.SetWindowLongW(hwnd, -20, user32.GetWindowLongW(hwnd, -20) | 0x08000000 | 0x80)
user32.ShowWindow(hwnd, 0)
hide_job = None


def hide():
    user32.ShowWindow(hwnd, 0)


def show(fixed, x, y):
    global hide_job
    label.config(text="✔ " + fixed)
    root.update_idletasks()
    root.geometry(f"+{x}+{max(0, y - label.winfo_reqheight() - 8)}")
    user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
    if hide_job:
        root.after_cancel(hide_job)
    hide_job = root.after(HIDE_AFTER_MS, hide)


def poll():
    while not results.empty():
        item = results.get()
        show(item[0], *item[1]) if item else hide()
    root.after(50, poll)


if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # 고해상도 좌표 보정
    except Exception:
        pass
    check("준비")  # Kiwi 미리 로딩
    keyboard.Listener(on_press=on_press, daemon=True).start()
    label.bind("<Button-1>", lambda e: hide())  # 클릭하면 닫기
    print("실시간 검사 실행 중 (종료: 이 창 닫기)")
    poll()
    root.mainloop()
