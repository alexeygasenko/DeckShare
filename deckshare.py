from __future__ import annotations

import json
import os
import posixpath
import queue
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


APP_NAME = "DeckShare"
DEFAULT_REMOTE_PATH = "/home/deck/DeckShare"
AUTH_PASSWORD = "password"
AUTH_KEY = "key"
LOCAL_DEPENDENCY_DIR = Path(__file__).resolve().parent / ".deps"

if LOCAL_DEPENDENCY_DIR.exists():
    sys.path.insert(0, str(LOCAL_DEPENDENCY_DIR))


def app_config_path() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        root = Path(base) / APP_NAME
    else:
        root = Path.home() / f".{APP_NAME.lower()}"

    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        root = Path.cwd() / f".{APP_NAME.lower()}"
        root.mkdir(parents=True, exist_ok=True)

    return root / "config.json"


def normalize_remote_path(value: str) -> str:
    cleaned = value.strip().replace("\\", "/")
    if not cleaned:
        return DEFAULT_REMOTE_PATH
    return cleaned.rstrip("/") or "/"


@dataclass
class Settings:
    host: str = "steamdeck.local"
    username: str = "deck"
    port: int = 22
    remote_path: str = DEFAULT_REMOTE_PATH
    auth_method: str = AUTH_PASSWORD
    identity_file: str = ""
    sources: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> "Settings":
        path = app_config_path()
        if not path.exists():
            return cls()

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()

        settings = cls()
        settings.host = str(raw.get("host") or settings.host)
        settings.username = str(raw.get("username") or settings.username)
        try:
            settings.port = int(raw.get("port") or settings.port)
        except (TypeError, ValueError):
            settings.port = 22
        settings.remote_path = normalize_remote_path(str(raw.get("remote_path") or settings.remote_path))
        auth_method = str(raw.get("auth_method") or settings.auth_method)
        settings.auth_method = auth_method if auth_method in {AUTH_PASSWORD, AUTH_KEY} else AUTH_PASSWORD
        settings.identity_file = str(raw.get("identity_file") or "")
        settings.sources = [str(item) for item in raw.get("sources", []) if Path(str(item)).exists()]
        return settings

    def save(self) -> None:
        payload = {
            "host": self.host,
            "username": self.username,
            "port": self.port,
            "remote_path": self.remote_path,
            "auth_method": self.auth_method,
            "identity_file": self.identity_file,
            "sources": self.sources,
        }
        app_config_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")


