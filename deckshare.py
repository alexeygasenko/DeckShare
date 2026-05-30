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
LANG_RU = "ru"
LANG_EN = "en"
LOCAL_DEPENDENCY_DIR = Path(__file__).resolve().parent / ".deps"

if LOCAL_DEPENDENCY_DIR.exists():
    sys.path.insert(0, str(LOCAL_DEPENDENCY_DIR))


TRANSLATIONS = {
    LANG_RU: {
        "add": "Добавить",
        "auth": "Вход",
        "auth_key": "SSH-ключ",
        "auth_password": "Пароль",
        "clear": "Очистить",
        "dialog_select_dir": "Выберите директорию для передачи",
        "dialog_select_key": "Выберите приватный SSH-ключ",
        "error": "Ошибка",
        "error_auth_key_missing": "Для входа по ключу выберите файл SSH-ключа.",
        "error_connect_failed": "SSH-проверка не удалась: {error}",
        "error_generic": "Ошибка: {error}",
        "error_host_user_required": "Хост и пользователь обязательны.",
        "error_identity_missing": "Выбранный SSH-ключ не найден.",
        "error_missing_folder": "Папка недоступна: {source}",
        "error_no_password": "Введите пароль пользователя Steam Deck.",
        "error_no_sources": "Не выбраны директории для передачи.",
        "error_paramiko_missing": "Не установлен пакет paramiko. Запустите install_requirements.bat.",
        "error_port_number": "Порт должен быть числом.",
        "error_port_range": "Порт должен быть в диапазоне 1-65535.",
        "error_prepare_failed": "Не удалось подготовить подключение: {error}",
        "error_stopped": "Передача остановлена.",
        "error_transfer_failed": "Передача не удалась: {error}",
        "group_actions": "Действия",
        "group_log": "Журнал",
        "group_sources": "Директории Windows",
        "group_steam_deck": "Steam Deck",
        "host": "Хост",
        "identity": "SSH-ключ",
        "language": "Язык",
        "log_connecting": "Подключаюсь к {user}@{host}:{port}",
        "log_processing_folder": "[{index}/{total}] Обрабатываю папку: {name}",
        "log_skipped": "Пропущен, уже есть: {path}",
        "log_uploaded": "Отправлен: {path}",
        "passphrase": "Фраза ключа",
        "password": "Пароль",
        "port": "Порт",
        "remote_path": "Путь на Deck",
        "remove": "Удалить",
        "status_ready": "Готово",
        "status_stopping": "Останавливаю...",
        "status_testing": "Проверяю SSH...",
        "status_transferring": "Передаю файлы...",
        "subtitle": "Передача выбранных Windows-папок на Steam Deck по SSH/SFTP",
        "success_connection": "SSH-соединение работает.",
        "success_transfer": "Передача завершена. Отправлено: {uploaded}, пропущено: {skipped}.",
        "test_ssh": "Проверить SSH",
        "transfer": "Передать",
        "user": "Пользователь",
        "stop": "Остановить",
    },
    LANG_EN: {
        "add": "Add",
        "auth": "Login",
        "auth_key": "SSH key",
        "auth_password": "Password",
        "clear": "Clear",
        "dialog_select_dir": "Choose a directory to transfer",
        "dialog_select_key": "Choose a private SSH key",
        "error": "Error",
        "error_auth_key_missing": "Choose an SSH key file for key login.",
        "error_connect_failed": "SSH check failed: {error}",
        "error_generic": "Error: {error}",
        "error_host_user_required": "Host and user are required.",
        "error_identity_missing": "Selected SSH key was not found.",
        "error_missing_folder": "Folder is not available: {source}",
        "error_no_password": "Enter the Steam Deck user password.",
        "error_no_sources": "No directories selected for transfer.",
        "error_paramiko_missing": "The paramiko package is not installed. Run install_requirements.bat.",
        "error_port_number": "Port must be a number.",
        "error_port_range": "Port must be in the 1-65535 range.",
        "error_prepare_failed": "Could not prepare the connection: {error}",
        "error_stopped": "Transfer stopped.",
        "error_transfer_failed": "Transfer failed: {error}",
        "group_actions": "Actions",
        "group_log": "Log",
        "group_sources": "Windows directories",
        "group_steam_deck": "Steam Deck",
        "host": "Host",
        "identity": "SSH key",
        "language": "Language",
        "log_connecting": "Connecting to {user}@{host}:{port}",
        "log_processing_folder": "[{index}/{total}] Processing folder: {name}",
        "log_skipped": "Skipped, already exists: {path}",
        "log_uploaded": "Uploaded: {path}",
        "passphrase": "Key passphrase",
        "password": "Password",
        "port": "Port",
        "remote_path": "Deck path",
        "remove": "Remove",
        "status_ready": "Ready",
        "status_stopping": "Stopping...",
        "status_testing": "Checking SSH...",
        "status_transferring": "Transferring files...",
        "subtitle": "Transfer selected Windows folders to Steam Deck over SSH/SFTP",
        "success_connection": "SSH connection works.",
        "success_transfer": "Transfer complete. Uploaded: {uploaded}, skipped: {skipped}.",
        "test_ssh": "Check SSH",
        "transfer": "Transfer",
        "user": "User",
        "stop": "Stop",
    },
}


