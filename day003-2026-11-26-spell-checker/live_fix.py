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
from spell_fix import check, check_diff, looks_like_prose, strip_prefix

PAUSE_TITLES = ("League of Legends",)       # 이 창이 앞에 있으면 검사 중지
TRIGGER_KEYS = {keyboard.Key.space, keyboard.Key.enter}
TRIGGER_CHARS = {".", ",", "?", "!"}
HIDE_AFTER_MS = 5000
MAX_CHARS = 60                              # 말풍선 한 줄에 보여줄 최대 글자 수

user32 = ctypes.windll.user32
results = queue.Queue()


# ---------- 화면 정보 읽기 ----------
def work_area():
    """작업 표시줄을 뺀 화면 영역"""
    rect = wt.RECT()
    if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
        return rect.left, rect.top, rect.right, rect.bottom
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def place(width, height, box):
    """말풍선 위치 — 글 쓰는 칸(box)을 가리지 않는 곳.

    칸 아래 → 칸 위 → 둘 다 자리가 없으면(화면을 꽉 채운 편집기) 오른쪽 아래 구석.
    """
    left, top, right, bottom = work_area()
    if box:
        b_left, b_top, _, b_bottom = box
        x = min(max(b_left, left + 8), max(left + 8, right - width - 8))
        if b_bottom + height + 6 <= bottom:
            return x, b_bottom + 6
        if b_top - height - 6 >= top:
            return x, b_top - height - 6
    return right - width - 16, bottom - height - 16


def paused():
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(user32.GetForegroundWindow(), buf, 256)
    return any(t in buf.value for t in PAUSE_TITLES)


def edited_prefix(previous, current):
    """커서 위치를 모를 때, 이전 내용과 비교해 방금 고친 곳까지의 글을 돌려준다."""
    if previous is None:
        return current if chr(10) not in current.strip() else ""  # 여러 줄이면 추측하지 않는다
    if previous == current:
        return ""
    limit = min(len(previous), len(current))
    head = 0
    while head < limit and previous[head] == current[head]:
        head += 1
    tail = 0
    while tail < limit - head and previous[-1 - tail] == current[-1 - tail]:
        tail += 1
    return current[:len(current) - tail]


def text_before_caret(ctrl):
    """문서 처음부터 커서까지의 글. 앱이 커서를 알려주지 않으면 None."""
    pattern = ctrl.GetPattern(auto.PatternId.TextPattern)
    if not pattern:
        return None
    selection = pattern.GetSelection()
    if not selection:
        return None
    span = pattern.DocumentRange.Clone()
    span.MoveEndpointByRange(auto.TextPatternRangeEndpoint.End, selection[0],
                             auto.TextPatternRangeEndpoint.Start, waitTime=0)
    return span.GetText(-1) or ""


_previous = {}  # 입력칸 → 직전에 읽은 내용


def focused_input():
    """(커서까지의 글, 입력칸 영역) — UI Automation"""
    with auto.UIAutomationInitializerInThread():
        ctrl = auto.GetFocusedControl()
        if not ctrl:
            return "", None
        r = ctrl.BoundingRectangle
        box = (r.left, r.top, r.right, r.bottom) if r.right > r.left else None
        try:
            text = text_before_caret(ctrl)
        except Exception:
            text = None
        if text is None and (p := ctrl.GetPattern(auto.PatternId.ValuePattern)):
            value = p.Value or ""
            key = tuple(ctrl.GetRuntimeId() or ())
            text = edited_prefix(_previous.get(key), value)
            _previous[key] = value
    return text or "", box


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
        text, box = focused_input()
        line = strip_prefix(last_sentence(text))
    except Exception:
        return
    if not looks_like_prose(line):
        results.put(None)   # 코드·링크·영문 줄은 건드리지 않는다
        return
    fixed, segments = check_diff(line)
    results.put((fixed, segments, box) if segments else None)


def on_press(key):
    results.put(None)  # 다시 타자를 치기 시작하면 떠 있던 말풍선을 먼저 치운다
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
# 포커스를 뺏지 않고(NOACTIVATE+TOOLWINDOW), 클릭은 아래 창으로 통과시킨다(TRANSPARENT).
# 말풍선이 글 쓰는 자리를 덮더라도 그 아래를 그대로 클릭할 수 있다.
user32.SetWindowLongW(hwnd, -20, user32.GetWindowLongW(hwnd, -20) | 0x08000000 | 0x80 | 0x20)
user32.ShowWindow(hwnd, 0)
hide_job = None


def hide():
    user32.ShowWindow(hwnd, 0)


def chip(text, fg="#222", bg=BG, font=FONT):
    part = tk.Label(sentence, text=text, fg=fg, bg=bg, font=font,
                    bd=0, padx=0, pady=0, highlightthickness=0)
    part.pack(side="left")


def trim(fixed, segments):
    """긴 문장은 고친 곳 주변만 잘라서 보여준다 (말풍선이 화면을 가로지르지 않게)."""
    if len(fixed) <= MAX_CHARS or not segments:
        return fixed, segments
    start = max(0, segments[0]["start"] - 8)
    end = min(len(fixed), start + MAX_CHARS)
    head = "…" if start else ""
    text = head + fixed[start:end] + ("…" if end < len(fixed) else "")
    shift = len(head) - start
    moved = []
    for seg in segments:
        a = max(len(head), seg["start"] + shift)
        b = min(len(head) + (end - start), seg["end"] + shift)
        if a < b:
            moved.append({**seg, "start": a, "end": b})
    return text, moved


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
    line = " · ".join(parts)
    summary.config(text=line if len(line) <= MAX_CHARS else line[:MAX_CHARS - 1] + "…")


def show(fixed, segments, box):
    global hide_job
    render(*trim(fixed, segments))
    root.update_idletasks()
    x, y = place(root.winfo_reqwidth(), root.winfo_reqheight(), box)
    root.geometry(f"+{x}+{y}")
    user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
    if hide_job:
        root.after_cancel(hide_job)
    hide_job = root.after(HIDE_AFTER_MS, hide)


def poll():
    while not results.empty():
        item = results.get()
        show(*item) if item else hide()
    root.after(50, poll)


if __name__ == "__main__":
    ensure_single("live_fix")  # 두 번 켜면 말풍선이 겹치므로 먼저 막는다
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # 고해상도 좌표 보정
    except Exception:
        pass
    check("준비")  # Kiwi 미리 로딩
    keyboard.Listener(on_press=on_press, daemon=True).start()
    print("실시간 검사 실행 중 (종료: 이 창 닫기)")
    poll()
    root.mainloop()
