"""Runtime configuration, resolved from environment variables with local defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _path(env_var: str, default: str) -> Path:
    """Resolve an environment-configured path relative to the project root.

    Parameters
    ----------
    env_var : str
        Name of the environment variable to read.
    default : str
        Fallback path, relative to the project root.

    Returns
    -------
    Path
        Absolute path.
    """
    raw = os.getenv(env_var, default)
    p = Path(raw)
    return p if p.is_absolute() else PROJECT_ROOT / p


@dataclass(frozen=True)
class Settings:
    """Immutable filesystem layout for the pipeline."""

    input_dir: Path
    db_path: Path
    raw_dir: Path
    review_dir: Path
    config_dir: Path

    @classmethod
    def load(cls) -> Settings:
        """Build settings from the environment.

        Returns
        -------
        Settings
            Populated configuration object.
        """
        return cls(
            input_dir=_path("EXAMENES_INPUT_DIR", "input"),
            db_path=_path("EXAMENES_DB_PATH", "data/labs.duckdb"),
            raw_dir=_path("EXAMENES_RAW_DIR", "data/raw"),
            review_dir=_path("EXAMENES_REVIEW_DIR", "review"),
            config_dir=PROJECT_ROOT / "config",
        )

    def ensure_dirs(self) -> None:
        """Create the output directories if they do not yet exist."""
        for d in (self.db_path.parent, self.raw_dir, self.review_dir):
            d.mkdir(parents=True, exist_ok=True)


SETTINGS = Settings.load()
