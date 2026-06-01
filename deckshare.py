from __future__ import annotations

import hashlib
import json
import os
import posixpath
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


APP_NAME = "DeckShare"
KEYRING_SERVICE = APP_NAME
DEFAULT_REMOTE_PATH = "/home/deck/DeckShare"
SFTP_WINDOW_SIZE = 64 * 1024 * 1024
SFTP_MAX_PACKET_SIZE = 1024 * 1024
MIN_PARALLEL_TRANSFERS = 1
MAX_PARALLEL_TRANSFERS = 8
AUTH_PASSWORD = "password"
AUTH_KEY = "key"
ENGINE_PARAMIKO = "paramiko"
ENGINE_OPENSSH = "openssh"
LANG_RU = "ru"
LANG_EN = "en"
LOCAL_DEPENDENCY_DIR = Path(__file__).resolve().parent / ".deps"

if LOCAL_DEPENDENCY_DIR.exists():
    sys.path.insert(0, str(LOCAL_DEPENDENCY_DIR))


TRANSLATIONS = {
    LANG_RU: {
        "add": "Добавить",
        "apply_remote_path": "Применить",
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
        "error_host_not_found": "Не удалось найти хост '{host}'. Укажите IP-адрес Steam Deck вместо steamdeck.local или настройте mDNS/Bonjour в Windows.",
        "error_identity_missing": "Выбранный SSH-ключ не найден.",
        "error_missing_folder": "Папка недоступна: {source}",
        "error_no_password": "Введите пароль пользователя Steam Deck.",
        "error_no_sources": "Не выбраны директории для передачи.",
        "error_keyring_missing": "Не установлен пакет keyring. Запустите install_requirements.bat.",
        "error_keyring_read_failed": "Не удалось прочитать сохраненный пароль: {error}",
        "error_keyring_save_failed": "Не удалось сохранить пароль: {error}",
        "error_openssh_command_failed": "Команда OpenSSH завершилась с ошибкой: {error}",
        "error_openssh_key_required": "Fast OpenSSH работает только с входом по SSH-ключу.",
        "error_openssh_missing": "Не найден {name}. Установите OpenSSH Client в Windows.",
        "error_paramiko_missing": "Не установлен пакет paramiko. Запустите install_requirements.bat.",
        "error_port_number": "Порт должен быть числом.",
        "error_port_range": "Порт должен быть в диапазоне 1-65535.",
        "error_prepare_failed": "Не удалось подготовить подключение: {error}",
        "error_stopped": "Передача остановлена.",
        "error_transfer_failed": "Передача не удалась: {error}",
        "error_upload_verify_failed": "Проверка загруженного файла не прошла: {path}",
        "group_actions": "Действия",
        "group_log": "Журнал",
        "group_sources": "Директории Windows",
        "group_steam_deck": "Steam Deck",
        "host": "Хост",
        "identity": "SSH-ключ",
        "engine_fast": "Fast OpenSSH",
        "engine_paramiko": "Compatible SFTP",
        "language": "Язык",
        "log_connecting": "Подключаюсь к {user}@{host}:{port}",
        "log_processing_folder": "[{index}/{total}] Обрабатываю папку: {name}",
        "log_hashing": "Проверяю временный файл после загрузки: {path}",
        "log_password_deleted": "Сохраненный пароль удален.",
        "log_password_loaded": "Сохраненный пароль загружен из системного хранилища.",
        "log_password_saved": "Пароль сохранен в системном хранилище.",
        "log_reuploading": "Файл будет передан заново: {path} ({reason})",
        "log_reuploading_size": "размер отличается",
        "log_skipped": "Пропущен, файл уже есть и размер совпал: {path}",
        "log_uploaded": "Отправлен: {path} - 100% - {speed}",
        "log_uploading": "Передается: {path} - {percent}% - {speed} - осталось: файл {file_eta}, всего {total_eta}",
        "passphrase": "Фраза ключа",
        "password": "Пароль",
        "parallel_transfers": "Параллельных файлов",
        "port": "Порт",
        "remote_path": "Путь на Deck",
        "remote_path_default": "Путь на Deck по умолчанию",
        "remove": "Удалить",
        "selected_remote_path": "Путь на Deck для выбранной папки",
        "save_password": "Сохранить пароль безопасно",
        "status_ready": "Готово",
        "status_stopping": "Останавливаю...",
        "status_testing": "Проверяю SSH...",
        "status_transferring": "Передаю файлы...",
        "subtitle": "Передача выбранных Windows-папок на Steam Deck по SSH/SFTP",
        "success_connection": "SSH-соединение работает.",
        "success_transfer": "Передача завершена. Отправлено: {uploaded}, пропущено: {skipped}.",
        "test_ssh": "Проверить SSH",
        "transfer": "Передать",
        "transfer_engine": "Движок передачи",
        "user": "Пользователь",
        "stop": "Остановить",
    },
    LANG_EN: {
        "add": "Add",
        "apply_remote_path": "Apply",
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
        "error_host_not_found": "Could not resolve host '{host}'. Use the Steam Deck IP address instead of steamdeck.local, or set up mDNS/Bonjour on Windows.",
        "error_identity_missing": "Selected SSH key was not found.",
        "error_missing_folder": "Folder is not available: {source}",
        "error_no_password": "Enter the Steam Deck user password.",
        "error_no_sources": "No directories selected for transfer.",
        "error_keyring_missing": "The keyring package is not installed. Run install_requirements.bat.",
        "error_keyring_read_failed": "Could not read the saved password: {error}",
        "error_keyring_save_failed": "Could not save the password: {error}",
        "error_openssh_command_failed": "OpenSSH command failed: {error}",
        "error_openssh_key_required": "Fast OpenSSH works only with SSH key login.",
        "error_openssh_missing": "{name} was not found. Install OpenSSH Client in Windows.",
        "error_paramiko_missing": "The paramiko package is not installed. Run install_requirements.bat.",
        "error_port_number": "Port must be a number.",
        "error_port_range": "Port must be in the 1-65535 range.",
        "error_prepare_failed": "Could not prepare the connection: {error}",
        "error_stopped": "Transfer stopped.",
        "error_transfer_failed": "Transfer failed: {error}",
        "error_upload_verify_failed": "Uploaded file verification failed: {path}",
        "group_actions": "Actions",
        "group_log": "Log",
        "group_sources": "Windows directories",
        "group_steam_deck": "Steam Deck",
        "host": "Host",
        "identity": "SSH key",
        "engine_fast": "Fast OpenSSH",
        "engine_paramiko": "Compatible SFTP",
        "language": "Language",
        "log_connecting": "Connecting to {user}@{host}:{port}",
        "log_processing_folder": "[{index}/{total}] Processing folder: {name}",
        "log_hashing": "Verifying temporary file after upload: {path}",
        "log_password_deleted": "Saved password deleted.",
        "log_password_loaded": "Saved password loaded from the system credential store.",
        "log_password_saved": "Password saved in the system credential store.",
        "log_reuploading": "File will be uploaded again: {path} ({reason})",
        "log_reuploading_size": "size differs",
        "log_skipped": "Skipped, file already exists and size matches: {path}",
        "log_uploaded": "Uploaded: {path} - 100% - {speed}",
        "log_uploading": "Uploading: {path} - {percent}% - {speed} - ETA: file {file_eta}, total {total_eta}",
        "passphrase": "Key passphrase",
        "password": "Password",
        "parallel_transfers": "Parallel files",
        "port": "Port",
        "remote_path": "Deck path",
        "remote_path_default": "Default Deck path",
        "remove": "Remove",
        "selected_remote_path": "Deck path for selected folder",
        "save_password": "Save password securely",
        "status_ready": "Ready",
        "status_stopping": "Stopping...",
        "status_testing": "Checking SSH...",
        "status_transferring": "Transferring files...",
        "subtitle": "Transfer selected Windows folders to Steam Deck over SSH/SFTP",
        "success_connection": "SSH connection works.",
        "success_transfer": "Transfer complete. Uploaded: {uploaded}, skipped: {skipped}.",
        "test_ssh": "Check SSH",
        "transfer": "Transfer",
        "transfer_engine": "Transfer engine",
        "user": "User",
        "stop": "Stop",
    },
}