class SftpRunner:
    def __init__(self, log: queue.Queue[tuple[str, str]], cancel_event: threading.Event) -> None:
        self.log = log
        self.cancel_event = cancel_event
        self.client = None
        self.sftp = None

    def stop(self) -> None:
        self.cancel_event.set()
        self.close()

    def _emit(self, level: str, text: str) -> None:
        self.log.put((level, text))

    def _require_paramiko(self):
        try:
            import paramiko  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Не установлен пакет paramiko. Выполните: python -m pip install -r requirements.txt") from exc
        return paramiko

    def close(self) -> None:
        if self.sftp is not None:
            self.sftp.close()
            self.sftp = None
        if self.client is not None:
            self.client.close()
            self.client = None

    def connect(self, settings: Settings, secret: str) -> None:
        paramiko = self._require_paramiko()
        self.close()
        self._emit("info", f"Подключаюсь к {settings.username}@{settings.host}:{settings.port}")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            "hostname": settings.host,
            "port": settings.port,
            "username": settings.username,
            "timeout": 10,
            "banner_timeout": 10,
            "auth_timeout": 10,
        }
        if settings.auth_method == AUTH_KEY:
            connect_kwargs["key_filename"] = settings.identity_file
            if secret:
                connect_kwargs["passphrase"] = secret
            connect_kwargs["look_for_keys"] = False
            connect_kwargs["allow_agent"] = False
        else:
            connect_kwargs["password"] = secret
            connect_kwargs["look_for_keys"] = False
            connect_kwargs["allow_agent"] = False

        client.connect(**connect_kwargs)
        self.client = client
        self.sftp = client.open_sftp()

    def test_connection(self, settings: Settings, secret: str) -> bool:
        try:
            self.connect(settings, secret)
            assert self.client is not None
            _, stdout, stderr = self.client.exec_command("echo DeckShare connection ok", timeout=8)
            output = stdout.read().decode("utf-8", errors="replace").strip()
            error = stderr.read().decode("utf-8", errors="replace").strip()
            if output:
                self._emit("output", output)
            if error:
                self._emit("output", error)
            self._emit("success", "SSH-соединение работает.")
            return True
        except Exception as exc:  # noqa: BLE001 - surface connection errors in UI.
            self._emit("error", f"SSH-проверка не удалась: {exc}")
            return False
        finally:
            self.close()

    def transfer(self, settings: Settings, secret: str) -> bool:
        if not settings.sources:
            self._emit("error", "Не выбраны директории для передачи.")
            return False

        valid_sources = [source for source in settings.sources if Path(source).is_dir()]
        missing = [source for source in settings.sources if source not in valid_sources]
        for source in missing:
            self._emit("error", f"Папка недоступна: {source}")

        if not valid_sources:
            return False

        try:
            self.connect(settings, secret)
            assert self.sftp is not None
            self.ensure_remote_dir(settings.remote_path)
        except Exception as exc:  # noqa: BLE001 - surface connection/setup errors in UI.
            self._emit("error", f"Не удалось подготовить подключение: {exc}")
            self.close()
            return False

        try:
            total = len(valid_sources)
            uploaded = 0
            skipped = 0
            for index, source in enumerate(valid_sources, start=1):
                if self.cancel_event.is_set():
                    self._emit("error", "Передача остановлена.")
                    return False

                name = Path(source).name
                remote_root = posixpath.join(settings.remote_path, name)
                self._emit("info", f"[{index}/{total}] Обрабатываю папку: {name}")
                source_uploaded, source_skipped = self.upload_directory(Path(source), remote_root)
                uploaded += source_uploaded
                skipped += source_skipped

            self._emit("success", f"Передача завершена. Отправлено: {uploaded}, пропущено: {skipped}.")
            return True
        except Exception as exc:  # noqa: BLE001 - surface transfer errors in UI.
            self._emit("error", f"Передача не удалась: {exc}")
            return False
        finally:
            self.close()

    def ensure_remote_dir(self, remote_path: str) -> None:
        assert self.sftp is not None
        current = ""
        parts = [part for part in normalize_remote_path(remote_path).split("/") if part]
        if remote_path.startswith("/"):
            current = "/"
        for part in parts:
            current = posixpath.join(current, part) if current != "/" else f"/{part}"
            try:
                self.sftp.stat(current)
            except OSError:
                self.sftp.mkdir(current)

    def remote_exists(self, remote_path: str) -> bool:
        assert self.sftp is not None
        try:
            self.sftp.stat(remote_path)
            return True
        except OSError:
            return False

    def upload_directory(self, source_root: Path, remote_root: str) -> tuple[int, int]:
        assert self.sftp is not None
        uploaded = 0
        skipped = 0
        self.ensure_remote_dir(remote_root)

        for local_dir, dir_names, file_names in os.walk(source_root):
            if self.cancel_event.is_set():
                return uploaded, skipped

            dir_names.sort()
            file_names.sort()
            relative_dir = Path(local_dir).relative_to(source_root)
            remote_dir = remote_root if str(relative_dir) == "." else posixpath.join(
                remote_root,
                relative_dir.as_posix(),
            )
            self.ensure_remote_dir(remote_dir)

            for file_name in file_names:
                if self.cancel_event.is_set():
                    return uploaded, skipped

                local_file = Path(local_dir) / file_name
                remote_file = posixpath.join(remote_dir, file_name)
                if self.remote_exists(remote_file):
                    skipped += 1
                    self._emit("output", f"Пропущен, уже есть: {remote_file}")
                    continue

                self.sftp.put(str(local_file), remote_file)
                uploaded += 1
                self._emit("output", f"Отправлен: {remote_file}")

        return uploaded, skipped


