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

from single_instance import ensure_single
from spell_fix import check, check_diff

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
    fixed, segments = check_diff(line) if line else ("", [])
    results.put((fixed, segments, caret_pos()) if segments else None)


def on_press(key):
    if key in TRIGGER_KEYS or getattr(key, "char", None) in TRIGGER_CHARS:
        threading.Thread(target=inspect, daemon=True).start()


# ---------- 말풍선 ----------
BG = "#FFF6C8"          # 말풍선 바탕
FONT = ("맑은 고딕", 11)
FONT_FIX = ("맑은 고딕", 11, "bold")
# 맞춤법 오류는 빨강, 띄어쓰기만 고친 곳은 파랑
MARK = {"spelling": {"bg": "#FFD3D3", "fg": "#C62828"},
        "spacing": {"bg": "#D9E6FF", "fg": "#1A4FA0"}}

root = tk.Tk()
root.overrideredirect(True)
root.attributes("-topmost", True)
root.configure(bg=BG)
bubble = tk.Frame(root, bg=BG, relief="solid", bd=1)
bubble.pack()
sentence = tk.Frame(bubble, bg=BG)          # 교정문 (고친 부분만 빨갛게)
sentence.pack(anchor="w", padx=8, pady=(4, 0))
summary = tk.Label(bubble, bg=BG, fg="#8A7B4A", font=("맑은 고딕", 9),
                   anchor="w", justify="left")
summary.pack(anchor="w", padx=8, pady=(1, 4))
root.update()
hwnd = user32.GetParent(root.winfo_id())
# 말풍선이 포커스를 뺏지 않게 (NOACTIVATE + TOOLWINDOW)
user32.SetWindowLongW(hwnd, -20, user32.GetWindowLongW(hwnd, -20) | 0x08000000 | 0x80)
user32.ShowWindow(hwnd, 0)
hide_job = None


def hide():
    user32.ShowWindow(hwnd, 0)


def chip(text, fg="#222", bg=BG, font=FONT):
    part = tk.Label(sentence, text=text, fg=fg, bg=bg, font=font,
                    bd=0, padx=0, pady=0, highlightthickness=0)
    part.pack(side="left")
    part.bind("<Button-1>", lambda e: hide())


def render(fixed, segments):
    """교정문을 쓰되 고친 구간만 다른 색으로 — 어디가 틀렸는지 바로 보이게."""
    for old in sentence.winfo_children():
        old.destroy()
    chip("✔ ", fg="#2E7D32")
    pos = 0
    for seg in segments:
        if seg["start"] > pos:
            chip(fixed[pos:seg["start"]])
        chip(fixed[seg["start"]:seg["end"]], font=FONT_FIX, **MARK[seg["kind"]])
        pos = seg["end"]
    chip(fixed[pos:])
    parts = [f"{s['before']} → {s['after']}" for s in segments if s["kind"] == "spelling"]
    spacing = sum(1 for s in segments if s["kind"] == "spacing")
    if spacing:
        parts.append(f"띄어쓰기 {spacing}곳")
    summary.config(text=" · ".join(parts))


def show(fixed, segments, x, y):
    global hide_job
    render(fixed, segments)
    root.update_idletasks()
    root.geometry(f"+{x}+{max(0, y - root.winfo_reqheight() - 8)}")
    user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
    if hide_job:
        root.after_cancel(hide_job)
    hide_job = root.after(HIDE_AFTER_MS, hide)


def poll():
    while not results.empty():
        item = results.get()
        show(item[0], item[1], *item[2]) if item else hide()
    root.after(50, poll)


if __name__ == "__main__":
    ensure_single("live_fix")  # 두 번 켜면 말풍선이 겹치므로 먼저 막는다
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # 고해상도 좌표 보정
    except Exception:
        pass
    check("준비")  # Kiwi 미리 로딩
    keyboard.Listener(on_press=on_press, daemon=True).start()
    for widget in (root, bubble, sentence, summary):
        widget.bind("<Button-1>", lambda e: hide())  # 클릭하면 닫기
    print("실시간 검사 실행 중 (종료: 이 창 닫기)")
    poll()
    root.mainloop()
