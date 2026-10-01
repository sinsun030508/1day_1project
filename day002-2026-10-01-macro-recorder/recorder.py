"""마우스·키보드 입력을 녹화한다."""

import time

from pynput import keyboard, mouse

import events as ev


class Recorder:
    def __init__(self, ignore_vks=(), move_interval=0.02, on_event=None):
        """ignore_vks: 녹화에서 제외할 가상 키 코드 (앱 단축키). move_interval: 마우스 이동 기록 간격(초)."""
        self.ignore_vks = set(ignore_vks)
        self.move_interval = move_interval
        self.record_moves = True  # 끄면 클릭 지점만 남아 파일이 훨씬 가벼워진다
        self.on_event = on_event
        self.events = []
        self._listeners = []
        self._last_time = 0.0
        self._last_move_time = 0.0
        self.recording = False

    def start(self):
        if self.recording:
            return
        self.events = []
        self.recording = True
        self._last_time = time.perf_counter()
        self._last_move_time = 0.0
        self._listeners = [
            mouse.Listener(on_move=self._on_move, on_click=self._on_click, on_scroll=self._on_scroll),
            keyboard.Listener(on_press=self._on_press, on_release=self._on_release),
        ]
        for listener in self._listeners:
            listener.start()

    def stop(self):
        self.recording = False
        for listener in self._listeners:
            listener.stop()
        self._listeners = []
        return self.events

    # ---- 내부 ----
    def _append(self, **fields):
        now = time.perf_counter()
        event = {"dt": round(now - self._last_time, 4), **fields}
        self._last_time = now
        self.events.append(event)
        if self.on_event:
            self.on_event(event)

    def _on_move(self, x, y):
        if not self.recording or not self.record_moves:
            return
        now = time.perf_counter()
        if now - self._last_move_time < self.move_interval:
            return  # 이동은 너무 잦아서 일정 간격으로만 기록한다
        self._last_move_time = now
        self._append(type=ev.MOVE, x=int(x), y=int(y))

    def _on_click(self, x, y, button, pressed):
        if self.recording:
            self._append(type=ev.CLICK, x=int(x), y=int(y), button=button.name, pressed=pressed)

    def _on_scroll(self, x, y, dx, dy):
        if self.recording:
            self._append(type=ev.SCROLL, x=int(x), y=int(y), dx=int(dx), dy=int(dy))

    def _ignored(self, key):
        return ev.key_vk(key) in self.ignore_vks

    def _on_press(self, key):
        if self.recording and not self._ignored(key):
            self._append(type=ev.KEY_PRESS, key=ev.key_to_dict(key))

    def _on_release(self, key):
        if self.recording and not self._ignored(key):
            self._append(type=ev.KEY_RELEASE, key=ev.key_to_dict(key))