def translate_text(language: str, key: str, **kwargs: object) -> str:
    bundle = TRANSLATIONS.get(language, TRANSLATIONS[LANG_RU])
    text = bundle.get(key, TRANSLATIONS[LANG_RU].get(key, key))
    return text.format(**kwargs)


def format_transfer_speed(bytes_per_second: float) -> str:
    units = ("B/s", "KB/s", "MB/s", "GB/s")
    value = max(bytes_per_second, 0.0)
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{value:.0f} {units[unit_index]}"
    return f"{value:.1f} {units[unit_index]}"


def format_transfer_percent(sent_bytes: int, total_bytes: int) -> str:
    if total_bytes <= 0:
        return "100.0" if sent_bytes else "0.0"
    percent = min((sent_bytes / total_bytes) * 100, 100)
    return f"{percent:.1f}"


def format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "--"

    total_seconds = int(seconds + 0.5)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:d}:{secs:02d}"


def credential_key_for(settings: "Settings") -> str:
    return f"ssh:{settings.username}@{settings.host}:{settings.port}"


def require_keyring(translate: callable):
    try:
        import keyring  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(translate("error_keyring_missing")) from exc
    return keyring


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


def quote_posix(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def find_windows_openssh(name: str) -> str:
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    candidate = Path(system_root) / "System32" / "OpenSSH" / f"{name}.exe"
    if candidate.exists():
        return str(candidate)

    found = shutil.which(name)
    if found:
        return found

    return f"{name}.exe"


@dataclass
class TransferItem:
    local_path: str
    remote_path: str = DEFAULT_REMOTE_PATH

    @classmethod
    def from_config(cls, raw: object, default_remote_path: str) -> "TransferItem | None":
        if isinstance(raw, str):
            local_path = raw
            remote_path = default_remote_path
        elif isinstance(raw, dict):
            local_path = str(raw.get("local_path") or raw.get("path") or "")
            remote_path = str(raw.get("remote_path") or default_remote_path)
        else:
            return None

        if not local_path or not Path(local_path).exists():
            return None

        return cls(local_path=str(Path(local_path)), remote_path=normalize_remote_path(remote_path))

    def to_config(self) -> dict[str, str]:
        return {
            "local_path": self.local_path,
            "remote_path": self.remote_path,
        }


@dataclass
class UploadTask:
    local_path: Path
    remote_path: str
    temp_path: str
    size: int


@dataclass
class TransferProgress:
    total_bytes: int = 0
    completed_bytes: int = 0
    started_at: float = 0.0
    active_bytes: dict[int, int] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)


