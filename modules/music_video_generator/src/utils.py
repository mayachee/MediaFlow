import os
import logging
from pathlib import Path
from typing import List, Dict, Any

import yaml


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Load configuration from YAML file."""
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_input_files(directory: str, extensions: List[str]) -> List[Path]:
    """Get all files with specified extensions from directory."""
    input_dir = Path(directory)
    if not input_dir.exists():
        return []
    
    allowed = {ext.lower() for ext in extensions}
    return sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in allowed)


def setup_logging(log_level: str = "INFO") -> None:
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def ensure_output_dir(output_dir: str) -> Path:
    """Ensure output directory exists."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    return output_path
