"""Download manager service for model files.

This service handles downloading large model files (ASR, NLU) with:
- Progress tracking
- Cancellation support
- Resume capability
- Event notifications for UI updates

Typical usage:
    manager = DownloadManager()

    # Start download
    manager.start_download(
        url="https://huggingface.co/...",
        dest_path="/path/to/model.gguf",
        name="Llama 3.2 3B",
    )

    # Check status
    status = manager.get_status()
    if status.in_progress:
        print(f"Downloading {status.name}: {status.progress}%")

    # Cancel if needed
    manager.cancel_download()
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class DownloadState(Enum):
    """Download state enumeration."""

    IDLE = auto()
    PENDING = auto()
    DOWNLOADING = auto()
    COMPLETED = auto()
    CANCELLED = auto()
    ERROR = auto()


@dataclass
class DownloadStatus:
    """Current download status.

    Attributes:
        state: Current download state.
        name: Human-readable name of the download.
        progress: Download progress (0-100).
        bytes_downloaded: Bytes downloaded so far.
        bytes_total: Total bytes to download.
        error_message: Error message if state is ERROR.
    """

    state: DownloadState = DownloadState.IDLE
    name: str = ""
    progress: int = 0
    bytes_downloaded: int = 0
    bytes_total: int = 0
    error_message: str = ""

    @property
    def in_progress(self) -> bool:
        """Check if download is in progress."""
        return self.state in (DownloadState.PENDING, DownloadState.DOWNLOADING)


@dataclass
class DownloadRequest:
    """Download request details.

    Attributes:
        url: URL to download from.
        dest_path: Destination file path.
        name: Human-readable name.
        headers: Optional HTTP headers.
    """

    url: str
    dest_path: str
    name: str
    headers: dict[str, str] = field(default_factory=dict)


class DownloadManager:
    """Manages model file downloads with progress tracking.

    This singleton service handles downloading large files in the background
    while providing progress updates and cancellation support.
    """

    _instance: "DownloadManager | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "DownloadManager":
        """Singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize the download manager."""
        if self._initialized:
            return

        self._status = DownloadStatus()
        self._current_request: DownloadRequest | None = None
        self._download_thread: threading.Thread | None = None
        self._cancel_requested = False
        self._callbacks: list[Callable[[DownloadStatus], None]] = []
        self._initialized = True

    def add_callback(self, callback: Callable[[DownloadStatus], None]) -> None:
        """Add a callback for status updates.

        Args:
            callback: Function called with DownloadStatus on updates.
        """
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[DownloadStatus], None]) -> None:
        """Remove a status callback.

        Args:
            callback: Callback to remove.
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify_callbacks(self) -> None:
        """Notify all registered callbacks of status change."""
        for callback in self._callbacks:
            try:
                callback(self._status)
            except Exception as e:
                logger.error(f"Error in download callback: {e}")

    def get_status(self) -> DownloadStatus:
        """Get current download status.

        Returns:
            Current DownloadStatus.
        """
        return self._status

    def start_download(
        self,
        url: str,
        dest_path: str,
        name: str,
        headers: dict[str, str] | None = None,
    ) -> bool:
        """Start a download.

        Args:
            url: URL to download from.
            dest_path: Where to save the file.
            name: Human-readable name for UI.
            headers: Optional HTTP headers (e.g., for auth).

        Returns:
            True if download started, False if already downloading.
        """
        if self._status.in_progress:
            logger.warning("Download already in progress")
            return False

        self._current_request = DownloadRequest(
            url=url,
            dest_path=dest_path,
            name=name,
            headers=headers or {},
        )

        self._cancel_requested = False
        self._status = DownloadStatus(
            state=DownloadState.PENDING,
            name=name,
        )
        self._notify_callbacks()

        self._download_thread = threading.Thread(
            target=self._download_worker,
            daemon=True,
        )
        self._download_thread.start()

        logger.info(f"Started download: {name} from {url}")
        return True

    def cancel_download(self) -> bool:
        """Cancel the current download.

        Returns:
            True if cancellation requested.
        """
        if not self._status.in_progress:
            return False

        self._cancel_requested = True
        logger.info(f"Cancellation requested for: {self._status.name}")
        return True

    def _download_worker(self) -> None:
        """Worker thread for downloading files."""
        if not self._current_request:
            return

        request = self._current_request
        dest_path = Path(request.dest_path)
        temp_path = dest_path.with_suffix(dest_path.suffix + ".partial")

        try:
            # Ensure directory exists
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Check for partial download to resume
            resume_pos = 0
            if temp_path.exists():
                resume_pos = temp_path.stat().st_size
                logger.info(f"Resuming download from byte {resume_pos}")

            # Prepare headers
            headers = dict(request.headers)
            if resume_pos > 0:
                headers["Range"] = f"bytes={resume_pos}-"

            # Start download
            response = requests.get(
                request.url,
                headers=headers,
                stream=True,
                timeout=30,
            )
            response.raise_for_status()

            # Get total size
            total_size = int(response.headers.get("content-length", 0))
            if resume_pos > 0:
                total_size += resume_pos

            self._status = DownloadStatus(
                state=DownloadState.DOWNLOADING,
                name=request.name,
                bytes_total=total_size,
                bytes_downloaded=resume_pos,
            )
            self._notify_callbacks()

            # Download with progress
            mode = "ab" if resume_pos > 0 else "wb"
            with open(temp_path, mode) as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self._cancel_requested:
                        logger.info("Download cancelled")
                        self._status = DownloadStatus(
                            state=DownloadState.CANCELLED,
                            name=request.name,
                        )
                        self._notify_callbacks()
                        return

                    if chunk:
                        f.write(chunk)
                        self._status.bytes_downloaded += len(chunk)
                        if total_size > 0:
                            self._status.progress = int(
                                100 * self._status.bytes_downloaded / total_size
                            )
                        self._notify_callbacks()

            # Move to final location
            temp_path.rename(dest_path)

            self._status = DownloadStatus(
                state=DownloadState.COMPLETED,
                name=request.name,
                progress=100,
                bytes_downloaded=total_size,
                bytes_total=total_size,
            )
            self._notify_callbacks()
            logger.info(f"Download completed: {request.name}")

        except requests.RequestException as e:
            logger.error(f"Download error: {e}")
            self._status = DownloadStatus(
                state=DownloadState.ERROR,
                name=request.name,
                error_message=str(e),
            )
            self._notify_callbacks()

        except Exception as e:
            logger.error(f"Unexpected download error: {e}")
            self._status = DownloadStatus(
                state=DownloadState.ERROR,
                name=request.name,
                error_message=str(e),
            )
            self._notify_callbacks()

    def delete_partial(self) -> bool:
        """Delete partial download file.

        Returns:
            True if file was deleted.
        """
        if not self._current_request:
            return False

        temp_path = Path(self._current_request.dest_path + ".partial")
        if temp_path.exists():
            temp_path.unlink()
            logger.info(f"Deleted partial download: {temp_path}")
            return True
        return False


