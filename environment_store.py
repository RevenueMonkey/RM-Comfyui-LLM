"""User-level persistent environment values; never part of the node package."""
import json
import os
import stat
import sys
import tempfile
from pathlib import Path


def environment_file():
    directory = Path(os.environ.get("XDG_CONFIG_HOME", ""))
    if not directory.is_absolute():
        directory = Path.home() / ".config"
    return directory / "rm-llm" / "environment.json"


def read_environment_file(path):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return {}
    with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise PermissionError("Environment file must be owned by this user with mode 600.")
        if info.st_size > 1024 * 1024:
            raise ValueError("Environment file is too large.")
        values = json.load(stream)
    if not isinstance(values, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in values.items()):
        raise ValueError("Invalid environment file.")
    return values


def read_persistent_environment(name):
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as registry:
                value, kind = winreg.QueryValueEx(registry, name)
        except FileNotFoundError:
            return ""
        return value if kind in {winreg.REG_SZ, winreg.REG_EXPAND_SZ} and isinstance(value, str) else ""
    return read_environment_file(environment_file()).get(name, "")


def write_persistent_environment(name, value):
    if sys.platform == "win32":
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, "Environment", access=winreg.KEY_SET_VALUE) as registry:
            winreg.SetValueEx(registry, name, 0, winreg.REG_SZ, value)
        return
    path = environment_file()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise PermissionError("Environment directory must be owned by this user.")
    path.parent.chmod(0o700)
    values = read_environment_file(path)
    values[name] = value
    descriptor, temporary = tempfile.mkstemp(prefix=".environment-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(values, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