def translate_text(language: str, key: str, **kwargs: object) -> str:
    bundle = TRANSLATIONS.get(language, TRANSLATIONS[LANG_RU])
    text = bundle.get(key, TRANSLATIONS[LANG_RU].get(key, key))
    return text.format(**kwargs)


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


def local_config_path() -> Path:
    root = Path.cwd() / f".{APP_NAME.lower()}"
    root.mkdir(parents=True, exist_ok=True)
    return root / "config.json"


def config_read_paths() -> list[Path]:
    paths = [app_config_path(), local_config_path()]
    unique_paths: list[Path] = []
    for path in paths:
        if path not in unique_paths:
            unique_paths.append(path)
    return unique_paths


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
    language: str = LANG_RU
    identity_file: str = ""
    sources: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> "Settings":
        raw = None
        for path in config_read_paths():
            if not path.exists():
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                break
            except (OSError, json.JSONDecodeError):
                continue

        if raw is None:
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
        language = str(raw.get("language") or settings.language)
        settings.language = language if language in TRANSLATIONS else LANG_RU
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
            "language": self.language,
            "identity_file": self.identity_file,
            "sources": self.sources,
        }
        data = json.dumps(payload, indent=2)
        try:
            app_config_path().write_text(data, encoding="utf-8")
        except OSError:
            local_config_path().write_text(data, encoding="utf-8")


class SftpRunner:
    def __init__(
        self,
        log: queue.Queue[tuple[str, str]],
        cancel_event: threading.Event,
        translate: callable,
    ) -> None:
        self.log = log
        self.cancel_event = cancel_event
        self.tr = translate
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
            raise RuntimeError(self.tr("error_paramiko_missing")) from exc
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
        self._emit("info", self.tr("log_connecting", user=settings.username, host=settings.host, port=settings.port))
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
            self._emit("success", self.tr("success_connection"))
            return True
        except Exception as exc:  # noqa: BLE001 - surface connection errors in UI.
            self._emit("error", self.tr("error_connect_failed", error=exc))
            return False
        finally:
            self.close()

    def transfer(self, settings: Settings, secret: str) -> bool:
        if not settings.sources:
            self._emit("error", self.tr("error_no_sources"))
            return False

        valid_sources = [source for source in settings.sources if Path(source).is_dir()]
        missing = [source for source in settings.sources if source not in valid_sources]
        for source in missing:
            self._emit("error", self.tr("error_missing_folder", source=source))

        if not valid_sources:
            return False

        try:
            self.connect(settings, secret)
            assert self.sftp is not None
            self.ensure_remote_dir(settings.remote_path)
        except Exception as exc:  # noqa: BLE001 - surface connection/setup errors in UI.
            self._emit("error", self.tr("error_prepare_failed", error=exc))
            self.close()
            return False

        try:
            total = len(valid_sources)
            uploaded = 0
            skipped = 0
            for index, source in enumerate(valid_sources, start=1):
                if self.cancel_event.is_set():
                    self._emit("error", self.tr("error_stopped"))
                    return False

                name = Path(source).name
                remote_root = posixpath.join(settings.remote_path, name)
                self._emit("info", self.tr("log_processing_folder", index=index, total=total, name=name))
                source_uploaded, source_skipped = self.upload_directory(Path(source), remote_root)
                uploaded += source_uploaded
                skipped += source_skipped

            self._emit("success", self.tr("success_transfer", uploaded=uploaded, skipped=skipped))
            return True
        except Exception as exc:  # noqa: BLE001 - surface transfer errors in UI.
            self._emit("error", self.tr("error_transfer_failed", error=exc))
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
                    self._emit("output", self.tr("log_skipped", path=remote_file))
                    continue

                self.sftp.put(str(local_file), remote_file)
                uploaded += 1
                self._emit("output", self.tr("log_uploaded", path=remote_file))

        return uploaded, skipped