def get_download_manager() -> DownloadManager:
    """Get the download manager singleton.

    Returns:
        DownloadManager instance.
    """
    return DownloadManager()


# Model URLs and configurations
LLAMA_MODELS = {
    "llama-3.2-1b-q4": {
        "url": "https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF/resolve/main/Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        "filename": "Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        "size_mb": 776,
        "name": "Llama 3.2 1B (Q4)",
    },
    "llama-3.2-3b-q4": {
        "url": "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "filename": "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "size_mb": 2020,
        "name": "Llama 3.2 3B (Q4)",
    },
    "llama-3.1-8b-q4": {
        "url": "https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
        "filename": "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
        "size_mb": 4920,
        "name": "Llama 3.1 8B (Q4)",
    },
}

# Default model for NLU
DEFAULT_NLU_MODEL = "llama-3.2-3b-q4"


def get_models_dir() -> Path:
    """Get the models directory path.

    Returns:
        Path to models directory (~/.airborne/models/).
    """
    models_dir = Path.home() / ".airborne" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir


def get_nlu_model_path(model_id: str = DEFAULT_NLU_MODEL) -> Path | None:
    """Get path to NLU model if it exists.

    Args:
        model_id: Model identifier.

    Returns:
        Path to model file, or None if not downloaded.
    """
    if model_id not in LLAMA_MODELS:
        return None

    model_info = LLAMA_MODELS[model_id]
    model_path = get_models_dir() / model_info["filename"]

    if model_path.exists():
        return model_path
    return None


def is_nlu_model_available(model_id: str = DEFAULT_NLU_MODEL) -> bool:
    """Check if NLU model is available.

    Args:
        model_id: Model identifier.

    Returns:
        True if model is downloaded and ready.
    """
    return get_nlu_model_path(model_id) is not None


def start_nlu_model_download(
    model_id: str = DEFAULT_NLU_MODEL,
    callback: Callable[[DownloadStatus], None] | None = None,
) -> bool:
    """Start downloading the NLU model.

    Args:
        model_id: Model identifier.
        callback: Optional progress callback.

    Returns:
        True if download started.
    """
    if model_id not in LLAMA_MODELS:
        logger.error(f"Unknown model: {model_id}")
        return False

    model_info = LLAMA_MODELS[model_id]
    dest_path = get_models_dir() / model_info["filename"]

    manager = get_download_manager()
    if callback:
        manager.add_callback(callback)

    return manager.start_download(
        url=model_info["url"],
        dest_path=str(dest_path),
        name=model_info["name"],
    )
