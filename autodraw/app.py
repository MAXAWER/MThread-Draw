"""The AutoDraw desktop window."""

from __future__ import annotations

import os
import tempfile
import threading
import traceback

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

from adbtouch import Device, Recorder, Session, VectorizeSettings, Vectorizer, replay, simulate
from adbtouch.errors import AdbTouchError

from .geometry import CanvasView, place_paths

CANVAS_MARGIN = 40
IMAGE_TYPES = [("Images", "*.png *.jpg *.jpeg *.bmp *.webp"), ("All files", "*.*")]
SESSION_TYPES = [("AutoDraw recording", "*.json"), ("All files", "*.*")]


class App:
    """Main window. Owns the device connection shared by both tabs."""

    def __init__(self):
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("AutoDraw - draw, record and replay on Android")
        self.root.geometry("1280x860")
        self.root.minsize(1000, 700)

        self.device: Device | None = None
        self.vectorizer = Vectorizer()
        self.recorder: Recorder | None = None
        self.session: Session | None = None

        self.is_busy = False
        self.cancel_requested = False

        self.preview_image: Image.Image | None = None
        self.tk_image = None
        self.canvas_image_item = None
        self.background_image: Image.Image | None = None
        self.background_tk = None

        self.image_scale = 1.0
        self.image_pos = [0.0, 0.0]
        self.screen_size = (1080, 2400)
        self.phone_rect = (CANVAS_MARGIN, CANVAS_MARGIN, 300, 600)
        self._last_mouse = (0, 0)
        self._placed = False

        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_tabs()
        self.root.bind("<Configure>", self._on_window_configure)

    # ------------------------------------------------------------------- setup

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.root, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(header, text="AutoDraw", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, padx=(20, 16), pady=12
        )
        self.btn_connect = ctk.CTkButton(header, text="Connect device", width=140, command=self.connect)
        self.btn_connect.grid(row=0, column=1, padx=6, pady=12)
        self.btn_capture = ctk.CTkButton(
            header, text="Capture screen", width=140, fg_color="gray30", command=self.capture_screen
        )
        self.btn_capture.grid(row=0, column=2, padx=6, pady=12)
        self.lbl_status = ctk.CTkLabel(header, text="Disconnected", text_color="gray70")
        self.lbl_status.grid(row=0, column=3, padx=16, pady=12)

        self.progress = ctk.CTkProgressBar(header, width=220)
        self.progress.set(0)
        self.progress.grid(row=0, column=5, padx=20, pady=12, sticky="e")

    def _build_tabs(self) -> None:
        self.tabs = ctk.CTkTabview(self.root)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=16, pady=(8, 16))
        self.tab_draw = self.tabs.add("Draw image")
        self.tab_record = self.tabs.add("Record and replay")
        self._build_draw_tab()
        self._build_record_tab()

    def _build_draw_tab(self) -> None:
        tab = self.tab_draw
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        side = ctk.CTkScrollableFrame(tab, width=280, label_text="Drawing")
        side.grid(row=0, column=0, sticky="nsw", padx=(0, 12), pady=4)

        ctk.CTkButton(side, text="Load image", command=self.load_image).pack(fill="x", pady=(4, 6))
        ctk.CTkButton(side, text="Centre on screen", fg_color="gray30", command=self.center_image).pack(
            fill="x", pady=(0, 12)
        )

        ctk.CTkLabel(side, text="Edge sensitivity", anchor="w").pack(fill="x")
        self.slider_sensitivity = ctk.CTkSlider(side, from_=1, to=10, number_of_steps=9, command=self._on_setting_change)
        self.slider_sensitivity.set(5)
        self.slider_sensitivity.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(side, text="Detail", anchor="w").pack(fill="x")
        self.slider_detail = ctk.CTkSlider(side, from_=1, to=10, number_of_steps=9, command=self._on_setting_change)
        self.slider_detail.set(5)
        self.slider_detail.pack(fill="x", pady=(0, 10))

        self.chk_remove_bg = ctk.CTkCheckBox(side, text="Remove background (needs rembg)", command=self._on_setting_change)
        self.chk_remove_bg.pack(fill="x", pady=(0, 10))

        self.chk_pointer = ctk.CTkCheckBox(side, text="Show touches while drawing")
        self.chk_pointer.pack(fill="x", pady=(0, 12))

        self.lbl_speed_value = ctk.CTkLabel(side, text="Speed  1.0x", anchor="w")
        self.lbl_speed_value.pack(fill="x")
        self.slider_speed = ctk.CTkSlider(side, from_=-2, to=2, number_of_steps=16,
                                          command=self._on_speed_setting)
        self.slider_speed.set(0)
        self.slider_speed.pack(fill="x", pady=(0, 10))

        self.lbl_human_value = ctk.CTkLabel(side, text="Draw like a hand  off", anchor="w")
        self.lbl_human_value.pack(fill="x")
        self.slider_human = ctk.CTkSlider(side, from_=0, to=3, number_of_steps=12,
                                          command=self._on_human_setting)
        self.slider_human.set(0)
        self.slider_human.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(side, text="Calibration offset X / Y (px)", anchor="w").pack(fill="x")
        offsets = ctk.CTkFrame(side, fg_color="transparent")
        offsets.pack(fill="x", pady=(2, 12))
        self.entry_offset_x = ctk.CTkEntry(offsets, width=80, placeholder_text="0")
        self.entry_offset_x.pack(side="left", padx=(0, 8))
        self.entry_offset_y = ctk.CTkEntry(offsets, width=80, placeholder_text="0")
        self.entry_offset_y.pack(side="left")

        self.lbl_paths = ctk.CTkLabel(side, text="No image loaded", anchor="w", text_color="gray70")
        self.lbl_paths.pack(fill="x", pady=(0, 2))

        self.lbl_method = ctk.CTkLabel(side, text="", anchor="w", justify="left",
                                       wraplength=250, text_color="gray60")
        self.lbl_method.pack(fill="x", pady=(0, 12))

        self.btn_draw = ctk.CTkButton(side, text="START DRAWING", height=42, fg_color="#2e8b57", command=self.start_drawing)
        self.btn_draw.pack(fill="x", pady=(0, 6))
        ctk.CTkButton(side, text="Stop", fg_color="#a83232", command=self.cancel).pack(fill="x")

        self.canvas = tk.Canvas(tab, bg="#1a1a1a", highlightthickness=0)
        self.canvas.grid(row=0, column=1, sticky="nsew", pady=4)
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)
        self.canvas.bind("<Button-4>", self._on_mouse_wheel)
        self.canvas.bind("<Button-5>", self._on_mouse_wheel)

    def _build_record_tab(self) -> None:
        tab = self.tab_record
        tab.grid_columnconfigure(0, weight=1)

        intro = (
            "Record what you do on the phone, save it to a file, and replay it later.\n"
            "Useful for regression passes: capture the steps once, then run them on every build."
        )
        ctk.CTkLabel(tab, text=intro, justify="left", anchor="w", text_color="gray70").grid(
            row=0, column=0, sticky="ew", padx=16, pady=(16, 12)
        )

        capture = ctk.CTkFrame(tab)
        capture.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        capture.grid_columnconfigure(3, weight=1)

        self.btn_record = ctk.CTkButton(capture, text="Start recording", width=160, fg_color="#a83232", command=self.toggle_recording)
        self.btn_record.grid(row=0, column=0, padx=12, pady=14)
        self.lbl_record = ctk.CTkLabel(capture, text="Idle", text_color="gray70")
        self.lbl_record.grid(row=0, column=1, padx=12)
        ctk.CTkButton(capture, text="Save recording", width=150, command=self.save_session).grid(row=0, column=2, padx=8)
        ctk.CTkButton(capture, text="Open recording", width=150, fg_color="gray30", command=self.open_session).grid(
            row=0, column=3, padx=8, sticky="w"
        )

        playback = ctk.CTkFrame(tab)
        playback.grid(row=2, column=0, sticky="ew", padx=16, pady=8)
        playback.grid_columnconfigure(5, weight=1)

        ctk.CTkLabel(playback, text="Speed").grid(row=0, column=0, padx=(12, 6), pady=14)
        self.slider_speed = ctk.CTkSlider(playback, from_=0.25, to=4.0, number_of_steps=15, width=180, command=self._on_speed_change)
        self.slider_speed.set(1.0)
        self.slider_speed.grid(row=0, column=1, padx=6)
        self.lbl_speed = ctk.CTkLabel(playback, text="1.00x", width=60)
        self.lbl_speed.grid(row=0, column=2, padx=6)

        ctk.CTkLabel(playback, text="Repeat").grid(row=0, column=3, padx=(24, 6))
        self.entry_repeat = ctk.CTkEntry(playback, width=70, placeholder_text="1")
        self.entry_repeat.grid(row=0, column=4, padx=6)

        self.btn_replay = ctk.CTkButton(playback, text="Replay", width=140, fg_color="#2e8b57", command=self.start_replay)
        self.btn_replay.grid(row=0, column=5, padx=12, sticky="e")

        self.txt_session = ctk.CTkTextbox(tab, height=260)
        self.txt_session.grid(row=3, column=0, sticky="nsew", padx=16, pady=(8, 16))
        tab.grid_rowconfigure(3, weight=1)
        self._describe_session()

    # ------------------------------------------------------------------ helpers

    def set_status(self, text: str, colour: str = "gray70") -> None:
        self.root.after(0, lambda: self.lbl_status.configure(text=text, text_color=colour))

    def set_progress(self, fraction: float) -> None:
        self.root.after(0, lambda: self.progress.set(max(0.0, min(1.0, fraction))))

    def require_device(self) -> Device | None:
        if self.device is None:
            self.set_status("Connect a device first", "orange")
        return self.device

    def _run_background(self, target, *args) -> None:
        if self.is_busy:
            self.set_status("Another operation is still running", "orange")
            return
        self.is_busy = True
        self.cancel_requested = False

        def wrapper():
            try:
                target(*args)
            except AdbTouchError as exc:
                self.set_status(str(exc), "orange")
            except Exception as exc:  # pragma: no cover - surfaced in the UI
                traceback.print_exc()
                self.set_status(f"Error: {exc}", "red")
            finally:
                self.is_busy = False
                self.set_progress(0)

        threading.Thread(target=wrapper, daemon=True).start()

    def cancel(self) -> None:
        self.cancel_requested = True
        self.set_status("Stopping...", "orange")

    def _should_continue(self) -> bool:
        return not self.cancel_requested

    def _int_entry(self, entry, default: int = 0) -> int:
        try:
            return int(entry.get().strip() or default)
        except (ValueError, AttributeError):
            return default

    # --------------------------------------------------------------- connection

    def connect(self) -> None:
        try:
            self.device = Device()
        except AdbTouchError as exc:
            self.device = None
            self.set_status(str(exc), "orange")
            return
        try:
            self.screen_size = self.device.screen_size
        except AdbTouchError as exc:
            self.set_status(str(exc), "orange")
            return
        detail = f"{self.device.serial} - {self.screen_size[0]}x{self.screen_size[1]}"
        try:
            touch = self.device.touch_device
            detail += f" - touch {touch.path}"
        except AdbTouchError:
            detail += " - no raw touch device (slow mode)"
        self.set_status(detail, "#4caf50")
        self._redraw_phone_rect()

    def capture_screen(self) -> None:
        if not self.require_device():
            return

        def work():
            self.set_status("Capturing screen...", "yellow")
            path = os.path.join(tempfile.gettempdir(), "autodraw_screen.png")
            self.device.screenshot(path)
            self.background_image = Image.open(path).copy()
            self.set_status("Screen captured", "#4caf50")
            self.root.after(0, self._redraw_phone_rect)

        self._run_background(work)

    # -------------------------------------------------------------------- canvas

    def _on_window_configure(self, event=None) -> None:
        if getattr(event, "widget", None) is self.root:
            self.root.after_idle(self._redraw_phone_rect)

    def _current_view(self) -> CanvasView:
        x, y, width, height = self.phone_rect
        return CanvasView(origin=(x, y), size=(width, height), screen=self.screen_size)

    def _redraw_phone_rect(self) -> None:
        canvas_w = max(self.canvas.winfo_width(), 200)
        canvas_h = max(self.canvas.winfo_height(), 200)
        screen_w, screen_h = self.screen_size

        scale = min((canvas_w - 2 * CANVAS_MARGIN) / screen_w, (canvas_h - 2 * CANVAS_MARGIN) / screen_h)
        scale = max(scale, 0.01)
        width = int(screen_w * scale)
        height = int(screen_h * scale)
        x = (canvas_w - width) // 2
        y = (canvas_h - height) // 2
        self.phone_rect = (x, y, width, height)

        self.canvas.delete("phone")
        if self.background_image is not None:
            self.background_tk = ImageTk.PhotoImage(self.background_image.resize((width, height), Image.LANCZOS))
            self.canvas.create_image(x, y, image=self.background_tk, anchor="nw", tags="phone")
        self.canvas.create_rectangle(x, y, x + width, y + height, outline="#5a5a5a", width=2, tags="phone")
        self.canvas.create_text(
            x, y - 12, text=f"{screen_w} x {screen_h}", fill="#8a8a8a", anchor="nw", tags="phone"
        )
        self.canvas.tag_lower("phone")

        if not self._placed and self.preview_image is not None:
            self.center_image()

    def _on_mouse_down(self, event) -> None:
        self._last_mouse = (event.x, event.y)

    def _on_mouse_drag(self, event) -> None:
        dx = event.x - self._last_mouse[0]
        dy = event.y - self._last_mouse[1]
        if self.canvas_image_item is not None:
            self.canvas.move(self.canvas_image_item, dx, dy)
            self.image_pos[0] += dx
            self.image_pos[1] += dy
        self._last_mouse = (event.x, event.y)

    def _on_mouse_wheel(self, event) -> None:
        if self.preview_image is None:
            return
        delta = getattr(event, "delta", 0)
        if getattr(event, "num", None) == 5 or delta < 0:
            factor = 0.9
        elif getattr(event, "num", None) == 4 or delta > 0:
            factor = 1.1
        else:
            return
        new_scale = self.image_scale * factor
        if not 0.02 <= new_scale <= 20:
            return
        self.image_pos[0] = event.x - (event.x - self.image_pos[0]) * factor
        self.image_pos[1] = event.y - (event.y - self.image_pos[1]) * factor
        self.image_scale = new_scale
        self._redraw_preview()

    def _redraw_preview(self) -> None:
        if self.preview_image is None:
            return
        width = max(1, int(self.preview_image.width * self.image_scale))
        height = max(1, int(self.preview_image.height * self.image_scale))
        self.tk_image = ImageTk.PhotoImage(self.preview_image.resize((width, height), Image.NEAREST))
        if self.canvas_image_item is not None:
            self.canvas.delete(self.canvas_image_item)
        self.canvas_image_item = self.canvas.create_image(
            self.image_pos[0], self.image_pos[1], image=self.tk_image, anchor="nw", tags="preview"
        )

    def center_image(self) -> None:
        if self.preview_image is None:
            return
        x, y, width, height = self.phone_rect
        self.image_scale = min(
            width / self.preview_image.width, height / self.preview_image.height
        ) * 0.9
        shown_w = self.preview_image.width * self.image_scale
        shown_h = self.preview_image.height * self.image_scale
        self.image_pos = [x + (width - shown_w) / 2, y + (height - shown_h) / 2]
        self._placed = True
        self._redraw_preview()

    # ------------------------------------------------------------------ drawing

    def _settings(self) -> VectorizeSettings:
        return VectorizeSettings.from_sliders(
            self.slider_sensitivity.get(),
            self.slider_detail.get(),
            remove_background=bool(self.chk_remove_bg.get()),
        )

    @property
    def draw_speed(self) -> float:
        """The speed slider, as a multiplier. It is exponential: the useful
        range runs from a quarter speed to four times, and a linear slider
        spends most of its travel in places nobody wants."""
        return float(2 ** self.slider_speed.get())

    def _on_speed_setting(self, _value=None) -> None:
        self.lbl_speed_value.configure(text=f"Speed  {self.draw_speed:.2f}x")
        self._refresh_estimate()

    def _on_human_setting(self, _value=None) -> None:
        amount = float(self.slider_human.get())
        text = "off" if amount <= 0 else f"{amount:.2f}"
        self.lbl_human_value.configure(text=f"Draw like a hand  {text}")
        self._refresh_estimate()

    def _refresh_estimate(self) -> None:
        """Say which injection path will be used, and how long it will take.

        On a device that refuses raw touch events the drawing is minutes rather
        than seconds, and a progress bar creeping along with no explanation is
        indistinguishable from one that has hung.
        """
        paths = self.vectorizer.paths
        if not paths:
            self.lbl_method.configure(text="")
            return
        human = float(self.slider_human.get())
        if human > 0:
            # The simulation changes the point count - that is the velocity
            # profile - so the estimate has to be made on what will be sent.
            paths = simulate(paths, human, seed=0)
        if self.device is None:
            self.lbl_method.configure(text="Connect a device to estimate the time.")
            return

        try:
            raw = self.device.supports_raw_touch
            seconds = self.device.estimate_duration(
                paths, method="raw" if raw else "input", speed=self.draw_speed)
        except AdbTouchError as exc:
            self.lbl_method.configure(text=str(exc))
            return

        minutes, secs = divmod(int(seconds + 0.5), 60)
        span = f"{minutes} min {secs} s" if minutes else f"{secs} s"
        if raw:
            self.lbl_method.configure(
                text=f"Raw touch events, about {span}.", text_color="gray60")
        else:
            self.lbl_method.configure(
                text=(f"This device refuses raw touch events, so drawing goes through "
                      f"Android's own input injection: about {span}. Lower Detail to "
                      f"cut that down."),
                text_color="#c9a227")

    def _on_setting_change(self, _value=None) -> None:
        if self.vectorizer.original_image is not None:
            self.refresh_preview()

    def load_image(self) -> None:
        path = filedialog.askopenfilename(filetypes=IMAGE_TYPES)
        if not path:
            return
        try:
            self.vectorizer.load_image(path)
        except ValueError as exc:
            messagebox.showerror("AutoDraw", str(exc))
            return
        self._placed = False
        self.refresh_preview()

    def refresh_preview(self) -> None:
        settings = self._settings()

        def work():
            self.set_status("Processing image...", "yellow")
            preview, paths = self.vectorizer.process(settings)
            points = sum(len(p) for p in paths)

            def apply():
                self.preview_image = preview
                self.lbl_paths.configure(text=f"{len(paths)} strokes, {points} points")
                self._refresh_estimate()
                if not self._placed:
                    self.center_image()
                else:
                    self._redraw_preview()
                self.set_status("Ready", "#4caf50")

            self.root.after(0, apply)

        self._run_background(work)

    def start_drawing(self) -> None:
        if not self.require_device() or self.preview_image is None:
            if self.preview_image is None:
                self.set_status("Load an image first", "orange")
            return

        settings = self._settings()
        view = self._current_view()
        origin = tuple(self.canvas.coords(self.canvas_image_item) or self.image_pos)
        scale = self.image_scale
        offset = (self._int_entry(self.entry_offset_x), self._int_entry(self.entry_offset_y))
        show_touches = bool(self.chk_pointer.get())
        speed = self.draw_speed
        human = float(self.slider_human.get())

        def work():
            self.set_status("Building paths...", "yellow")
            _, paths = self.vectorizer.process(settings)
            placed = place_paths(paths, view, origin, scale, offset)
            if not placed:
                self.set_status("Nothing to draw at this position", "orange")
                return

            raw = self.device.supports_raw_touch
            method = "raw" if raw else "input"
            costed = simulate(placed, human, seed=0) if human > 0 else placed
            seconds = self.device.estimate_duration(costed, method=method, speed=speed)
            minutes, secs = divmod(int(seconds + 0.5), 60)
            span = f"{minutes}m {secs}s" if minutes else f"{secs}s"
            how = "raw events" if raw else "input injection (slow)"

            if show_touches:
                self.device.set_pointer_location(True)
            try:
                self.set_status(f"Drawing {len(placed)} strokes via {how}, about {span}...",
                                "yellow")
                self.device.draw_paths(
                    placed,
                    method=method,
                    speed=speed,
                    human=human,
                    progress=lambda done, total: self.set_progress(done / max(total, 1)),
                    should_continue=self._should_continue,
                )
            finally:
                if show_touches:
                    self.device.set_pointer_location(False)
            self.set_status("Stopped" if self.cancel_requested else "Drawing finished", "#4caf50")

        self._run_background(work)

    # ------------------------------------------------------------ record/replay

    def toggle_recording(self) -> None:
        if self.recorder is not None and self.recorder.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        if not self.require_device():
            return
        self.recorder = Recorder(self.device)
        try:
            self.recorder.start()
        except AdbTouchError as exc:
            self.set_status(str(exc), "orange")
            return
        self.btn_record.configure(text="Stop recording", fg_color="#c25a00")
        self.set_status("Recording - interact with the phone", "#c25a00")
        self._poll_recording()

    def _poll_recording(self) -> None:
        if self.recorder is None or not self.recorder.is_recording:
            return
        self.lbl_record.configure(text=f"Recording... {self.recorder.event_count} events", text_color="#c25a00")
        self.root.after(250, self._poll_recording)

    def _stop_recording(self) -> None:
        if self.recorder is None:
            return
        self.session = self.recorder.stop()
        error = self.recorder.error
        self.recorder = None
        self.btn_record.configure(text="Start recording", fg_color="#a83232")
        if error:
            self.set_status(f"Recorder error: {error}", "red")
        else:
            self.set_status("Recording stopped", "#4caf50")
        self._describe_session()

    def _describe_session(self) -> None:
        box = self.txt_session
        box.configure(state="normal")
        box.delete("1.0", "end")
        if self.session is None or not self.session.events:
            box.insert("1.0", "No recording loaded.\n\nPress 'Start recording', touch the phone, then stop.")
            self.lbl_record.configure(text="Idle", text_color="gray70")
        else:
            session = self.session
            lines = [
                f"Events      : {len(session.events)}",
                f"Duration    : {session.duration:.2f} s",
                f"Recorded    : {session.created_at}",
                f"Device      : {session.device_serial or 'unknown'}",
                f"Screen      : {session.screen_size or 'unknown'}",
                f"Input paths : {', '.join(session.devices) or 'none'}",
                "",
                "First events (time, device, type, code, value):",
            ]
            for event in session.events[:25]:
                lines.append(f"  {event.t:8.3f}  {event.device}  {event.type:>3} {event.code:>4} {event.value}")
            if len(session.events) > 25:
                lines.append(f"  ... {len(session.events) - 25} more")
            box.insert("1.0", "\n".join(lines))
            self.lbl_record.configure(
                text=f"{len(session.events)} events / {session.duration:.1f}s", text_color="#4caf50"
            )
        box.configure(state="disabled")

    def save_session(self) -> None:
        if self.session is None or not self.session.events:
            self.set_status("Nothing recorded yet", "orange")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=SESSION_TYPES)
        if not path:
            return
        self.session.save(path)
        self.set_status(f"Saved to {os.path.basename(path)}", "#4caf50")

    def open_session(self) -> None:
        path = filedialog.askopenfilename(filetypes=SESSION_TYPES)
        if not path:
            return
        try:
            self.session = Session.load(path)
        except (ValueError, OSError) as exc:
            messagebox.showerror("AutoDraw", f"Could not open the recording:\n{exc}")
            return
        self.set_status(f"Loaded {os.path.basename(path)}", "#4caf50")
        self._describe_session()

    def _on_speed_change(self, value) -> None:
        self.lbl_speed.configure(text=f"{float(value):.2f}x")

    def start_replay(self) -> None:
        if not self.require_device():
            return
        if self.session is None or not self.session.events:
            self.set_status("Load or record something first", "orange")
            return
        speed = float(self.slider_speed.get())
        repeat = max(1, self._int_entry(self.entry_repeat, 1))

        def work():
            self.set_status(f"Replaying at {speed:.2f}x...", "yellow")
            try:
                replay(
                    self.device,
                    self.session,
                    speed=speed,
                    repeat=repeat,
                    progress=lambda done, total: self.set_progress(done / max(total, 1)),
                    should_continue=self._should_continue,
                )
            except ValueError as exc:
                self.set_status(str(exc), "orange")
                return
            self.set_status("Stopped" if self.cancel_requested else "Replay finished", "#4caf50")

        self._run_background(work)

    # --------------------------------------------------------------------- main

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    App().run()


if __name__ == "__main__":
    main()