class DeckShareApp(ttk.Frame):
    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root, padding=16)
        self.root = root
        self.settings = Settings.load()
        self.messages: queue.Queue[tuple[str, str]] = queue.Queue()
        self.cancel_event = threading.Event()
        self.runner = SftpRunner(self.messages, self.cancel_event)
        self.worker: threading.Thread | None = None

        self.host_var = tk.StringVar(value=self.settings.host)
        self.user_var = tk.StringVar(value=self.settings.username)
        self.port_var = tk.StringVar(value=str(self.settings.port))
        self.remote_path_var = tk.StringVar(value=self.settings.remote_path)
        self.auth_method_var = tk.StringVar(value=self.settings.auth_method)
        self.identity_var = tk.StringVar(value=self.settings.identity_file)
        self.password_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Готово")

        self._configure_root()
        self._build()
        self._load_sources()
        self.update_auth_fields()
        self._poll_messages()

    def _configure_root(self) -> None:
        self.root.title("DeckShare")
        self.root.minsize(820, 560)
        self.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=2)
        self.columnconfigure(1, weight=3)
        self.rowconfigure(2, weight=1)

        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")

    def _build(self) -> None:
        header = ttk.Frame(self)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="DeckShare", font=("Segoe UI", 20, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Передача выбранных Windows-папок на Steam Deck по SSH/SFTP",
            foreground="#555555",
        ).grid(row=1, column=0, sticky="w")

        settings_box = ttk.LabelFrame(self, text="Steam Deck")
        settings_box.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        settings_box.columnconfigure(1, weight=1)

        self._entry(settings_box, "Хост", self.host_var, 0)
        self._entry(settings_box, "Пользователь", self.user_var, 1)
        self._entry(settings_box, "Порт", self.port_var, 2)
        self._entry(settings_box, "Путь на Deck", self.remote_path_var, 3)

        ttk.Label(settings_box, text="Вход").grid(row=4, column=0, sticky="w", padx=12, pady=6)
        auth_row = ttk.Frame(settings_box)
        auth_row.grid(row=4, column=1, sticky="ew", padx=12, pady=6)
        ttk.Radiobutton(
            auth_row,
            text="Пароль",
            value=AUTH_PASSWORD,
            variable=self.auth_method_var,
            command=self.update_auth_fields,
        ).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            auth_row,
            text="SSH-ключ",
            value=AUTH_KEY,
            variable=self.auth_method_var,
            command=self.update_auth_fields,
        ).grid(row=0, column=1, sticky="w", padx=(16, 0))

        self.password_label = ttk.Label(settings_box, text="Пароль")
        self.password_label.grid(row=5, column=0, sticky="w", padx=12, pady=6)
        self.password_entry = ttk.Entry(settings_box, textvariable=self.password_var, show="*")
        self.password_entry.grid(row=5, column=1, sticky="ew", padx=12, pady=6)

        self.identity_label = ttk.Label(settings_box, text="SSH-ключ")
        self.identity_label.grid(row=6, column=0, sticky="w", padx=12, pady=6)
        key_row = ttk.Frame(settings_box)
        key_row.grid(row=6, column=1, sticky="ew", padx=12, pady=6)
        key_row.columnconfigure(0, weight=1)
        self.identity_entry = ttk.Entry(key_row, textvariable=self.identity_var)
        self.identity_entry.grid(row=0, column=0, sticky="ew")
        self.identity_button = ttk.Button(key_row, text="...", width=4, command=self.choose_identity)
        self.identity_button.grid(row=0, column=1, padx=(6, 0))

        source_box = ttk.LabelFrame(self, text="Директории Windows")
        source_box.grid(row=1, column=1, rowspan=2, sticky="nsew")
        source_box.columnconfigure(0, weight=1)
        source_box.rowconfigure(0, weight=1)

        self.source_list = tk.Listbox(source_box, height=10, activestyle="none", exportselection=False)
        self.source_list.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=12)
        source_scroll = ttk.Scrollbar(source_box, orient="vertical", command=self.source_list.yview)
        source_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 12), pady=12)
        self.source_list.configure(yscrollcommand=source_scroll.set)

        source_buttons = ttk.Frame(source_box)
        source_buttons.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))
        for column in range(3):
            source_buttons.columnconfigure(column, weight=1)
        ttk.Button(source_buttons, text="Добавить", command=self.add_source).grid(row=0, column=0, sticky="ew")
        ttk.Button(source_buttons, text="Удалить", command=self.remove_source).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(source_buttons, text="Очистить", command=self.clear_sources).grid(row=0, column=2, sticky="ew")

        actions = ttk.LabelFrame(self, text="Действия")
        actions.grid(row=2, column=0, sticky="nsew", padx=(0, 12), pady=(12, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        ttk.Button(actions, text="Проверить SSH", command=self.start_test).grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        ttk.Button(actions, text="Передать", command=self.start_transfer).grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=12)
        self.stop_button = ttk.Button(actions, text="Остановить", command=self.stop_worker, state="disabled")
        self.stop_button.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))
        self.progress = ttk.Progressbar(actions, mode="indeterminate")
        self.progress.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))
        ttk.Label(actions, textvariable=self.status_var).grid(row=3, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 12))

        log_box = ttk.LabelFrame(self, text="Журнал")
        log_box.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        log_box.columnconfigure(0, weight=1)
        log_box.rowconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        self.log_text = tk.Text(log_box, height=10, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=12)
        log_scroll = ttk.Scrollbar(log_box, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 12), pady=12)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.tag_configure("error", foreground="#b00020")
        self.log_text.tag_configure("success", foreground="#0b6b2b")
        self.log_text.tag_configure("info", foreground="#1f4e79")
        self.log_text.tag_configure("output", foreground="#333333")

    def _entry(self, parent: ttk.Frame, label: str, variable: tk.StringVar, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=12, pady=6)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=12, pady=6)

    def update_auth_fields(self) -> None:
        is_key = self.auth_method_var.get() == AUTH_KEY
        if is_key:
            self.password_label.configure(text="Фраза ключа")
            self.identity_entry.configure(state="normal")
            self.identity_button.configure(state="normal")
        else:
            self.password_label.configure(text="Пароль")
            self.identity_entry.configure(state="disabled")
            self.identity_button.configure(state="disabled")

    def _load_sources(self) -> None:
        for source in self.settings.sources:
            self.source_list.insert("end", source)

    def add_source(self) -> None:
        selected = filedialog.askdirectory(title="Выберите директорию для передачи")
        if not selected:
            return
        normalized = str(Path(selected))
        existing = set(self.source_list.get(0, "end"))
        if normalized not in existing:
            self.source_list.insert("end", normalized)
            self.save_settings()

    def remove_source(self) -> None:
        selected = list(self.source_list.curselection())
        selected.reverse()
        for index in selected:
            self.source_list.delete(index)
        self.save_settings()

    def clear_sources(self) -> None:
        self.source_list.delete(0, "end")
        self.save_settings()

    def choose_identity(self) -> None:
        selected = filedialog.askopenfilename(title="Выберите приватный SSH-ключ")
        if selected:
            self.identity_var.set(selected)
            self.save_settings()

    def collect_settings(self, validate_auth: bool = True) -> Settings | None:
        try:
            port = int(self.port_var.get().strip())
        except ValueError:
            messagebox.showerror(APP_NAME, "Порт должен быть числом.")
            return None

        if port < 1 or port > 65535:
            messagebox.showerror(APP_NAME, "Порт должен быть в диапазоне 1-65535.")
            return None

        host = self.host_var.get().strip()
        username = self.user_var.get().strip()
        if not host or not username:
            messagebox.showerror(APP_NAME, "Хост и пользователь обязательны.")
            return None

        identity_file = self.identity_var.get().strip()
        auth_method = self.auth_method_var.get()
        if auth_method not in {AUTH_PASSWORD, AUTH_KEY}:
            auth_method = AUTH_PASSWORD

        if validate_auth and auth_method == AUTH_KEY and not identity_file:
            messagebox.showerror(APP_NAME, "Для входа по ключу выберите файл SSH-ключа.")
            return None

        if validate_auth and auth_method == AUTH_KEY and identity_file and not Path(identity_file).is_file():
            messagebox.showerror(APP_NAME, "Выбранный SSH-ключ не найден.")
            return None

        return Settings(
            host=host,
            username=username,
            port=port,
            remote_path=normalize_remote_path(self.remote_path_var.get()),
            auth_method=auth_method,
            identity_file=identity_file,
            sources=list(self.source_list.get(0, "end")),
        )

    def collect_secret(self) -> str | None:
        secret = self.password_var.get()
        if self.auth_method_var.get() == AUTH_PASSWORD and not secret:
            messagebox.showerror(APP_NAME, "Введите пароль пользователя Steam Deck.")
            return None
        return secret

    def save_settings(self) -> bool:
        settings = self.collect_settings(validate_auth=False)
        if settings is None:
            return False
        self.settings = settings
        self.settings.save()
        return True

    def start_test(self) -> None:
        settings = self.collect_settings()
        if settings is None:
            return
        secret = self.collect_secret()
        if secret is None:
            return
        settings.save()
        self._start_worker(lambda: self.runner.test_connection(settings, secret), "Проверяю SSH...")

    def start_transfer(self) -> None:
        settings = self.collect_settings()
        if settings is None:
            return
        secret = self.collect_secret()
        if secret is None:
            return
        settings.save()
        self.remote_path_var.set(settings.remote_path)
        self._start_worker(lambda: self.runner.transfer(settings, secret), "Передаю файлы...")

    def _start_worker(self, target: callable, status: str) -> None:
        if self.worker and self.worker.is_alive():
            return

        self.cancel_event.clear()
        self.status_var.set(status)
        self.stop_button.configure(state="normal")
        self.progress.start(10)

        def wrapped() -> None:
            try:
                target()
            except Exception as exc:  # noqa: BLE001 - show unexpected failures in the UI log.
                self.messages.put(("error", f"Ошибка: {exc}"))
            finally:
                self.messages.put(("done", "Готово"))

        self.worker = threading.Thread(target=wrapped, daemon=True)
        self.worker.start()

    def stop_worker(self) -> None:
        self.runner.stop()
        self.status_var.set("Останавливаю...")

    def _poll_messages(self) -> None:
        try:
            while True:
                level, text = self.messages.get_nowait()
                if level == "done":
                    self.stop_button.configure(state="disabled")
                    self.progress.stop()
                    self.status_var.set(text)
                else:
                    self.append_log(level, text)
        except queue.Empty:
            pass

        self.root.after(100, self._poll_messages)

    def append_log(self, level: str, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {text}\n", level)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


def main() -> None:
    root = tk.Tk()
    app = DeckShareApp(root)
    app.mainloop()


if __name__ == "__main__":
    main()
