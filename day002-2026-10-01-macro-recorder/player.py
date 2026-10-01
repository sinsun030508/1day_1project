"""녹화한 이벤트를 다시 실행한다."""

import threading
import time

from pynput import keyboard, mouse

import events as ev


class Player:
    def __init__(self, on_progress=None, on_finish=None):
        """on_progress(round_index, total_rounds, event_index, total_events), on_finish(stopped)"""
        self.on_progress = on_progress
        self.on_finish = on_finish
        self._mouse = mouse.Controller()
        self._keyboard = keyboard.Controller()
        self._stop = threading.Event()
        self._thread = None

    @property
    def playing(self):
        return self._thread is not None and self._thread.is_alive()

    def play(self, events, repeat=1, speed=1.0, gap=0.0):
        """repeat<=0이면 중지할 때까지 무한 반복. speed는 배속, gap은 반복 사이 쉬는 시간(초)."""
        if self.playing or not events:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(list(events), repeat, max(speed, 0.1), gap), daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop.set()

    # ---- 내부 ----
    def _run(self, events, repeat, speed, gap):
        total = len(events)
        round_index = 0
        try:
            while not self._stop.is_set():
                round_index += 1
                for i, event in enumerate(events, start=1):
                    if self._stop.is_set():
                        break
                    self._sleep(event.get("dt", 0) / speed)
                    if self._stop.is_set():
                        break
                    self._apply(event)
                    if self.on_progress:
                        self.on_progress(round_index, repeat, i, total)
                if repeat > 0 and round_index >= repeat:
                    break
                if gap:
                    self._sleep(gap)
        finally:
            self._release_all()
            if self.on_finish:
                self.on_finish(self._stop.is_set())

    def _sleep(self, seconds):
        """중지 요청에 바로 반응하도록 쪼개서 기다린다."""
        if seconds > 0:
            self._stop.wait(seconds)

    def _apply(self, event):
        t = event["type"]
        if t == ev.MOVE:
            self._mouse.position = (event["x"], event["y"])
        elif t == ev.CLICK:
            self._mouse.position = (event["x"], event["y"])
            button = getattr(mouse.Button, event["button"], mouse.Button.left)
            (self._mouse.press if event["pressed"] else self._mouse.release)(button)
        elif t == ev.SCROLL:
            self._mouse.position = (event["x"], event["y"])
            self._mouse.scroll(event["dx"], event["dy"])
        elif t in (ev.KEY_PRESS, ev.KEY_RELEASE):
            key = ev.dict_to_key(event["key"])
            try:
                (self._keyboard.press if t == ev.KEY_PRESS else self._keyboard.release)(key)
            except (ValueError, self._keyboard.InvalidKeyException):
                pass  # 이 환경에서 못 누르는 키는 건너뛴다

    def _release_all(self):
        """중간에 멈춰도 눌린 채로 남는 키·버튼이 없게 정리한다."""
        for button in (mouse.Button.left, mouse.Button.right, mouse.Button.middle):
            try:
                self._mouse.release(button)
            except Exception:
                pass
        for key in (keyboard.Key.shift, keyboard.Key.ctrl, keyboard.Key.alt, keyboard.Key.cmd):
            try:
                self._keyboard.release(key)
            except Exception:
                pass
