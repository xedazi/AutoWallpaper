import json
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageOps

APP_NAME = "AutoWallpaper"
APP_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / APP_NAME
SETTINGS_FILE = APP_DIR / "settings.json"
CACHE_DIR = APP_DIR / "wallpaper_cache"
SUPPORTED = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULTS = {
    "wallpapers": [],
    "queue_index": 0,
    "interval_minutes": 30,
    "repeat_queue": True,
    "auto_start_rotation": True,
    "startup_enabled": False,
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
    SETTINGS_FILE.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def make_windows_bmp(source_path):
    """Convert source image to a BMP file for reliable Windows 7 wallpaper setting."""
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(f"Файл не найден: {source}")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = CACHE_DIR / (source.stem + "_wallpaper.bmp")
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.save(target, format="BMP")
    return target


def set_windows_wallpaper(path):
    if os.name != "nt":
        raise OSError("Установка обоев поддерживается только в Windows.")
    import ctypes
    bmp_path = make_windows_bmp(path)
    SPI_SETDESKWALLPAPER = 20
    SPIF_UPDATEINIFILE = 0x01
    SPIF_SENDCHANGE = 0x02
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, str(bmp_path.resolve()),
        SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
    )
    if not ok:
        raise ctypes.WinError()
    return bmp_path


