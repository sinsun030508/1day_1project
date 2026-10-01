"""매크로 녹화기 — 마우스·키보드 동작을 녹화해 반복 재생한다."""

import ctypes
import queue
import tkinter as tk
from tkinter import messagebox, ttk

import events as ev
import hotkeys as hk
import storage
from player import Player
from recorder import Recorder

# 기본 전역 단축키. Esc를 전역으로 잡으면 다른 프로그램에서도 막히고, F12는 윈도우가 예약한 키라 등록되지 않는다.
DEFAULT_HOTKEYS = {
    "record": {"mods": [], "vk": 0x78, "label": "F9"},
    "play": {"mods": [], "vk": 0x79, "label": "F10"},
    "stop": {"mods": [], "vk": 0x77, "label": "F8"},
}
CONTROL_LABELS = {"record": "녹화 시작/중지", "play": "재생 시작/중지", "stop": "즉시 중지"}

DEFAULT_PLAYBACK = {"repeat": 1, "infinite": False, "speed": 1.0, "gap": 0.0, "countdown": False, "record_moves": True}


def enable_dpi_awareness():
    """화면 배율(125% 등)이 걸려 있어도 실제 픽셀 좌표를 쓰도록 한다.

    이걸 켜지 않으면 윈도우가 좌표를 축소해서 넘겨주기 때문에,
    녹화한 위치와 재생하는 위치가 어긋난다.
    """
    user32 = ctypes.windll.user32
    try:  # Windows 10 1703+
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):  # PER_MONITOR_AWARE_V2
            return
    except AttributeError:
        pass
    try:  # Windows 8.1+
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            user32.SetProcessDPIAware()
        except AttributeError:
            pass


def dpi_scale():
    try:
        return ctypes.windll.user32.GetDpiForSystem() / 96
    except AttributeError:
        return 1.0


