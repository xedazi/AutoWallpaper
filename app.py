import json
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

import customtkinter as ctk
from PIL import Image

APP_NAME = "AutoWallpaper"
APP_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / APP_NAME
SETTINGS_FILE = APP_DIR / "settings.json"
SUPPORTED = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

DEFAULTS = {
    "wallpapers": [],
    "queue_index": 0,
    "interval_minutes": 30,
    "repeat_queue": True,
    "auto_start_rotation": True,
    "startup_enabled": True,
    "source_image": "",
}

def load_settings():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        settings = DEFAULTS.copy()
        settings.update(data if isinstance(data, dict) else {})
        if not isinstance(settings.get("wallpapers"), list):
            settings["wallpapers"] = []
        return settings
    except (OSError, json.JSONDecodeError):
        return DEFAULTS.copy()

def save_settings(settings):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")

def set_windows_wallpaper(path):
    if os.name != "nt":
        raise OSError("Установка обоев поддерживается только в Windows.")
    import ctypes
    SPI_SETDESKWALLPAPER = 20
    SPIF_UPDATEINIFILE = 0x01
    SPIF_SENDCHANGE = 0x02
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, str(Path(path).resolve()),
        SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
    )
    if not ok:
        raise ctypes.WinError()

def enable_startup(enabled):
    if os.name != "nt":
        return
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                exe = sys.executable
                if getattr(sys, "frozen", False):
                    command = f'"{exe}" --background'
                else:
                    script = str(Path(__file__).resolve())
                    command = f'"{exe}" "{script}" --background'
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
    except OSError:
        pass

class AutoWallpaperApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.title("AutoWallpaper")
        self.geometry("760x650")
        self.minsize(680, 590)
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.interval_var = tk.StringVar(value=str(self.settings.get("interval_minutes", 30)))
        self.repeat_var = tk.BooleanVar(value=bool(self.settings.get("repeat_queue", True)))
        self.autostart_var = tk.BooleanVar(value=bool(self.settings.get("auto_start_rotation", True)))
        self.startup_var = tk.BooleanVar(value=bool(self.settings.get("startup_enabled", True)))
        self.status_var = tk.StringVar(value="Готово")
        self.timer_id = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="AutoWallpaper", font=ctk.CTkFont(size=28, weight="bold")).grid(
            row=0, column=0, padx=20, pady=(18, 2), sticky="w")
        ctk.CTkLabel(self, text="Очередь обоев с автоматической сменой", text_color=("gray35", "gray70")).grid(
            row=1, column=0, padx=20, pady=(0, 14), sticky="w")

        queue_frame = ctk.CTkFrame(self)
        queue_frame.grid(row=2, column=0, padx=20, pady=4, sticky="nsew")
        queue_frame.grid_columnconfigure(0, weight=1)
        queue_frame.grid_rowconfigure(0, weight=1)
        self.queue_list = tk.Listbox(queue_frame, height=10, selectmode=tk.SINGLE, font=("Segoe UI", 10),
                                     activestyle="dotbox", exportselection=False)
        self.queue_list.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")
        scroll = ctk.CTkScrollbar(queue_frame, command=self.queue_list.yview)
        scroll.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="ns")
        self.queue_list.configure(yscrollcommand=scroll.set)

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=3, column=0, padx=20, pady=8, sticky="ew")
        for i in range(6):
            controls.grid_columnconfigure(i, weight=1)
        ctk.CTkButton(controls, text="＋ Добавить", command=self.add_files).grid(row=0, column=0, padx=3, sticky="ew")
        ctk.CTkButton(controls, text="↑ Вверх", width=85, command=lambda: self.move_item(-1)).grid(row=0, column=1, padx=3, sticky="ew")
        ctk.CTkButton(controls, text="↓ Вниз", width=85, command=lambda: self.move_item(1)).grid(row=0, column=2, padx=3, sticky="ew")
        ctk.CTkButton(controls, text="Удалить", command=self.remove_item).grid(row=0, column=3, padx=3, sticky="ew")
        ctk.CTkButton(controls, text="Применить", command=self.apply_selected).grid(row=0, column=4, padx=3, sticky="ew")
        ctk.CTkButton(controls, text="Следующие", command=self.apply_next).grid(row=0, column=5, padx=3, sticky="ew")

        settings_frame = ctk.CTkFrame(self)
        settings_frame.grid(row=4, column=0, padx=20, pady=8, sticky="ew")
        settings_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(settings_frame, text="Интервал смены (минуты):").grid(row=0, column=0, padx=12, pady=10, sticky="w")
        self.interval_entry = ctk.CTkEntry(settings_frame, textvariable=self.interval_var, width=110)
        self.interval_entry.grid(row=0, column=1, padx=8, pady=10, sticky="w")
        ctk.CTkButton(settings_frame, text="Сохранить настройки", command=self.save_preferences).grid(
            row=0, column=2, padx=12, pady=10)
        ctk.CTkCheckBox(settings_frame, text="Повторять очередь по кругу", variable=self.repeat_var,
                        command=self.save_preferences).grid(row=1, column=0, columnspan=2, padx=12, pady=7, sticky="w")
        ctk.CTkCheckBox(settings_frame, text="Автоматически менять обои", variable=self.autostart_var,
                        command=self.save_preferences).grid(row=2, column=0, columnspan=2, padx=12, pady=7, sticky="w")
        ctk.CTkCheckBox(settings_frame, text="Запускать вместе с Windows", variable=self.startup_var,
                        command=self.save_preferences).grid(row=3, column=0, columnspan=2, padx=12, pady=(7, 12), sticky="w")

        self.status_label = ctk.CTkLabel(self, textvariable=self.status_var, anchor="w")
        self.status_label.grid(row=5, column=0, padx=22, pady=(3, 14), sticky="ew")

        self.refresh_queue()
        self.save_preferences(silent=True)
        if "--background" in sys.argv:
            self.withdraw()
            self.after(1800, self._background_start)
        else:
            self.protocol("WM_DELETE_WINDOW", self.on_close)
            self.after(1000, self._schedule_next)

    def refresh_queue(self, select_index=None):
        self.queue_list.delete(0, tk.END)
        for i, path in enumerate(self.settings.get("wallpapers", [])):
            self.queue_list.insert(tk.END, f"{i + 1}. {Path(path).name}")
        if self.settings.get("wallpapers"):
            idx = select_index
            if idx is None:
                idx = min(max(0, int(self.settings.get("queue_index", 0))), len(self.settings["wallpapers"]) - 1)
            self.queue_list.selection_set(idx)
            self.queue_list.activate(idx)

    def selected_index(self):
        selection = self.queue_list.curselection()
        return int(selection[0]) if selection else None

    def add_files(self):
        paths = filedialog.askopenfilenames(title="Выберите обои", filetypes=[
            ("Изображения", "*.jpg *.jpeg *.png *.bmp *.webp"), ("Все файлы", "*.*")])
        added = 0
        for path in paths:
            if Path(path).suffix.lower() in SUPPORTED and path not in self.settings["wallpapers"]:
                self.settings["wallpapers"].append(path)
                added += 1
        self.refresh_queue(len(self.settings["wallpapers"]) - 1 if added else None)
        self.save_preferences(silent=True)
        self.status_var.set(f"Добавлено файлов: {added}" if added else "Очередь не изменилась")

    def move_item(self, delta):
        idx = self.selected_index()
        items = self.settings["wallpapers"]
        if idx is None or not (0 <= idx + delta < len(items)):
            return
        items[idx], items[idx + delta] = items[idx + delta], items[idx]
        self.refresh_queue(idx + delta)
        self.save_preferences(silent=True)

    def remove_item(self):
        idx = self.selected_index()
        if idx is None:
            return
        items = self.settings["wallpapers"]
        items.pop(idx)
        self.settings["queue_index"] = min(int(self.settings.get("queue_index", 0)), max(0, len(items) - 1))
        self.refresh_queue(min(idx, max(0, len(items) - 1)) if items else None)
        self.save_preferences(silent=True)

    def apply_path(self, path, announce=True):
        if not Path(path).is_file():
            self.status_var.set(f"Файл не найден: {path}")
            return False
        try:
            set_windows_wallpaper(path)
            self.settings["source_image"] = path
            self.save_preferences(silent=True)
            if announce:
                self.status_var.set(f"Установлены обои: {Path(path).name}")
            return True
        except Exception as exc:
            self.status_var.set(f"Ошибка установки: {exc}")
            return False

    def apply_selected(self):
        idx = self.selected_index()
        if idx is None:
            self.status_var.set("Сначала добавь обои в очередь")
            return
        self.settings["queue_index"] = idx
        if self.apply_path(self.settings["wallpapers"][idx]):
            self.save_preferences(silent=True)
            self._schedule_next()

    def apply_next(self):
        items = self.settings.get("wallpapers", [])
        if not items:
            self.status_var.set("Сначала добавь обои в очередь")
            return
        idx = int(self.settings.get("queue_index", -1)) + 1
        if idx >= len(items):
            if self.repeat_var.get():
                idx = 0
            else:
                self.status_var.set("Очередь закончилась")
                return
        self.settings["queue_index"] = idx
        self.refresh_queue(idx)
        if self.apply_path(items[idx]):
            self.save_preferences(silent=True)
            self._schedule_next()

    def save_preferences(self, silent=False):
        try:
            interval = int(self.interval_var.get().strip())
            if interval < 1 or interval > 10080:
                raise ValueError
        except ValueError:
            if not silent:
                messagebox.showerror("Неверный интервал", "Укажи целое число от 1 до 10080 минут.")
            return False
        self.settings["interval_minutes"] = interval
        self.settings["repeat_queue"] = bool(self.repeat_var.get())
        self.settings["auto_start_rotation"] = bool(self.autostart_var.get())
        self.settings["startup_enabled"] = bool(self.startup_var.get())
        save_settings(self.settings)
        enable_startup(self.settings["startup_enabled"])
        self._schedule_next()
        if not silent:
            self.status_var.set(f"Настройки сохранены. Интервал: {interval} мин.")
        return True

    def _schedule_next(self):
        if self.timer_id:
            try:
                self.after_cancel(self.timer_id)
            except tk.TclError:
                pass
            self.timer_id = None
        if self.autostart_var.get() and self.settings.get("wallpapers"):
            try:
                minutes = max(1, int(self.interval_var.get()))
            except ValueError:
                minutes = 30
            self.timer_id = self.after(minutes * 60 * 1000, self._timer_tick)

    def _timer_tick(self):
        self.timer_id = None
        self.apply_next()
        self._schedule_next()

    def _background_start(self):
        if self.settings.get("auto_start_rotation") and self.settings.get("wallpapers"):
            # Apply the current queue item at login, then begin the rotation timer.
            idx = int(self.settings.get("queue_index", 0)) % len(self.settings["wallpapers"])
            self.settings["queue_index"] = idx
            self.refresh_queue(idx)
            self.apply_path(self.settings["wallpapers"][idx])
            self.save_preferences(silent=True)
            self._schedule_next()
        else:
            self._schedule_next()

    def on_close(self):
        self.save_preferences(silent=True)
        self.destroy()

if __name__ == "__main__":
    if "--apply-only" in sys.argv:
        settings = load_settings()
        items = settings.get("wallpapers", [])
        if items:
            idx = int(settings.get("queue_index", 0)) % len(items)
            try:
                set_windows_wallpaper(items[idx])
            except Exception:
                pass
        elif settings.get("source_image") and Path(settings["source_image"]).is_file():
            try:
                set_windows_wallpaper(settings["source_image"])
            except Exception:
                pass
    else:
        app = AutoWallpaperApp()
        app.mainloop()
