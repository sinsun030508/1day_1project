"""어디서든 텍스트 선택 → Ctrl+Alt+K → 맞춤법 자동 교정"""
import platform
import threading
import time

import pyperclip
from pynput import keyboard

from spell_fix import check_diff

HOTKEY = "<ctrl>+<alt>+k"
MOD = keyboard.Key.cmd if platform.system() == "Darwin" else keyboard.Key.ctrl
kb = keyboard.Controller()


def send(key):
    """Ctrl(맥은 Cmd) + key 입력"""
    with kb.pressed(MOD):
        kb.press(key)
        kb.release(key)
    time.sleep(0.15)  # 클립보드 반영 대기


def fix_selection():
    for k in (keyboard.Key.ctrl, keyboard.Key.alt, keyboard.Key.shift):
        kb.release(k)  # 사용자가 누른 단축키가 복사를 방해하지 않게

    backup = pyperclip.paste()
    pyperclip.copy("")
    send("c")  # 선택 영역 복사
    text = pyperclip.paste()

    if text:
        fixed, segments = check_diff(text)
        if segments:
            pyperclip.copy(fixed)
            send("v")  # 교정본으로 덮어쓰기
            print("교정:", ", ".join(f"{s['before']}→{s['after']}" for s in segments))
        else:
            print("고칠 곳 없음")

    time.sleep(0.2)
    pyperclip.copy(backup)  # 원래 클립보드 복구


def on_hotkey():
    threading.Thread(target=fix_selection, daemon=True).start()


if __name__ == "__main__":
    print(f"실행 중 — 텍스트 선택 후 {HOTKEY} (종료: Ctrl+C)")
    with keyboard.GlobalHotKeys({HOTKEY: on_hotkey}) as listener:
        listener.join()