class App:
    def __init__(self, root):
        self.root = root
        self.queue = queue.Queue()  # 다른 스레드 → UI 갱신 통로
        self.events = []
        self.current_name = ""
        self.countdown_job = None
        self.macro_items = []

        self.settings = storage.load_settings({"hotkeys": DEFAULT_HOTKEYS, "playback": DEFAULT_PLAYBACK})
        self.control_hotkeys = {
            name: hk.Hotkey.from_dict(self.settings["hotkeys"].get(name, DEFAULT_HOTKEYS[name]))
            for name in DEFAULT_HOTKEYS
        }

        self.recorder = Recorder(on_event=lambda e: self.queue.put(("event", e)))
        self.player = Player(
            on_progress=lambda r, total, i, n: self.queue.put(("progress", (r, total, i, n))),
            on_finish=lambda stopped: self.queue.put(("finish", stopped)),
        )
        self.hotkey_manager = hk.HotkeyManager(
            on_trigger=lambda name: self.queue.put(("hotkey", name)),
            on_error=lambda name, hotkey: self.queue.put(("hotkey_error", (name, hotkey))),
        )

        self._build_ui()
        self.refresh_macro_list()
        self.hotkey_manager.start()
        self.apply_hotkeys()
        self.root.bind("<Escape>", lambda _: self.stop_all())
        self._drain_job = self.root.after(50, self._drain_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- UI ----------------
    def _build_ui(self):
        root = self.root
        root.title("매크로 녹화기")
        scale = dpi_scale()
        root.geometry(f"{int(880 * scale)}x{int(660 * scale)}")
        root.minsize(int(780 * scale), int(600 * scale))
        root.columnconfigure(0, weight=3)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(4, weight=1)

        self.status = tk.Label(root, text="대기 중", font=("Malgun Gothic", 14, "bold"),
                               bg="#2b2b2b", fg="#eeeeee", pady=12)
        self.status.grid(row=0, column=0, columnspan=2, sticky="ew")

        bar = ttk.Frame(root, padding=(12, 12, 12, 4))
        bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.btn_record = ttk.Button(bar, text="● 녹화 시작", command=self.toggle_record, width=18)
        self.btn_play = ttk.Button(bar, text="▶ 재생", command=self.toggle_play, width=16)
        self.btn_stop = ttk.Button(bar, text="■ 중지", command=self.stop_all, width=14)
        for i, btn in enumerate((self.btn_record, self.btn_play, self.btn_stop)):
            btn.grid(row=0, column=i, padx=(0, 8))

        # 재생 설정
        opts = ttk.LabelFrame(root, text="재생 설정", padding=10)
        opts.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 6))

        playback = {**DEFAULT_PLAYBACK, **self.settings.get("playback", {})}
        self.repeat = tk.IntVar(value=playback["repeat"])
        self.infinite = tk.BooleanVar(value=playback["infinite"])
        self.speed = tk.DoubleVar(value=playback["speed"])
        self.gap = tk.DoubleVar(value=playback["gap"])
        self.countdown = tk.BooleanVar(value=playback["countdown"])
        self.record_moves = tk.BooleanVar(value=playback["record_moves"])

        ttk.Label(opts, text="반복").grid(row=0, column=0, sticky="w")
        self.spin_repeat = ttk.Spinbox(opts, from_=1, to=9999, width=6, textvariable=self.repeat)
        self.spin_repeat.grid(row=0, column=1, padx=(6, 4))
        ttk.Checkbutton(opts, text="무한", variable=self.infinite, command=self._sync_repeat).grid(row=0, column=2, padx=(0, 18))

        ttk.Label(opts, text="속도").grid(row=0, column=3, sticky="w")
        ttk.Scale(opts, from_=0.25, to=4.0, variable=self.speed, orient="horizontal", length=130,
                  command=lambda _: self.lbl_speed.config(text=f"{self.speed.get():.2f}배")).grid(row=0, column=4, padx=6)
        self.lbl_speed = ttk.Label(opts, text=f"{self.speed.get():.2f}배", width=7)
        self.lbl_speed.grid(row=0, column=5, padx=(0, 18))

        ttk.Label(opts, text="반복 간격(초)").grid(row=0, column=6, sticky="w")
        ttk.Spinbox(opts, from_=0, to=60, increment=0.5, width=6, textvariable=self.gap).grid(row=0, column=7, padx=6)

        ttk.Checkbutton(opts, text="재생 전 3초 기다리기", variable=self.countdown).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Checkbutton(opts, text="마우스 이동도 녹화", variable=self.record_moves).grid(row=1, column=3, columnspan=3, sticky="w", pady=(8, 0))

        # 전역 단축키
        keys = ttk.LabelFrame(root, text="전역 단축키 (다른 창에서도 동작)", padding=10)
        keys.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 6))
        self.hotkey_labels = {}
        for i, name in enumerate(DEFAULT_HOTKEYS):
            ttk.Label(keys, text=CONTROL_LABELS[name]).grid(row=0, column=i * 3, sticky="w", padx=(0 if i == 0 else 16, 6))
            label = ttk.Label(keys, text="", width=14, relief="groove", anchor="center", padding=3)
            label.grid(row=0, column=i * 3 + 1)
            self.hotkey_labels[name] = label
            ttk.Button(keys, text="변경", width=6,
                       command=lambda n=name: self.change_control_hotkey(n)).grid(row=0, column=i * 3 + 2, padx=(4, 0))

        # 이벤트 목록
        left = ttk.LabelFrame(root, text="이벤트", padding=8)
        left.grid(row=4, column=0, sticky="nsew", padx=(12, 6), pady=(0, 8))
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
        right.grid(row=4, column=1, sticky="nsew", padx=(6, 12), pady=(0, 8))
        right.rowconfigure(0, weight=1)
        for col in (0, 1, 2):
            right.columnconfigure(col, weight=1)
        self.list_macros = tk.Listbox(right, activestyle="none")
        self.list_macros.grid(row=0, column=0, columnspan=3, sticky="nsew")
        self.list_macros.bind("<Double-Button-1>", lambda _: self.load_selected())
        ttk.Button(right, text="불러오기", command=self.load_selected).grid(row=1, column=0, sticky="ew", pady=(8, 0), padx=(0, 3))
        ttk.Button(right, text="단축키 지정", command=self.change_macro_hotkey).grid(row=1, column=1, sticky="ew", pady=(8, 0), padx=3)
        ttk.Button(right, text="삭제", command=self.delete_selected).grid(row=1, column=2, sticky="ew", pady=(8, 0), padx=(3, 0))

        save = ttk.Frame(right)
        save.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        save.columnconfigure(0, weight=1)
        self.entry_name = ttk.Entry(save)
        self.entry_name.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.entry_name.insert(0, "매크로1")
        ttk.Button(save, text="저장", command=self.save_current).grid(row=0, column=1)

        self._sync_repeat()
        self._update_idle_status()

    def set_status(self, text, color="#2b2b2b"):
        self.status.config(text=text, bg=color)

    def _update_idle_status(self):
        parts = [f"{CONTROL_LABELS[n]} {self.control_hotkeys[n].label}" for n in DEFAULT_HOTKEYS if self.control_hotkeys[n]]
        self.set_status("대기 중 · " + " / ".join(parts))

    def _sync_repeat(self):
        self.spin_repeat.config(state="disabled" if self.infinite.get() else "normal")

    # ---------------- 단축키 ----------------
    def apply_hotkeys(self):
        """현재 설정된 단축키 전체를 다시 등록하고, 녹화에서 제외할 키도 갱신한다."""
        bindings = {f"ctl:{name}": hotkey for name, hotkey in self.control_hotkeys.items()}
        for item in self.macro_items:
            hotkey = hk.Hotkey.from_dict(item["hotkey"])
            if hotkey:
                bindings[f"macro:{item['path']}"] = hotkey
        self.hotkey_manager.set_bindings(bindings)
        self.recorder.ignore_vks = {h.vk for h in bindings.values()}
        for name, label in self.hotkey_labels.items():
            hotkey = self.control_hotkeys[name]
            label.config(text=hotkey.label if hotkey else "없음")

    def _conflict(self, hotkey, exclude_control=None, exclude_path=None):
        for name, existing in self.control_hotkeys.items():
            if name != exclude_control and existing and existing == hotkey:
                return CONTROL_LABELS[name]
        for item in self.macro_items:
            existing = hk.Hotkey.from_dict(item["hotkey"])
            if item["path"] != exclude_path and existing and existing == hotkey:
                return f"매크로 '{item['name']}'"
        return None

    def change_control_hotkey(self, name):
        result = HotkeyDialog(self.root, CONTROL_LABELS[name], allow_clear=False).result
        if not result:
            return
        conflict = self._conflict(result, exclude_control=name)
        if conflict:
            return messagebox.showwarning("중복", f"{result.label}은(는) 이미 {conflict}에 지정돼 있습니다.")
        self.control_hotkeys[name] = result
        self.settings["hotkeys"][name] = result.to_dict()
        storage.save_settings(self.settings)
        self.apply_hotkeys()
        self._update_idle_status()

    def change_macro_hotkey(self):
        item = self._selected_macro()
        if not item:
            return messagebox.showinfo("선택 없음", "단축키를 지정할 매크로를 먼저 선택하세요.")
        dialog = HotkeyDialog(self.root, f"매크로 '{item['name']}' 실행", allow_clear=True)
        if dialog.result is None:
            return
        if dialog.result == "clear":
            storage.set_hotkey(item["path"], None)
        else:
            conflict = self._conflict(dialog.result, exclude_path=item["path"])
            if conflict:
                return messagebox.showwarning("중복", f"{dialog.result.label}은(는) 이미 {conflict}에 지정돼 있습니다.")
            storage.set_hotkey(item["path"], dialog.result.to_dict())
        self.refresh_macro_list()
        self.apply_hotkeys()

    def _run_hotkey(self, name):
        if name.startswith("ctl:"):
            {"record": self.toggle_record, "play": self.toggle_play, "stop": self.stop_all}[name[4:]]()
            return
        path = name[len("macro:"):]
        item = next((i for i in self.macro_items if str(i["path"]) == path), None)
        if not item or self.recorder.recording:
            return
        if self.player.playing or self.countdown_job:
            return self.stop_all()
        self.current_name, self.events = storage.load(item["path"])
        self._render_events()
        self.entry_name.delete(0, tk.END)
        self.entry_name.insert(0, self.current_name)
        self.toggle_play()

    # ---------------- 녹화 ----------------
    def toggle_record(self):
        if self.player.playing:
            return
        if self.recorder.recording:
            self.events = self.recorder.stop()
            self.btn_record.config(text="● 녹화 시작")
            self.set_status(f"녹화 완료 · {len(self.events)}개 이벤트")
            self._render_events()
        else:
            self.recorder.record_moves = self.record_moves.get()
            self.recorder.start()
            self.events = []
            self.list_events.delete(0, tk.END)
            self.btn_record.config(text="■ 녹화 중지")
            stop_key = self.control_hotkeys["record"].label
            self.set_status(f"● 녹화 중 … {stop_key}를 누르면 멈춥니다", "#8b1d1d")

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
        self.set_status(f"{left}초 후 재생 … ({self.control_hotkeys['stop'].label} 취소)", "#7a5d00")
        self.countdown_job = self.root.after(1000, self._countdown, left - 1)

    def _start_play(self):
        repeat = 0 if self.infinite.get() else max(1, self.repeat.get())
        self.btn_play.config(text="■ 재생 중지")
        self.set_status("▶ 재생 중 …", "#1d4e89")
        self.player.play(self.events, repeat=repeat, speed=self.speed.get(), gap=self.gap.get())

    def stop_all(self):
        if self.countdown_job:
            self.root.after_cancel(self.countdown_job)
            self.countdown_job = None
            self.set_status("재생을 취소했습니다")
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
        self.apply_hotkeys()
        self.set_status(f"저장됨 · {path.name}")

    def _selected_macro(self):
        selection = self.list_macros.curselection()
        return self.macro_items[selection[0]] if selection else None

    def load_selected(self):
        item = self._selected_macro()
        if not item:
            return
        self.current_name, self.events = storage.load(item["path"])
        self.entry_name.delete(0, tk.END)
        self.entry_name.insert(0, self.current_name)
        self._render_events()
        self.set_status(f"불러옴 · {self.current_name} ({len(self.events)}개)")

    def delete_selected(self):
        item = self._selected_macro()
        if not item:
            return
        if messagebox.askyesno("삭제", f"'{item['name']}' 매크로를 삭제할까요?"):
            storage.delete(item["path"])
            self.refresh_macro_list()
            self.apply_hotkeys()

    def refresh_macro_list(self):
        self.macro_items = storage.list_macros()
        self.list_macros.delete(0, tk.END)
        for item in self.macro_items:
            text = f"{item['name']}  ({item['count']}개 · {item['duration']:.1f}초)"
            if item["hotkey"]:
                text += f"  [{item['hotkey'].get('label', '')}]"
            self.list_macros.insert(tk.END, text)

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
                    self._run_hotkey(payload)
                elif kind == "hotkey_error":
                    name, hotkey = payload
                    target = CONTROL_LABELS.get(name[4:], "매크로") if name.startswith("ctl:") else "매크로"
                    messagebox.showwarning(
                        "단축키 등록 실패",
                        f"{hotkey.label} 키를 다른 프로그램이 이미 사용 중이라 {target} 단축키로 등록하지 못했습니다.\n"
                        "다른 조합으로 바꿔 주세요.",
                    )
                elif kind == "progress":
                    round_index, total, i, n = payload
                    label = f"{round_index}/{total}" if total > 0 else f"{round_index}회차"
                    stop_key = self.control_hotkeys["stop"].label
                    self.set_status(f"▶ 재생 중 {label} · {i}/{n} … {stop_key} 중지", "#1d4e89")
                elif kind == "finish":
                    self.btn_play.config(text="▶ 재생")
                    self.set_status("재생을 멈췄습니다" if payload else "재생 완료")
        except queue.Empty:
            pass
        self._drain_job = self.root.after(50, self._drain_queue)

    def _save_playback(self):
        self.settings["playback"] = {
            "repeat": self.repeat.get(), "infinite": self.infinite.get(),
            "speed": round(self.speed.get(), 2), "gap": self.gap.get(),
            "countdown": self.countdown.get(), "record_moves": self.record_moves.get(),
        }
        storage.save_settings(self.settings)

    def on_close(self):
        self.root.after_cancel(self._drain_job)
        self._save_playback()
        self.player.stop()
        if self.recorder.recording:
            self.recorder.stop()
        self.hotkey_manager.stop()
        self.root.destroy()