class DeckShareApp(ttk.Frame):
    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root, padding=16)
        self.root = root
        self.settings = Settings.load()
        self.messages: queue.Queue[tuple[str, str]] = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.localized_widgets: list[tuple[tk.Widget, str]] = []

        self.host_var = tk.StringVar(value=self.settings.host)
        self.user_var = tk.StringVar(value=self.settings.username)
        self.port_var = tk.StringVar(value=str(self.settings.port))
        self.remote_path_var = tk.StringVar(value=self.settings.remote_path)
        self.auth_method_var = tk.StringVar(value=self.settings.auth_method)
        self.language_var = tk.StringVar(value=self.settings.language)
        self.identity_var = tk.StringVar(value=self.settings.identity_file)
        self.password_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value=self.tr("status_ready"))
        self.runner = SftpRunner(self.messages, self.cancel_event, self.make_translator(self.settings.language))

        self._configure_root()
        self._build()
        self._load_sources()
        self.update_auth_fields()
        self.apply_language()
        self._poll_messages()

    def tr(self, key: str, **kwargs: object) -> str:
        return translate_text(self.language_var.get(), key, **kwargs)

    def make_translator(self, language: str) -> callable:
        selected = language if language in TRANSLATIONS else LANG_RU
        return lambda key, **kwargs: translate_text(selected, key, **kwargs)

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
        self.subtitle_label = ttk.Label(
            header,
            text=self.tr("subtitle"),
            foreground="#555555",
        )
        self.subtitle_label.grid(row=1, column=0, sticky="w")
        self.localized_widgets.append((self.subtitle_label, "subtitle"))

        language_row = ttk.Frame(header)
        language_row.grid(row=0, column=1, rowspan=2, sticky="e")
        self.language_label = ttk.Label(language_row, text=self.tr("language"))
        self.language_label.grid(row=0, column=0, sticky="e", padx=(0, 8))
        self.localized_widgets.append((self.language_label, "language"))
        self.language_select = ttk.Combobox(
            language_row,
            textvariable=self.language_var,
            values=(LANG_RU, LANG_EN),
            width=6,
            state="readonly",
        )
        self.language_select.grid(row=0, column=1, sticky="e")
        self.language_select.bind("<<ComboboxSelected>>", self.change_language)

        self.settings_box = ttk.LabelFrame(self, text=self.tr("group_steam_deck"))
        self.settings_box.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        self.settings_box.columnconfigure(1, weight=1)
        self.localized_widgets.append((self.settings_box, "group_steam_deck"))

        self._entry(self.settings_box, "host", self.host_var, 0)
        self._entry(self.settings_box, "user", self.user_var, 1)
        self._entry(self.settings_box, "port", self.port_var, 2)
        self._entry(self.settings_box, "remote_path", self.remote_path_var, 3)

        self.auth_label = ttk.Label(self.settings_box, text=self.tr("auth"))
        self.auth_label.grid(row=4, column=0, sticky="w", padx=12, pady=6)
        self.localized_widgets.append((self.auth_label, "auth"))
        auth_row = ttk.Frame(self.settings_box)
        auth_row.grid(row=4, column=1, sticky="ew", padx=12, pady=6)
        self.auth_password_radio = ttk.Radiobutton(
            auth_row,
            text=self.tr("auth_password"),
            value=AUTH_PASSWORD,
            variable=self.auth_method_var,
            command=self.update_auth_fields,
        )
        self.auth_password_radio.grid(row=0, column=0, sticky="w")
        self.localized_widgets.append((self.auth_password_radio, "auth_password"))
        self.auth_key_radio = ttk.Radiobutton(
            auth_row,
            text=self.tr("auth_key"),
            value=AUTH_KEY,
            variable=self.auth_method_var,
            command=self.update_auth_fields,
        )
        self.auth_key_radio.grid(row=0, column=1, sticky="w", padx=(16, 0))
        self.localized_widgets.append((self.auth_key_radio, "auth_key"))

        self.password_label = ttk.Label(self.settings_box, text=self.tr("password"))
        self.password_label.grid(row=5, column=0, sticky="w", padx=12, pady=6)
        self.password_entry = ttk.Entry(self.settings_box, textvariable=self.password_var, show="*")
        self.password_entry.grid(row=5, column=1, sticky="ew", padx=12, pady=6)

        self.identity_label = ttk.Label(self.settings_box, text=self.tr("identity"))
        self.identity_label.grid(row=6, column=0, sticky="w", padx=12, pady=6)
        self.localized_widgets.append((self.identity_label, "identity"))
        key_row = ttk.Frame(self.settings_box)
        key_row.grid(row=6, column=1, sticky="ew", padx=12, pady=6)
        key_row.columnconfigure(0, weight=1)
        self.identity_entry = ttk.Entry(key_row, textvariable=self.identity_var)
        self.identity_entry.grid(row=0, column=0, sticky="ew")
        self.identity_button = ttk.Button(key_row, text="...", width=4, command=self.choose_identity)
        self.identity_button.grid(row=0, column=1, padx=(6, 0))

        self.source_box = ttk.LabelFrame(self, text=self.tr("group_sources"))
        self.source_box.grid(row=1, column=1, rowspan=2, sticky="nsew")
        self.source_box.columnconfigure(0, weight=1)
        self.source_box.rowconfigure(0, weight=1)
        self.localized_widgets.append((self.source_box, "group_sources"))

        self.source_list = tk.Listbox(self.source_box, height=10, activestyle="none", exportselection=False)
        self.source_list.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=12)
        source_scroll = ttk.Scrollbar(self.source_box, orient="vertical", command=self.source_list.yview)
        source_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 12), pady=12)
        self.source_list.configure(yscrollcommand=source_scroll.set)

        source_buttons = ttk.Frame(self.source_box)
        source_buttons.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))
        for column in range(3):
            source_buttons.columnconfigure(column, weight=1)
        self.add_button = ttk.Button(source_buttons, text=self.tr("add"), command=self.add_source)
        self.add_button.grid(row=0, column=0, sticky="ew")
        self.localized_widgets.append((self.add_button, "add"))
        self.remove_button = ttk.Button(source_buttons, text=self.tr("remove"), command=self.remove_source)
        self.remove_button.grid(row=0, column=1, sticky="ew", padx=8)
        self.localized_widgets.append((self.remove_button, "remove"))
        self.clear_button = ttk.Button(source_buttons, text=self.tr("clear"), command=self.clear_sources)
        self.clear_button.grid(row=0, column=2, sticky="ew")
        self.localized_widgets.append((self.clear_button, "clear"))

        self.actions_box = ttk.LabelFrame(self, text=self.tr("group_actions"))
        self.actions_box.grid(row=2, column=0, sticky="nsew", padx=(0, 12), pady=(12, 0))
        self.actions_box.columnconfigure(0, weight=1)
        self.actions_box.columnconfigure(1, weight=1)
        self.localized_widgets.append((self.actions_box, "group_actions"))
        self.test_button = ttk.Button(self.actions_box, text=self.tr("test_ssh"), command=self.start_test)
        self.test_button.grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        self.localized_widgets.append((self.test_button, "test_ssh"))
        self.transfer_button = ttk.Button(self.actions_box, text=self.tr("transfer"), command=self.start_transfer)
        self.transfer_button.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=12)
        self.localized_widgets.append((self.transfer_button, "transfer"))
        self.stop_button = ttk.Button(self.actions_box, text=self.tr("stop"), command=self.stop_worker, state="disabled")
        self.stop_button.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))
        self.localized_widgets.append((self.stop_button, "stop"))
        self.progress = ttk.Progressbar(self.actions_box, mode="indeterminate")
        self.progress.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))
        ttk.Label(self.actions_box, textvariable=self.status_var).grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="w",
            padx=12,
            pady=(0, 12),
        )

        self.log_box = ttk.LabelFrame(self, text=self.tr("group_log"))
        self.log_box.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        self.log_box.columnconfigure(0, weight=1)
        self.log_box.rowconfigure(0, weight=1)
        self.localized_widgets.append((self.log_box, "group_log"))
        self.rowconfigure(3, weight=1)

        self.log_text = tk.Text(self.log_box, height=10, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=12)
        log_scroll = ttk.Scrollbar(self.log_box, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 12), pady=12)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.tag_configure("error", foreground="#b00020")
        self.log_text.tag_configure("success", foreground="#0b6b2b")
        self.log_text.tag_configure("info", foreground="#1f4e79")
        self.log_text.tag_configure("output", foreground="#333333")

    def _entry(self, parent: ttk.Frame, label_key: str, variable: tk.StringVar, row: int) -> None:
        label = ttk.Label(parent, text=self.tr(label_key))
        label.grid(row=row, column=0, sticky="w", padx=12, pady=6)
        self.localized_widgets.append((label, label_key))
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=12, pady=6)

    def apply_language(self) -> None:
        for widget, key in self.localized_widgets:
            widget.configure(text=self.tr(key))
        self.update_auth_fields()
        if self.status_var.get() in {
            TRANSLATIONS[LANG_RU]["status_ready"],
            TRANSLATIONS[LANG_EN]["status_ready"],
        }:
            self.status_var.set(self.tr("status_ready"))

    def change_language(self, _event: tk.Event | None = None) -> None:
        self.apply_language()
        self.save_settings()

    def update_auth_fields(self) -> None:
        is_key = self.auth_method_var.get() == AUTH_KEY
        if is_key:
            self.password_label.configure(text=self.tr("passphrase"))
            self.identity_entry.configure(state="normal")
            self.identity_button.configure(state="normal")
        else:
            self.password_label.configure(text=self.tr("password"))
            self.identity_entry.configure(state="disabled")
            self.identity_button.configure(state="disabled")

    def _load_sources(self) -> None:
        for source in self.settings.sources:
            self.source_list.insert("end", source)

    def add_source(self) -> None:
        selected = filedialog.askdirectory(title=self.tr("dialog_select_dir"))
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
        selected = filedialog.askopenfilename(title=self.tr("dialog_select_key"))
        if selected:
            self.identity_var.set(selected)
            self.save_settings()

    def collect_settings(self, validate_auth: bool = True) -> Settings | None:
        try:
            port = int(self.port_var.get().strip())
        except ValueError:
            messagebox.showerror(APP_NAME, self.tr("error_port_number"))
            return None

        if port < 1 or port > 65535:
            messagebox.showerror(APP_NAME, self.tr("error_port_range"))
            return None

        host = self.host_var.get().strip()
        username = self.user_var.get().strip()
        if not host or not username:
            messagebox.showerror(APP_NAME, self.tr("error_host_user_required"))
            return None

        identity_file = self.identity_var.get().strip()
        auth_method = self.auth_method_var.get()
        if auth_method not in {AUTH_PASSWORD, AUTH_KEY}:
            auth_method = AUTH_PASSWORD

        if validate_auth and auth_method == AUTH_KEY and not identity_file:
            messagebox.showerror(APP_NAME, self.tr("error_auth_key_missing"))
            return None

        if validate_auth and auth_method == AUTH_KEY and identity_file and not Path(identity_file).is_file():
            messagebox.showerror(APP_NAME, self.tr("error_identity_missing"))
            return None

        return Settings(
            host=host,
            username=username,
            port=port,
            remote_path=normalize_remote_path(self.remote_path_var.get()),
            auth_method=auth_method,
            language=self.language_var.get() if self.language_var.get() in TRANSLATIONS else LANG_RU,
            identity_file=identity_file,
            sources=list(self.source_list.get(0, "end")),
        )

    def collect_secret(self) -> str | None:
        secret = self.password_var.get()
        if self.auth_method_var.get() == AUTH_PASSWORD and not secret:
            messagebox.showerror(APP_NAME, self.tr("error_no_password"))
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
        self.runner.tr = self.make_translator(settings.language)
        self._start_worker(lambda: self.runner.test_connection(settings, secret), self.tr("status_testing"))

    def start_transfer(self) -> None:
        settings = self.collect_settings()
        if settings is None:
            return
        secret = self.collect_secret()
        if secret is None:
            return
        settings.save()
        self.remote_path_var.set(settings.remote_path)
        self.runner.tr = self.make_translator(settings.language)
        self._start_worker(lambda: self.runner.transfer(settings, secret), self.tr("status_transferring"))

    def _start_worker(self, target: callable, status: str) -> None:
        if self.worker and self.worker.is_alive():
            return

        self.cancel_event.clear()
        self.status_var.set(status)
        self.stop_button.configure(state="normal")
        self.progress.start(10)
        tr = self.make_translator(self.language_var.get())

        def wrapped() -> None:
            try:
                target()
            except Exception as exc:  # noqa: BLE001 - show unexpected failures in the UI log.
                self.messages.put(("error", tr("error_generic", error=exc)))
            finally:
                self.messages.put(("done", tr("status_ready")))

        self.worker = threading.Thread(target=wrapped, daemon=True)
        self.worker.start()

    def stop_worker(self) -> None:
        self.runner.stop()
        self.status_var.set(self.tr("status_stopping"))

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