def enable_startup(enabled):
    if os.name != "nt":
        return
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                exe = sys.executable
                if getattr(sys, "frozen", False):
                    command = f'"{exe}" --background'
                else:
                    command = f'"{exe}" "{Path(__file__).resolve()}" --background'
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
        self.geometry("900x700")
        self.minsize(760, 620)
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.interval_var = tk.StringVar(
            value=str(self.settings.get("interval_minutes", 30))
        )
        self.repeat_var = tk.BooleanVar(
            value=bool(self.settings.get("repeat_queue", True))
        )
        self.autostart_var = tk.BooleanVar(
            value=bool(self.settings.get("auto_start_rotation", True))
        )
        self.startup_var = tk.BooleanVar(
            value=bool(self.settings.get("startup_enabled", False))
        )
        self.status_var = tk.StringVar(value="Готово")
        self.timer_id = None
        self.preview_image = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self, text="AutoWallpaper",
            font=ctk.CTkFont(size=28, weight="bold")
        ).grid(row=0, column=0, padx=20, pady=(18, 2), sticky="w")
        ctk.CTkLabel(
            self, text="Очередь обоев с предпросмотром и автоматической сменой",
            text_color=("gray35", "gray70")
        ).grid(row=1, column=0, padx=20, pady=(0, 14), sticky="w")

        main_frame = ctk.CTkFrame(self)
        main_frame.grid(row=2, column=0, padx=20, pady=4, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=3)
        main_frame.grid_columnconfigure(1, weight=4)
        main_frame.grid_rowconfigure(0, weight=1)

        queue_frame = ctk.CTkFrame(main_frame)
        queue_frame.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")
        queue_frame.grid_columnconfigure(0, weight=1)
        queue_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(queue_frame, text="Очередь обоев",
                     font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, padx=10, pady=(10, 4), sticky="w")
        self.queue_list = tk.Listbox(
            queue_frame, height=10, selectmode=tk.SINGLE,
            font=("Segoe UI", 10), activestyle="dotbox",
            exportselection=False
        )
        self.queue_list.grid(row=1, column=0, padx=(10, 4), pady=8, sticky="nsew")
        scroll = ctk.CTkScrollbar(queue_frame, command=self.queue_list.yview)
        scroll.grid(row=1, column=1, padx=(0, 10), pady=8, sticky="ns")
        self.queue_list.configure(yscrollcommand=scroll.set)
        self.queue_list.bind("<<ListboxSelect>>", self.on_queue_select)

        preview_frame = ctk.CTkFrame(main_frame)
        preview_frame.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")
        preview_frame.grid_columnconfigure(0, weight=1)
        preview_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(preview_frame, text="Предпросмотр",
                     font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, padx=10, pady=(10, 4))
        self.preview_label = ctk.CTkLabel(
            preview_frame, text="Добавь изображения,\nчтобы увидеть предпросмотр",
            fg_color=("gray90", "gray17"), corner_radius=8
        )
        self.preview_label.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.preview_name = ctk.CTkLabel(preview_frame, text="Изображение не выбрано")
        self.preview_name.grid(row=2, column=0, padx=10, pady=(0, 10))

        controls = ctk.CTkFrame(self)
        controls.grid(row=3, column=0, padx=20, pady=8, sticky="ew")
        for i in range(6):
            controls.grid_columnconfigure(i, weight=1)
        ctk.CTkButton(controls, text="＋ Добавить", command=self.add_files).grid(
            row=0, column=0, padx=3, pady=8, sticky="ew")
        ctk.CTkButton(controls, text="↑ Вверх", command=lambda: self.move_item(-1)).grid(
            row=0, column=1, padx=3, pady=8, sticky="ew")
        ctk.CTkButton(controls, text="↓ Вниз", command=lambda: self.move_item(1)).grid(
            row=0, column=2, padx=3, pady=8, sticky="ew")
        ctk.CTkButton(controls, text="Удалить", command=self.remove_item).grid(
            row=0, column=3, padx=3, pady=8, sticky="ew")
        ctk.CTkButton(controls, text="Применить", command=self.apply_selected).grid(
            row=0, column=4, padx=3, pady=8, sticky="ew")
        ctk.CTkButton(controls, text="Следующие", command=self.apply_next).grid(
            row=0, column=5, padx=3, pady=8, sticky="ew")

        settings_frame = ctk.CTkFrame(self)
        settings_frame.grid(row=4, column=0, padx=20, pady=8, sticky="ew")
        settings_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(settings_frame, text="Интервал смены (минуты):").grid(
            row=0, column=0, padx=12, pady=10, sticky="w")
        ctk.CTkEntry(settings_frame, textvariable=self.interval_var, width=110).grid(
            row=0, column=1, padx=8, pady=10, sticky="w")
        ctk.CTkButton(settings_frame, text="Сохранить настройки",
                      command=self.save_preferences).grid(
            row=0, column=2, padx=12, pady=10)
        ctk.CTkCheckBox(settings_frame, text="Повторять очередь по кругу",
                        variable=self.repeat_var, command=self.save_preferences).grid(
            row=1, column=0, columnspan=2, padx=12, pady=7, sticky="w")
        ctk.CTkCheckBox(settings_frame, text="Автоматически менять обои",
                        variable=self.autostart_var, command=self.save_preferences).grid(
            row=2, column=0, columnspan=2, padx=12, pady=7, sticky="w")
        ctk.CTkCheckBox(settings_frame, text="Запускать вместе с Windows",
                        variable=self.startup_var, command=self.save_preferences).grid(
            row=3, column=0, columnspan=2, padx=12, pady=(7, 12), sticky="w")

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
        items = self.settings.get("wallpapers", [])
        for i, path in enumerate(items):
            self.queue_list.insert(tk.END, f"{i + 1}. {Path(path).name}")
        if items:
            idx = select_index
            if idx is None:
                idx = min(max(0, int(self.settings.get("queue_index", 0))), len(items) - 1)
            self.queue_list.selection_clear(0, tk.END)
            self.queue_list.selection_set(idx)
            self.queue_list.activate(idx)
            self.show_preview(items[idx])
        else:
            self.preview_label.configure(image=None, text="Добавь изображения,\nчтобы увидеть предпросмотр")
            self.preview_name.configure(text="Изображение не выбрано")
            self.preview_image = None

    def selected_index(self):
        selection = self.queue_list.curselection()
        return int(selection[0]) if selection else None

    def on_queue_select(self, _event=None):
        idx = self.selected_index()
        if idx is not None and idx < len(self.settings.get("wallpapers", [])):
            self.show_preview(self.settings["wallpapers"][idx])

    def show_preview(self, path):
        try:
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                image.thumbnail((420, 320), Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS)
                self.preview_image = ctk.CTkImage(
                    light_image=image, dark_image=image, size=image.size
                )
            self.preview_label.configure(image=self.preview_image, text="")
            self.preview_name.configure(text=Path(path).name)
        except Exception as exc:
            self.preview_image = None
            self.preview_label.configure(image=None, text="Не удалось открыть изображение")
            self.preview_name.configure(text=str(exc))

    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Выберите обои",
            filetypes=[("Изображения", "*.jpg *.jpeg *.png *.bmp *.webp"),
                       ("Все файлы", "*.*")]
        )
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
        self.settings["wallpapers"].pop(idx)
        self.settings["queue_index"] = min(
            int(self.settings.get("queue_index", 0)),
            max(0, len(self.settings["wallpapers"]) - 1)
        )
        self.refresh_queue(min(idx, max(0, len(self.settings["wallpapers"]) - 1))
                           if self.settings["wallpapers"] else None)
        self.save_preferences(silent=True)

    def apply_path(self, path, announce=True):
        if not Path(path).is_file():
            self.status_var.set(f"Файл не найден: {path}")
            return False
        try:
            bmp_path = set_windows_wallpaper(path)
            self.settings["source_image"] = path
            self.save_preferences(self.settings)
            if announce:
                self.status_var.set(f"Обои установлены: {Path(path).name}")
            return True
        except Exception as exc:
            self.status_var.set(f"Ошибка установки: {exc}")
            if announce:
                messagebox.showerror("Не удалось установить обои", str(exc))
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
                messagebox.showerror("Неверный интервал",
                                     "Укажи целое число от 1 до 10080 минут.")
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
        items = self.settings.get("wallpapers", [])
        if self.settings.get("auto_start_rotation") and items:
            idx = int(self.settings.get("queue_index", 0)) % len(items)
            self.settings["queue_index"] = idx
            self.refresh_queue(idx)
            self.apply_path(items[idx], announce=False)
            self.save_preferences(silent=True)
        self._schedule_next()

    def on_close(self):
        self.save_preferences(silent=True)
        self.destroy()


if __name__ == "__main__":
    if "--apply-only" in sys.argv:
        settings = load_settings()
        items = settings.get("wallpapers", [])
        path = None
        if items:
            idx = int(settings.get("queue_index", 0)) % len(items)
            path = items[idx]
        elif settings.get("source_image") and Path(settings["source_image"]).is_file():
            path = settings["source_image"]
        if path:
            try:
                set_windows_wallpaper(path)
            except Exception:
                pass
    else:
        app = AutoWallpaperApp()
        app.mainloop()
