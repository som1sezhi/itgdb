"""Path utilities."""

import os
from pathlib import Path, PureWindowsPath

# TODO: consider using pathlib instead of passing around paths as strings

def convert_path_to_os_style(path: str) -> str:
    """Convert a Windows or Posix-style path to the current OS-specific style"""
    return str(Path(PureWindowsPath(path)))


# https://stackoverflow.com/a/37708342
def find_case_sensitive_path(dir: str, insensitive_path: str) -> str | None:
    insensitive_path = os.path.normpath(insensitive_path)
    insensitive_path = insensitive_path.lstrip(os.path.sep)

    parts = insensitive_path.split(os.path.sep, 1)
    next_name = parts[0]
    for name in os.listdir(dir):
        if next_name.lower() == name.lower():
            improved_path = os.path.join(dir, name)
            if len(parts) == 1:
                return improved_path
            else:
                return find_case_sensitive_path(
                    improved_path, parts[1]
                )
    return None