@dataclass
class Settings:
    host: str = "steamdeck.local"
    username: str = "deck"
    port: int = 22
    remote_path: str = DEFAULT_REMOTE_PATH
    auth_method: str = AUTH_PASSWORD
    transfer_engine: str = ENGINE_PARAMIKO
    parallel_transfers: int = 1
    language: str = LANG_RU
    identity_file: str = ""
    save_password: bool = False
    credential_key: str = ""
    sources: list[TransferItem] = field(default_factory=list)

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
        transfer_engine = str(raw.get("transfer_engine") or settings.transfer_engine)
        settings.transfer_engine = transfer_engine if transfer_engine in {ENGINE_PARAMIKO, ENGINE_OPENSSH} else ENGINE_PARAMIKO
        try:
            settings.parallel_transfers = int(raw.get("parallel_transfers") or settings.parallel_transfers)
        except (TypeError, ValueError):
            settings.parallel_transfers = 1
        settings.parallel_transfers = max(
            MIN_PARALLEL_TRANSFERS,
            min(settings.parallel_transfers, MAX_PARALLEL_TRANSFERS),
        )
        language = str(raw.get("language") or settings.language)
        settings.language = language if language in TRANSLATIONS else LANG_RU
        settings.identity_file = str(raw.get("identity_file") or "")
        settings.save_password = bool(raw.get("save_password", False))
        settings.credential_key = str(raw.get("credential_key") or "")
        settings.sources = [
            item
            for item in (
                TransferItem.from_config(source, settings.remote_path)
                for source in raw.get("sources", [])
            )
            if item is not None
        ]
        return settings

    def save(self) -> None:
        payload = {
            "host": self.host,
            "username": self.username,
            "port": self.port,
            "remote_path": self.remote_path,
            "auth_method": self.auth_method,
            "transfer_engine": self.transfer_engine,
            "parallel_transfers": self.parallel_transfers,
            "language": self.language,
            "identity_file": self.identity_file,
            "save_password": self.save_password,
            "credential_key": self.credential_key,
            "sources": [source.to_config() for source in self.sources],
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
        self.current_process: subprocess.Popen[bytes] | None = None
        self.ssh_path = find_windows_openssh("ssh")
        self.transfer_progress = TransferProgress()
        self.child_runners: list[SftpRunner] = []
        self.child_lock = threading.Lock()

    def stop(self) -> None:
        self.cancel_event.set()
        if self.current_process and self.current_process.poll() is None:
            self.current_process.terminate()
        with self.child_lock:
            children = list(self.child_runners)
        for child in children:
            child.stop()

    def _emit(self, level: str, text: str) -> None:
        self.log.put((level, text))

    def register_child(self, child: "SftpRunner") -> None:
        with self.child_lock:
            self.child_runners.append(child)

    def unregister_child(self, child: "SftpRunner") -> None:
        with self.child_lock:
            if child in self.child_runners:
                self.child_runners.remove(child)

    def start_transfer_progress(self, total_bytes: int) -> None:
        self.transfer_progress = TransferProgress(total_bytes=total_bytes, started_at=time.monotonic())

    def progress_snapshot(self, task: UploadTask, current_file_bytes: int) -> tuple[int, float, int]:
        with self.transfer_progress.lock:
            self.transfer_progress.active_bytes[id(task)] = current_file_bytes
            total_sent = self.transfer_progress.completed_bytes + sum(self.transfer_progress.active_bytes.values())
            started_at = self.transfer_progress.started_at
            total_bytes = self.transfer_progress.total_bytes
        return total_sent, started_at, total_bytes

    def mark_task_completed(self, task: UploadTask) -> None:
        with self.transfer_progress.lock:
            self.transfer_progress.active_bytes.pop(id(task), None)
            self.transfer_progress.completed_bytes += task.size

    def clear_task_progress(self, task: UploadTask) -> None:
        with self.transfer_progress.lock:
            self.transfer_progress.active_bytes.pop(id(task), None)

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
        transport = client.get_transport()
        if transport is None:
            raise RuntimeError("SSH transport is not available")
        self.sftp = paramiko.SFTPClient.from_transport(
            transport,
            window_size=SFTP_WINDOW_SIZE,
            max_packet_size=SFTP_MAX_PACKET_SIZE,
        )

    def describe_connection_error(self, settings: Settings, error: Exception) -> str:
        if isinstance(error, socket.gaierror):
            return self.tr("error_host_not_found", host=settings.host)
        return str(error)

    def test_connection(self, settings: Settings, secret: str) -> bool:
        if settings.transfer_engine == ENGINE_OPENSSH:
            try:
                output = self.run_openssh(settings, "echo DeckShare connection ok")
                if output:
                    self._emit("output", output)
                self._emit("success", self.tr("success_connection"))
                return True
            except Exception as exc:  # noqa: BLE001 - surface connection errors in UI.
                self._emit("error", self.tr("error_connect_failed", error=self.describe_connection_error(settings, exc)))
                return False

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
            self._emit("error", self.tr("error_connect_failed", error=self.describe_connection_error(settings, exc)))
            return False
        finally:
            self.close()

    def transfer(self, settings: Settings, secret: str) -> bool:
        if settings.transfer_engine == ENGINE_OPENSSH:
            return self.transfer_openssh(settings)

        if not settings.sources:
            self._emit("error", self.tr("error_no_sources"))
            return False

        valid_sources = [source for source in settings.sources if Path(source.local_path).is_dir()]
        missing = [source for source in settings.sources if source not in valid_sources]
        for source in missing:
            self._emit("error", self.tr("error_missing_folder", source=source.local_path))

        if not valid_sources:
            return False

        try:
            self.connect(settings, secret)
            assert self.sftp is not None
            for source in valid_sources:
                self.ensure_remote_dir(source.remote_path)
        except Exception as exc:  # noqa: BLE001 - surface connection/setup errors in UI.
            self._emit("error", self.tr("error_prepare_failed", error=self.describe_connection_error(settings, exc)))
            self.close()
            return False

        try:
            total = len(valid_sources)
            skipped = 0
            upload_tasks: list[UploadTask] = []
            for index, source in enumerate(valid_sources, start=1):
                if self.cancel_event.is_set():
                    self._emit("error", self.tr("error_stopped"))
                    return False

                source_path = Path(source.local_path)
                name = source_path.name
                remote_root = source.remote_path
                self._emit("info", self.tr("log_processing_folder", index=index, total=total, name=name))
                source_tasks, source_skipped = self.build_upload_tasks(source_path, remote_root)
                upload_tasks.extend(source_tasks)
                skipped += source_skipped

            self.start_transfer_progress(sum(task.size for task in upload_tasks))
            uploaded = self.upload_tasks_paramiko(settings, secret, upload_tasks)

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

    def remote_stat(self, remote_path: str):
        assert self.sftp is not None
        try:
            return self.sftp.stat(remote_path)
        except OSError:
            return None

    def local_sha256(self, local_path: Path) -> str:
        digest = hashlib.sha256()
        with local_path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def remote_sha256(self, remote_path: str) -> str | None:
        assert self.client is not None
        command = f"sha256sum -- {quote_posix(remote_path)}"
        _, stdout, stderr = self.client.exec_command(command)
        output = stdout.read().decode("utf-8", errors="replace").strip()
        stderr.read()
        if stdout.channel.recv_exit_status() != 0 or not output:
            return None
        return output.split()[0].lower()

    def remove_remote_file(self, remote_path: str) -> None:
        assert self.sftp is not None
        try:
            self.sftp.remove(remote_path)
        except OSError:
            pass

    def replace_remote_file(self, temp_path: str, final_path: str) -> None:
        assert self.sftp is not None
        try:
            self.sftp.posix_rename(temp_path, final_path)
            return
        except (AttributeError, OSError):
            pass

        self.remove_remote_file(final_path)
        self.sftp.rename(temp_path, final_path)

    def openssh_args(self, settings: Settings) -> list[str]:
        if not Path(self.ssh_path).exists():
            raise RuntimeError(self.tr("error_openssh_missing", name="ssh.exe"))

        args = [
            self.ssh_path,
            "-p",
            str(settings.port),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]
        if settings.identity_file:
            args.extend(["-i", settings.identity_file])
        args.append(f"{settings.username}@{settings.host}")
        return args

    def run_openssh(self, settings: Settings, command: str) -> str:
        try:
            result = subprocess.run(
                self.openssh_args(settings) + [command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception as exc:  # noqa: BLE001 - show subprocess failures in UI.
            raise RuntimeError(self.tr("error_openssh_command_failed", error=exc)) from exc

        if result.returncode != 0:
            error = (result.stderr or result.stdout).strip() or f"exit code {result.returncode}"
            raise RuntimeError(self.tr("error_openssh_command_failed", error=error))
        return result.stdout.strip()

    def ensure_remote_dir_openssh(self, settings: Settings, remote_path: str) -> None:
        self.run_openssh(settings, f"mkdir -p -- {quote_posix(remote_path)}")

    def remote_stat_openssh(self, settings: Settings, remote_path: str) -> int | None:
        output = self.run_openssh(
            settings,
            f"if [ -e {quote_posix(remote_path)} ]; then stat -c %s -- {quote_posix(remote_path)}; fi",
        )
        if not output:
            return None
        try:
            return int(output.splitlines()[-1])
        except ValueError:
            return None

    def remote_sha256_openssh(self, settings: Settings, remote_path: str) -> str | None:
        output = self.run_openssh(settings, f"sha256sum -- {quote_posix(remote_path)}")
        return output.split()[0].lower() if output else None

    def remove_remote_file_openssh(self, settings: Settings, remote_path: str) -> None:
        self.run_openssh(settings, f"rm -f -- {quote_posix(remote_path)}")

    def replace_remote_file_openssh(self, settings: Settings, temp_path: str, final_path: str) -> None:
        self.run_openssh(settings, f"mv -f -- {quote_posix(temp_path)} {quote_posix(final_path)}")

    def bounded_parallelism(self, settings: Settings, task_count: int) -> int:
        return max(
            MIN_PARALLEL_TRANSFERS,
            min(settings.parallel_transfers, task_count, MAX_PARALLEL_TRANSFERS),
        )

    def transfer_openssh(self, settings: Settings) -> bool:
        if settings.auth_method != AUTH_KEY:
            self._emit("error", self.tr("error_openssh_key_required"))
            return False

        if not settings.sources:
            self._emit("error", self.tr("error_no_sources"))
            return False

        valid_sources = [source for source in settings.sources if Path(source.local_path).is_dir()]
        missing = [source for source in settings.sources if source not in valid_sources]
        for source in missing:
            self._emit("error", self.tr("error_missing_folder", source=source.local_path))

        if not valid_sources:
            return False

        try:
            for source in valid_sources:
                self.ensure_remote_dir_openssh(settings, source.remote_path)

            total = len(valid_sources)
            skipped = 0
            upload_tasks: list[UploadTask] = []
            for index, source in enumerate(valid_sources, start=1):
                if self.cancel_event.is_set():
                    self._emit("error", self.tr("error_stopped"))
                    return False

                source_path = Path(source.local_path)
                name = source_path.name
                remote_root = source.remote_path
                self._emit("info", self.tr("log_processing_folder", index=index, total=total, name=name))
                source_tasks, source_skipped = self.build_upload_tasks_openssh(settings, source_path, remote_root)
                upload_tasks.extend(source_tasks)
                skipped += source_skipped

            self.start_transfer_progress(sum(task.size for task in upload_tasks))
            uploaded = self.upload_tasks_openssh(settings, upload_tasks)

            self._emit("success", self.tr("success_transfer", uploaded=uploaded, skipped=skipped))
            return True
        except Exception as exc:  # noqa: BLE001 - surface transfer errors in UI.
            self._emit("error", self.tr("error_transfer_failed", error=exc))
            return False

    def build_upload_tasks(self, source_root: Path, remote_root: str) -> tuple[list[UploadTask], int]:
        assert self.sftp is not None
        tasks: list[UploadTask] = []
        skipped = 0
        self.ensure_remote_dir(remote_root)

        for local_dir, dir_names, file_names in os.walk(source_root):
            if self.cancel_event.is_set():
                return tasks, skipped

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
                    return tasks, skipped

                local_file = Path(local_dir) / file_name
                remote_file = posixpath.join(remote_dir, file_name)
                temp_file = f"{remote_file}.deckshare-part"
                file_size = local_file.stat().st_size
                remote_attrs = self.remote_stat(remote_file)

                if remote_attrs is not None:
                    if remote_attrs.st_size == file_size:
                        skipped += 1
                        self._emit("output", self.tr("log_skipped", path=remote_file))
                        continue

                    self._emit(
                        "info",
                        self.tr("log_reuploading", path=remote_file, reason=self.tr("log_reuploading_size")),
                    )

                tasks.append(
                    UploadTask(
                        local_path=local_file,
                        remote_path=remote_file,
                        temp_path=temp_file,
                        size=file_size,
                    )
                )

        return tasks, skipped

    def upload_tasks_paramiko(self, settings: Settings, secret: str, upload_tasks: list[UploadTask]) -> int:
        if not upload_tasks:
            return 0

        parallelism = self.bounded_parallelism(settings, len(upload_tasks))
        if parallelism == 1:
            uploaded = 0
            for task in upload_tasks:
                if self.cancel_event.is_set():
                    raise RuntimeError(self.tr("error_stopped"))
                self.upload_file(task)
                uploaded += 1
            return uploaded

        self.close()

        def worker(task: UploadTask) -> int:
            child = SftpRunner(self.log, self.cancel_event, self.tr)
            child.transfer_progress = self.transfer_progress
            self.register_child(child)
            try:
                child.connect(settings, secret)
                child.upload_file(task)
                return 1
            finally:
                child.close()
                self.unregister_child(child)

        uploaded = 0
        with ThreadPoolExecutor(max_workers=parallelism) as executor:
            futures = [executor.submit(worker, task) for task in upload_tasks]
            for future in as_completed(futures):
                if self.cancel_event.is_set():
                    for pending in futures:
                        pending.cancel()
                    raise RuntimeError(self.tr("error_stopped"))
                try:
                    uploaded += future.result()
                except Exception:
                    self.cancel_event.set()
                    for pending in futures:
                        pending.cancel()
                    raise
        return uploaded

    def upload_file(self, task: UploadTask) -> None:
        assert self.sftp is not None
        self.remove_remote_file(task.temp_path)
        started_at = time.monotonic()
        last_progress_at = 0.0

        def progress_callback(sent_bytes: int, total_bytes: int) -> None:
            nonlocal last_progress_at
            if self.cancel_event.is_set():
                raise RuntimeError(self.tr("error_stopped"))

            now = time.monotonic()
            total = total_bytes or task.size
            if now - last_progress_at < 1 and sent_bytes < total:
                return

            elapsed = max(now - started_at, 0.001)
            current_speed = sent_bytes / elapsed
            total_sent, transfer_started_at, transfer_total_bytes = self.progress_snapshot(task, sent_bytes)
            overall_elapsed = max(now - transfer_started_at, 0.001)
            overall_speed = total_sent / overall_elapsed if total_sent else 0
            file_eta = format_duration((total - sent_bytes) / current_speed) if current_speed > 0 else "--"
            total_remaining = max(transfer_total_bytes - total_sent, 0)
            total_eta = format_duration(total_remaining / overall_speed) if overall_speed > 0 else "--"
            speed = format_transfer_speed(current_speed)
            percent = format_transfer_percent(sent_bytes, total)
            self._emit(
                "progress",
                self.tr(
                    "log_uploading",
                    path=task.remote_path,
                    percent=percent,
                    speed=speed,
                    file_eta=file_eta,
                    total_eta=total_eta,
                ),
            )
            last_progress_at = now

        try:
            progress_callback(0, task.size)
            self.sftp.put(str(task.local_path), task.temp_path, callback=progress_callback)
            upload_elapsed = max(time.monotonic() - started_at, 0.001)
            self._emit("output", self.tr("log_hashing", path=task.temp_path))
            if self.cancel_event.is_set():
                raise RuntimeError(self.tr("error_stopped"))
            temp_attrs = self.remote_stat(task.temp_path)
            local_hash = self.local_sha256(task.local_path)
            if self.cancel_event.is_set():
                raise RuntimeError(self.tr("error_stopped"))
            temp_hash = self.remote_sha256(task.temp_path)
            if self.cancel_event.is_set():
                raise RuntimeError(self.tr("error_stopped"))
            if temp_attrs is None or temp_attrs.st_size != task.size or temp_hash != local_hash:
                self.remove_remote_file(task.temp_path)
                raise RuntimeError(self.tr("error_upload_verify_failed", path=task.remote_path))

            self.replace_remote_file(task.temp_path, task.remote_path)
        except Exception:
            self.remove_remote_file(task.temp_path)
            self.clear_task_progress(task)
            raise

        self.mark_task_completed(task)
        speed = format_transfer_speed(task.size / upload_elapsed)
        self._emit("output", self.tr("log_uploaded", path=task.remote_path, speed=speed))

    def build_upload_tasks_openssh(
        self,
        settings: Settings,
        source_root: Path,
        remote_root: str,
    ) -> tuple[list[UploadTask], int]:
        tasks: list[UploadTask] = []
        skipped = 0
        self.ensure_remote_dir_openssh(settings, remote_root)

        for local_dir, dir_names, file_names in os.walk(source_root):
            if self.cancel_event.is_set():
                return tasks, skipped

            dir_names.sort()
            file_names.sort()
            relative_dir = Path(local_dir).relative_to(source_root)
            remote_dir = remote_root if str(relative_dir) == "." else posixpath.join(
                remote_root,
                relative_dir.as_posix(),
            )
            self.ensure_remote_dir_openssh(settings, remote_dir)

            for file_name in file_names:
                if self.cancel_event.is_set():
                    return tasks, skipped

                local_file = Path(local_dir) / file_name
                remote_file = posixpath.join(remote_dir, file_name)
                temp_file = f"{remote_file}.deckshare-part"
                file_size = local_file.stat().st_size
                remote_size = self.remote_stat_openssh(settings, remote_file)

                if remote_size is not None:
                    if remote_size == file_size:
                        skipped += 1
                        self._emit("output", self.tr("log_skipped", path=remote_file))
                        continue

                    self._emit(
                        "info",
                        self.tr("log_reuploading", path=remote_file, reason=self.tr("log_reuploading_size")),
                    )

                tasks.append(
                    UploadTask(
                        local_path=local_file,
                        remote_path=remote_file,
                        temp_path=temp_file,
                        size=file_size,
                    )
                )

        return tasks, skipped

    def upload_tasks_openssh(self, settings: Settings, upload_tasks: list[UploadTask]) -> int:
        if not upload_tasks:
            return 0

        parallelism = self.bounded_parallelism(settings, len(upload_tasks))
        if parallelism == 1:
            uploaded = 0
            for task in upload_tasks:
                if self.cancel_event.is_set():
                    raise RuntimeError(self.tr("error_stopped"))
                self.upload_file_openssh(settings, task)
                uploaded += 1
            return uploaded

        def worker(task: UploadTask) -> int:
            child = SftpRunner(self.log, self.cancel_event, self.tr)
            child.transfer_progress = self.transfer_progress
            self.register_child(child)
            try:
                child.upload_file_openssh(settings, task)
                return 1
            finally:
                self.unregister_child(child)

        uploaded = 0
        with ThreadPoolExecutor(max_workers=parallelism) as executor:
            futures = [executor.submit(worker, task) for task in upload_tasks]
            for future in as_completed(futures):
                if self.cancel_event.is_set():
                    for pending in futures:
                        pending.cancel()
                    raise RuntimeError(self.tr("error_stopped"))
                try:
                    uploaded += future.result()
                except Exception:
                    self.cancel_event.set()
                    for pending in futures:
                        pending.cancel()
                    raise
        return uploaded

    def upload_file_openssh(self, settings: Settings, task: UploadTask) -> None:
        self.remove_remote_file_openssh(settings, task.temp_path)
        started_at = time.monotonic()
        last_progress_at = 0.0
        sent_bytes = 0
        digest = hashlib.sha256()
        command = f"cat > {quote_posix(task.temp_path)}"
        self.current_process = subprocess.Popen(
            self.openssh_args(settings) + [command],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        assert self.current_process.stdin is not None

        def emit_progress(force: bool = False) -> None:
            nonlocal last_progress_at
            now = time.monotonic()
            if not force and now - last_progress_at < 1 and sent_bytes < task.size:
                return

            elapsed = max(now - started_at, 0.001)
            current_speed = sent_bytes / elapsed
            total_sent, transfer_started_at, transfer_total_bytes = self.progress_snapshot(task, sent_bytes)
            overall_elapsed = max(now - transfer_started_at, 0.001)
            overall_speed = total_sent / overall_elapsed if total_sent else 0
            file_eta = format_duration((task.size - sent_bytes) / current_speed) if current_speed > 0 else "--"
            total_remaining = max(transfer_total_bytes - total_sent, 0)
            total_eta = format_duration(total_remaining / overall_speed) if overall_speed > 0 else "--"
            speed = format_transfer_speed(current_speed)
            percent = format_transfer_percent(sent_bytes, task.size)
            self._emit(
                "progress",
                self.tr(
                    "log_uploading",
                    path=task.remote_path,
                    percent=percent,
                    speed=speed,
                    file_eta=file_eta,
                    total_eta=total_eta,
                ),
            )
            last_progress_at = now

        try:
            emit_progress(force=True)
            with task.local_path.open("rb") as file:
                for chunk in iter(lambda: file.read(1024 * 1024), b""):
                    if self.cancel_event.is_set():
                        self.current_process.terminate()
                        raise RuntimeError(self.tr("error_stopped"))
                    digest.update(chunk)
                    self.current_process.stdin.write(chunk)
                    sent_bytes += len(chunk)
                    emit_progress()
            self.current_process.stdin.close()
            stdout = self.current_process.stdout.read() if self.current_process.stdout else b""
            stderr = self.current_process.stderr.read() if self.current_process.stderr else b""
            return_code = self.current_process.wait()
        except Exception:
            if self.current_process and self.current_process.poll() is None:
                self.current_process.terminate()
                self.current_process.wait(timeout=5)
            try:
                self.remove_remote_file_openssh(settings, task.temp_path)
            except Exception:
                pass
            self.clear_task_progress(task)
            raise
        finally:
            self.current_process = None

        try:
            if return_code != 0:
                error = (stderr or stdout).decode("utf-8", errors="replace").strip() or f"exit code {return_code}"
                raise RuntimeError(self.tr("error_openssh_command_failed", error=error))

            emit_progress(force=True)
            upload_elapsed = max(time.monotonic() - started_at, 0.001)
            self._emit("output", self.tr("log_hashing", path=task.temp_path))
            if self.cancel_event.is_set():
                raise RuntimeError(self.tr("error_stopped"))
            temp_size = self.remote_stat_openssh(settings, task.temp_path)
            temp_hash = self.remote_sha256_openssh(settings, task.temp_path)
            if self.cancel_event.is_set():
                raise RuntimeError(self.tr("error_stopped"))
            if temp_size != task.size or temp_hash != digest.hexdigest():
                raise RuntimeError(self.tr("error_upload_verify_failed", path=task.remote_path))

            self.replace_remote_file_openssh(settings, task.temp_path, task.remote_path)
        except Exception:
            try:
                self.remove_remote_file_openssh(settings, task.temp_path)
            except Exception:
                pass
            self.clear_task_progress(task)
            raise

        self.mark_task_completed(task)
        speed = format_transfer_speed(task.size / upload_elapsed)
        self._emit("output", self.tr("log_uploaded", path=task.remote_path, speed=speed))


class DeckShareApp(ttk.Frame):
    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root, padding=16)
        self.root = root
        self.settings = Settings.load()
        self.messages: queue.Queue[tuple[str, str]] = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.localized_widgets: list[tuple[tk.Widget, str]] = []
        self.source_items: list[TransferItem] = list(self.settings.sources)
        self.stored_credential_key = self.settings.credential_key

        self.host_var = tk.StringVar(value=self.settings.host)
        self.user_var = tk.StringVar(value=self.settings.username)
        self.port_var = tk.StringVar(value=str(self.settings.port))
        self.remote_path_var = tk.StringVar(value=self.settings.remote_path)
        self.selected_remote_path_var = tk.StringVar(value="")
        self.auth_method_var = tk.StringVar(value=self.settings.auth_method)
        self.transfer_engine_var = tk.StringVar(value=self.settings.transfer_engine)
        self.parallel_transfers_var = tk.StringVar(value=str(self.settings.parallel_transfers))
        self.language_var = tk.StringVar(value=self.settings.language)
        self.identity_var = tk.StringVar(value=self.settings.identity_file)
        self.password_var = tk.StringVar(value="")
        self.save_password_var = tk.BooleanVar(value=self.settings.save_password)
        self.status_var = tk.StringVar(value=self.tr("status_ready"))
        self.runner = SftpRunner(self.messages, self.cancel_event, self.make_translator(self.settings.language))

        self._configure_root()
        self._build()
        self._load_sources()
        self.update_auth_fields()
        self.apply_language()
        self.load_saved_password()
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
        self._entry(self.settings_box, "remote_path_default", self.remote_path_var, 3)

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

        self.save_password_check = ttk.Checkbutton(
            self.settings_box,
            text=self.tr("save_password"),
            variable=self.save_password_var,
            command=self.handle_save_password_toggle,
        )
        self.save_password_check.grid(row=6, column=1, sticky="w", padx=12, pady=6)
        self.localized_widgets.append((self.save_password_check, "save_password"))

        self.identity_label = ttk.Label(self.settings_box, text=self.tr("identity"))
        self.identity_label.grid(row=7, column=0, sticky="w", padx=12, pady=6)
        self.localized_widgets.append((self.identity_label, "identity"))
        key_row = ttk.Frame(self.settings_box)
        key_row.grid(row=7, column=1, sticky="ew", padx=12, pady=6)
        key_row.columnconfigure(0, weight=1)
        self.identity_entry = ttk.Entry(key_row, textvariable=self.identity_var)
        self.identity_entry.grid(row=0, column=0, sticky="ew")
        self.identity_button = ttk.Button(key_row, text="...", width=4, command=self.choose_identity)
        self.identity_button.grid(row=0, column=1, padx=(6, 0))

        self.transfer_engine_label = ttk.Label(self.settings_box, text=self.tr("transfer_engine"))
        self.transfer_engine_label.grid(row=8, column=0, sticky="w", padx=12, pady=6)
        self.localized_widgets.append((self.transfer_engine_label, "transfer_engine"))
        engine_row = ttk.Frame(self.settings_box)
        engine_row.grid(row=8, column=1, sticky="ew", padx=12, pady=6)
        self.engine_paramiko_radio = ttk.Radiobutton(
            engine_row,
            text=self.tr("engine_paramiko"),
            value=ENGINE_PARAMIKO,
            variable=self.transfer_engine_var,
            command=self.update_auth_fields,
        )
        self.engine_paramiko_radio.grid(row=0, column=0, sticky="w")
        self.localized_widgets.append((self.engine_paramiko_radio, "engine_paramiko"))
        self.engine_openssh_radio = ttk.Radiobutton(
            engine_row,
            text=self.tr("engine_fast"),
            value=ENGINE_OPENSSH,
            variable=self.transfer_engine_var,
            command=self.update_auth_fields,
        )
        self.engine_openssh_radio.grid(row=0, column=1, sticky="w", padx=(16, 0))
        self.localized_widgets.append((self.engine_openssh_radio, "engine_fast"))

        self.parallel_transfers_label = ttk.Label(self.settings_box, text=self.tr("parallel_transfers"))
        self.parallel_transfers_label.grid(row=9, column=0, sticky="w", padx=12, pady=6)
        self.localized_widgets.append((self.parallel_transfers_label, "parallel_transfers"))
        self.parallel_transfers_spin = ttk.Spinbox(
            self.settings_box,
            from_=MIN_PARALLEL_TRANSFERS,
            to=MAX_PARALLEL_TRANSFERS,
            textvariable=self.parallel_transfers_var,
            width=6,
            command=self.save_settings,
        )
        self.parallel_transfers_spin.grid(row=9, column=1, sticky="w", padx=12, pady=6)

        self.source_box = ttk.LabelFrame(self, text=self.tr("group_sources"))
        self.source_box.grid(row=1, column=1, rowspan=2, sticky="nsew")
        self.source_box.columnconfigure(0, weight=1)
        self.source_box.rowconfigure(0, weight=1)
        self.localized_widgets.append((self.source_box, "group_sources"))

        self.source_list = tk.Listbox(self.source_box, height=10, activestyle="none", exportselection=False)
        self.source_list.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=12)
        self.source_list.bind("<<ListboxSelect>>", self.update_selected_source_path)
        source_scroll = ttk.Scrollbar(self.source_box, orient="vertical", command=self.source_list.yview)
        source_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 12), pady=12)
        self.source_list.configure(yscrollcommand=source_scroll.set)

        selected_path_row = ttk.Frame(self.source_box)
        selected_path_row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))
        selected_path_row.columnconfigure(1, weight=1)
        self.selected_remote_path_label = ttk.Label(selected_path_row, text=self.tr("selected_remote_path"))
        self.selected_remote_path_label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.localized_widgets.append((self.selected_remote_path_label, "selected_remote_path"))
        self.selected_remote_path_entry = ttk.Entry(selected_path_row, textvariable=self.selected_remote_path_var)
        self.selected_remote_path_entry.grid(row=0, column=1, sticky="ew")
        self.apply_remote_path_button = ttk.Button(
            selected_path_row,
            text=self.tr("apply_remote_path"),
            command=self.apply_selected_remote_path,
        )
        self.apply_remote_path_button.grid(row=0, column=2, sticky="ew", padx=(8, 0))
        self.localized_widgets.append((self.apply_remote_path_button, "apply_remote_path"))

        source_buttons = ttk.Frame(self.source_box)
        source_buttons.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))
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

    def load_saved_password(self) -> None:
        if (
            not self.settings.save_password
            or self.settings.auth_method != AUTH_PASSWORD
            or not self.settings.credential_key
        ):
            return

        try:
            keyring = require_keyring(self.tr)
            saved_password = keyring.get_password(KEYRING_SERVICE, self.settings.credential_key)
        except Exception as exc:  # noqa: BLE001 - keyring backends raise different exceptions.
            self.messages.put(("error", self.tr("error_keyring_read_failed", error=exc)))
            return

        if saved_password:
            self.password_var.set(saved_password)
            self.messages.put(("info", self.tr("log_password_loaded")))

    def handle_save_password_toggle(self) -> None:
        if self.save_password_var.get():
            self.save_settings()
            return

        settings = self.collect_settings(validate_auth=False)
        if settings is None:
            return
        self.delete_saved_password()
        settings.save_password = False
        settings.credential_key = ""
        settings.save()

    def delete_saved_password(self) -> None:
        if not self.stored_credential_key:
            return

        try:
            keyring = require_keyring(self.tr)
            keyring.delete_password(KEYRING_SERVICE, self.stored_credential_key)
            self.messages.put(("info", self.tr("log_password_deleted")))
        except Exception:
            pass
        finally:
            self.stored_credential_key = ""

    def persist_password_preference(self, settings: Settings, secret: str) -> bool:
        if settings.auth_method != AUTH_PASSWORD or not settings.save_password:
            self.delete_saved_password()
            settings.save_password = False
            settings.credential_key = ""
            return True

        try:
            keyring = require_keyring(self.tr)
            credential_key = credential_key_for(settings)
            keyring.set_password(KEYRING_SERVICE, credential_key, secret)
            if self.stored_credential_key and self.stored_credential_key != credential_key:
                try:
                    keyring.delete_password(KEYRING_SERVICE, self.stored_credential_key)
                except Exception:
                    pass
            settings.credential_key = credential_key
            self.stored_credential_key = credential_key
            self.messages.put(("info", self.tr("log_password_saved")))
            return True
        except Exception as exc:  # noqa: BLE001 - keyring backends raise different exceptions.
            messagebox.showerror(APP_NAME, self.tr("error_keyring_save_failed", error=exc))
            return False

    def update_auth_fields(self) -> None:
        is_key = self.auth_method_var.get() == AUTH_KEY
        if is_key:
            self.password_label.configure(text=self.tr("passphrase"))
            self.identity_entry.configure(state="normal")
            self.identity_button.configure(state="normal")
            self.save_password_check.configure(state="disabled")
            self.engine_openssh_radio.configure(state="normal")
        else:
            if self.transfer_engine_var.get() == ENGINE_OPENSSH:
                self.transfer_engine_var.set(ENGINE_PARAMIKO)
            self.password_label.configure(text=self.tr("password"))
            self.identity_entry.configure(state="disabled")
            self.identity_button.configure(state="disabled")
            self.save_password_check.configure(state="normal")
            self.engine_openssh_radio.configure(state="disabled")

    def _load_sources(self) -> None:
        self.refresh_source_list()

    def format_source_item(self, item: TransferItem) -> str:
        return f"{item.local_path}  ->  {item.remote_path}"

    def refresh_source_list(self, selected_index: int | None = None) -> None:
        self.source_list.delete(0, "end")
        for item in self.source_items:
            self.source_list.insert("end", self.format_source_item(item))

        if selected_index is not None and self.source_items:
            index = min(selected_index, len(self.source_items) - 1)
            self.source_list.selection_set(index)
            self.source_list.activate(index)
            self.source_list.see(index)
        self.update_selected_source_path()

    def update_selected_source_path(self, _event: tk.Event | None = None) -> None:
        selected = self.source_list.curselection()
        if not selected:
            self.selected_remote_path_var.set("")
            return
        self.selected_remote_path_var.set(self.source_items[selected[0]].remote_path)

    def apply_selected_remote_path(self) -> None:
        self.sync_selected_remote_path()
        selected = self.source_list.curselection()
        self.refresh_source_list(selected[0] if selected else None)
        self.save_settings()

    def sync_selected_remote_path(self) -> None:
        selected = self.source_list.curselection()
        if not selected:
            return

        index = selected[0]
        self.source_items[index].remote_path = normalize_remote_path(self.selected_remote_path_var.get())
        self.selected_remote_path_var.set(self.source_items[index].remote_path)

    def add_source(self) -> None:
        selected = filedialog.askdirectory(title=self.tr("dialog_select_dir"))
        if not selected:
            return
        normalized = str(Path(selected))
        existing = {source.local_path for source in self.source_items}
        if normalized not in existing:
            self.source_items.append(
                TransferItem(
                    local_path=normalized,
                    remote_path=normalize_remote_path(self.remote_path_var.get()),
                )
            )
            self.refresh_source_list(len(self.source_items) - 1)
            self.save_settings()

    def remove_source(self) -> None:
        selected = list(self.source_list.curselection())
        selected.reverse()
        for index in selected:
            del self.source_items[index]
        self.refresh_source_list(selected[-1] if selected else None)
        self.save_settings()

    def clear_sources(self) -> None:
        self.source_items.clear()
        self.refresh_source_list()
        self.save_settings()

    def choose_identity(self) -> None:
        selected = filedialog.askopenfilename(title=self.tr("dialog_select_key"))
        if selected:
            self.identity_var.set(selected)
            self.save_settings()

    def collect_settings(self, validate_auth: bool = True) -> Settings | None:
        self.sync_selected_remote_path()

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
        transfer_engine = self.transfer_engine_var.get()
        if transfer_engine not in {ENGINE_PARAMIKO, ENGINE_OPENSSH}:
            transfer_engine = ENGINE_PARAMIKO
        try:
            parallel_transfers = int(self.parallel_transfers_var.get().strip())
        except ValueError:
            parallel_transfers = 1
        parallel_transfers = max(MIN_PARALLEL_TRANSFERS, min(parallel_transfers, MAX_PARALLEL_TRANSFERS))
        self.parallel_transfers_var.set(str(parallel_transfers))

        if validate_auth and auth_method == AUTH_KEY and transfer_engine != ENGINE_OPENSSH and not identity_file:
            messagebox.showerror(APP_NAME, self.tr("error_auth_key_missing"))
            return None

        if validate_auth and auth_method == AUTH_KEY and identity_file and not Path(identity_file).is_file():
            messagebox.showerror(APP_NAME, self.tr("error_identity_missing"))
            return None

        if validate_auth and transfer_engine == ENGINE_OPENSSH and auth_method != AUTH_KEY:
            messagebox.showerror(APP_NAME, self.tr("error_openssh_key_required"))
            return None

        should_save_password = self.save_password_var.get() if auth_method == AUTH_PASSWORD else False

        return Settings(
            host=host,
            username=username,
            port=port,
            remote_path=normalize_remote_path(self.remote_path_var.get()),
            auth_method=auth_method,
            transfer_engine=transfer_engine,
            parallel_transfers=parallel_transfers,
            language=self.language_var.get() if self.language_var.get() in TRANSLATIONS else LANG_RU,
            identity_file=identity_file,
            save_password=should_save_password,
            credential_key=self.stored_credential_key if should_save_password else "",
            sources=list(self.source_items),
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
        if not self.persist_password_preference(settings, secret):
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
        if not self.persist_password_preference(settings, secret):
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
                elif level == "progress":
                    self.status_var.set(text)
                    self.append_log("output", text)
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
