"""매크로 녹화기 — 마우스·키보드 동작을 녹화해 반복 재생한다."""

import queue
import tkinter as tk
from tkinter import messagebox, ttk

from pynput import keyboard

import events as ev
import storage
from player import Player
from recorder import Recorder

HOTKEYS = {keyboard.Key.f9: "record", keyboard.Key.f10: "play", keyboard.Key.esc: "stop"}


class App:
    def __init__(self, root):
        self.root = root
        self.queue = queue.Queue()  # 다른 스레드 → UI 갱신 통로
        self.events = []
        self.current_name = ""
        self.countdown_job = None

        self.recorder = Recorder(ignore_keys=HOTKEYS.keys(), on_event=lambda e: self.queue.put(("event", e)))
        self.player = Player(
            on_progress=lambda r, total, i, n: self.queue.put(("progress", (r, total, i, n))),
            on_finish=lambda stopped: self.queue.put(("finish", stopped)),
        )

        self._build_ui()
        self.refresh_macro_list()
        self._start_hotkeys()
        self.root.after(50, self._drain_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- UI ----------------
    def _build_ui(self):
        root = self.root
        root.title("매크로 녹화기")
        root.geometry("820x600")
        root.minsize(720, 560)
        root.columnconfigure(0, weight=3)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(3, weight=1)

        self.status = tk.Label(root, text="대기 중 · F9 녹화 / F10 재생 / Esc 중지", font=("Malgun Gothic", 14, "bold"),
                               bg="#2b2b2b", fg="#eeeeee", pady=12)
        self.status.grid(row=0, column=0, columnspan=2, sticky="ew")

        # 버튼 줄
        bar = ttk.Frame(root, padding=(12, 12, 12, 4))
        bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.btn_record = ttk.Button(bar, text="● 녹화 시작 (F9)", command=self.toggle_record, width=18)
        self.btn_play = ttk.Button(bar, text="▶ 재생 (F10)", command=self.toggle_play, width=16)
        self.btn_stop = ttk.Button(bar, text="■ 중지 (Esc)", command=self.stop_all, width=14)
        for i, btn in enumerate((self.btn_record, self.btn_play, self.btn_stop)):
            btn.grid(row=0, column=i, padx=(0, 8))

        # 설정 줄
        opts = ttk.LabelFrame(root, text="재생 설정", padding=10)
        opts.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 8))

        self.repeat = tk.IntVar(value=1)
        self.infinite = tk.BooleanVar(value=False)
        self.speed = tk.DoubleVar(value=1.0)
        self.gap = tk.DoubleVar(value=0.0)
        self.countdown = tk.BooleanVar(value=True)
        self.record_moves = tk.BooleanVar(value=True)

        ttk.Label(opts, text="반복").grid(row=0, column=0, sticky="w")
        self.spin_repeat = ttk.Spinbox(opts, from_=1, to=9999, width=6, textvariable=self.repeat)
        self.spin_repeat.grid(row=0, column=1, padx=(6, 4))
        ttk.Checkbutton(opts, text="무한", variable=self.infinite, command=self._sync_repeat).grid(row=0, column=2, padx=(0, 18))

        ttk.Label(opts, text="속도").grid(row=0, column=3, sticky="w")
        ttk.Scale(opts, from_=0.25, to=4.0, variable=self.speed, orient="horizontal", length=130,
                  command=lambda _: self.lbl_speed.config(text=f"{self.speed.get():.2f}배")).grid(row=0, column=4, padx=6)
        self.lbl_speed = ttk.Label(opts, text="1.00배", width=7)
        self.lbl_speed.grid(row=0, column=5, padx=(0, 18))

        ttk.Label(opts, text="반복 간격(초)").grid(row=0, column=6, sticky="w")
        ttk.Spinbox(opts, from_=0, to=60, increment=0.5, width=6, textvariable=self.gap).grid(row=0, column=7, padx=6)

        ttk.Checkbutton(opts, text="재생 전 3초 대기", variable=self.countdown).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Checkbutton(opts, text="마우스 이동도 녹화", variable=self.record_moves).grid(row=1, column=3, columnspan=3, sticky="w", pady=(8, 0))

        # 이벤트 목록
        left = ttk.LabelFrame(root, text="이벤트", padding=8)
        left.grid(row=3, column=0, sticky="nsew", padx=(12, 6), pady=(0, 8))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.list_events = tk.Listbox(left, font=("Consolas", 10), activestyle="none")
        self.list_events.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.list_events.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.list_events.config(yscrollcommand=scroll.set)
        self.lbl_summary = ttk.Label(left, text="0개 · 0.0초")
        self.lbl_summary.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # 저장된 매크로
        right = ttk.LabelFrame(root, text="저장된 매크로", padding=8)
        right.grid(row=3, column=1, sticky="nsew", padx=(6, 12), pady=(0, 8))
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        right.columnconfigure(1, weight=1)
        self.list_macros = tk.Listbox(right, activestyle="none")
        self.list_macros.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.list_macros.bind("<Double-Button-1>", lambda _: self.load_selected())
        ttk.Button(right, text="불러오기", command=self.load_selected).grid(row=1, column=0, sticky="ew", pady=(8, 0), padx=(0, 4))
        ttk.Button(right, text="삭제", command=self.delete_selected).grid(row=1, column=1, sticky="ew", pady=(8, 0), padx=(4, 0))

        save = ttk.Frame(right)
        save.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        save.columnconfigure(0, weight=1)
        self.entry_name = ttk.Entry(save)
        self.entry_name.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.entry_name.insert(0, "매크로1")
        ttk.Button(save, text="저장", command=self.save_current).grid(row=0, column=1)

    def set_status(self, text, color="#2b2b2b"):
        self.status.config(text=text, bg=color)

    def _sync_repeat(self):
        self.spin_repeat.config(state="disabled" if self.infinite.get() else "normal")

    # ---------------- 녹화 ----------------
    def toggle_record(self):
        if self.player.playing:
            return
        if self.recorder.recording:
            self.events = self.recorder.stop()
            self.btn_record.config(text="● 녹화 시작 (F9)")
            self.set_status(f"녹화 완료 · {len(self.events)}개 이벤트", "#2b2b2b")
            self._render_events()
        else:
            self.recorder.record_moves = self.record_moves.get()
            self.recorder.start()
            self.events = []
            self.list_events.delete(0, tk.END)
            self.btn_record.config(text="■ 녹화 중지 (F9)")
            self.set_status("● 녹화 중 … F9를 누르면 멈춥니다", "#8b1d1d")

    # ---------------- 재생 ----------------
    def toggle_play(self):
        if self.recorder.recording:
            return
        if self.player.playing or self.countdown_job:
            return self.stop_all()
        if not self.events:
            return messagebox.showinfo("매크로 없음", "먼저 녹화하거나 저장된 매크로를 불러오세요.")
        if self.countdown.get():
            self._countdown(3)
        else:
            self._start_play()

    def _countdown(self, left):
        if left <= 0:
            self.countdown_job = None
            return self._start_play()
        self.set_status(f"{left}초 후 재생 … (Esc 취소)", "#7a5d00")
        self.countdown_job = self.root.after(1000, self._countdown, left - 1)

    def _start_play(self):
        repeat = 0 if self.infinite.get() else max(1, self.repeat.get())
        self.btn_play.config(text="■ 재생 중지 (F10)")
        self.set_status("▶ 재생 중 … Esc를 누르면 멈춥니다", "#1d4e89")
        self.player.play(self.events, repeat=repeat, speed=self.speed.get(), gap=self.gap.get())

    def stop_all(self):
        if self.countdown_job:
            self.root.after_cancel(self.countdown_job)
            self.countdown_job = None
            self.set_status("재생을 취소했습니다", "#2b2b2b")
        if self.player.playing:
            self.player.stop()
        if self.recorder.recording:
            self.toggle_record()

    # ---------------- 저장/불러오기 ----------------
    def save_current(self):
        if not self.events:
            return messagebox.showinfo("저장할 내용 없음", "먼저 녹화를 해주세요.")
        name = self.entry_name.get().strip() or "매크로"
        path = storage.save(name, self.events)
        self.current_name = name
        self.refresh_macro_list()
        self.set_status(f"저장됨 · {path.name}")

    def _selected_macro(self):
        selection = self.list_macros.curselection()
        return self.macro_items[selection[0]] if selection else None

    def load_selected(self):
        item = self._selected_macro()
        if not item:
            return
        name, path, _, _ = item
        self.current_name, self.events = storage.load(path)
        self.entry_name.delete(0, tk.END)
        self.entry_name.insert(0, name)
        self._render_events()
        self.set_status(f"불러옴 · {name} ({len(self.events)}개)")

    def delete_selected(self):
        item = self._selected_macro()
        if not item:
            return
        name, path, _, _ = item
        if messagebox.askyesno("삭제", f"'{name}' 매크로를 삭제할까요?"):
            storage.delete(path)
            self.refresh_macro_list()

    def refresh_macro_list(self):
        self.macro_items = storage.list_macros()
        self.list_macros.delete(0, tk.END)
        for name, _, count, duration in self.macro_items:
            self.list_macros.insert(tk.END, f"{name}  ({count}개 · {duration:.1f}초)")

    # ---------------- 이벤트 목록 ----------------
    def _render_events(self):
        self.list_events.delete(0, tk.END)
        elapsed = 0.0
        for i, event in enumerate(self.events[:2000], start=1):
            elapsed += event.get("dt", 0)
            self.list_events.insert(tk.END, f"{i:>5}  {elapsed:7.2f}s  {ev.describe(event)}")
        if len(self.events) > 2000:
            self.list_events.insert(tk.END, f"… 외 {len(self.events) - 2000}개")
        total = sum(e.get("dt", 0) for e in self.events)
        self.lbl_summary.config(text=f"{len(self.events)}개 · {total:.1f}초")

    # ---------------- 스레드 → UI ----------------
    def _drain_queue(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "event":
                    self.lbl_summary.config(text=f"{len(self.recorder.events)}개 · 녹화 중")
                elif kind == "hotkey":
                    {"record": self.toggle_record, "play": self.toggle_play, "stop": self.stop_all}[payload]()
                elif kind == "progress":
                    round_index, total, i, n = payload
                    label = f"{round_index}/{total}" if total > 0 else f"{round_index}회차"
                    self.set_status(f"▶ 재생 중 {label} · {i}/{n} … Esc 중지", "#1d4e89")
                elif kind == "finish":
                    self.btn_play.config(text="▶ 재생 (F10)")
                    self.set_status("재생을 멈췄습니다" if payload else "재생 완료", "#2b2b2b")
        except queue.Empty:
            pass
        self.root.after(50, self._drain_queue)

    def _start_hotkeys(self):
        """창이 선택돼 있지 않아도 동작하도록 전역 키 리스너를 쓴다."""
        def on_press(key):
            action = HOTKEYS.get(key)
            if action:
                self.queue.put(("hotkey", action))

        self.hotkey_listener = keyboard.Listener(on_press=on_press)
        self.hotkey_listener.start()

    def on_close(self):
        self.player.stop()
        if self.recorder.recording:
            self.recorder.stop()
        self.hotkey_listener.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