class HotkeyDialog(tk.Toplevel):
    """키 조합을 눌러서 단축키를 지정하는 작은 창."""

    def __init__(self, parent, target_label, allow_clear):
        super().__init__(parent)
        self.result = None
        self.title("단축키 지정")
        self.resizable(False, False)
        self.transient(parent)

        ttk.Label(self, text=f"{target_label}에 사용할 키를 누르세요", padding=(20, 16, 20, 6)).pack()
        self.preview = ttk.Label(self, text="…", font=("Malgun Gothic", 16, "bold"), padding=(0, 4, 0, 10))
        self.preview.pack()
        ttk.Label(self, text="Ctrl·Alt·Shift와 함께 누르면 조합키가 됩니다", foreground="#666").pack(padx=20)

        buttons = ttk.Frame(self, padding=14)
        buttons.pack()
        if allow_clear:
            ttk.Button(buttons, text="단축키 없음", command=self._clear).grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text="취소", command=self.destroy).grid(row=0, column=1, padx=4)

        self.bind("<KeyPress>", self._on_key)
        self.grab_set()
        self.focus_force()
        parent.wait_window(self)

    def _on_key(self, event):
        hotkey = hk.from_tk_event(event)
        if not hotkey:
            return "break"
        self.preview.config(text=hotkey.label)
        self.result = hotkey
        self.after(250, self.destroy)  # 누른 키를 잠깐 보여주고 닫는다
        return "break"

    def _clear(self):
        self.result = "clear"
        self.destroy()


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    root.tk.call("tk", "scaling", dpi_scale() * 96 / 72)
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
