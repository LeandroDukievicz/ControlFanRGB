"""Perfil salvo em ~/.config/pulsedeck/config.json."""
import json
import os

DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "pulsedeck")
PATH = os.path.join(DIR, "config.json")

DEFAULT = {
    "mode": "zones",                 # "zones" | "firmware" | "software"
    "zones": [[255, 45, 111], [177, 74, 237], [79, 124, 255], [45, 226, 255]],
    "theme": "Vapor",
    "firmware_mode": 3,              # onda
    "speed": 5,
    "direction": 1,
    "brightness": 100,
    "color": [45, 226, 255],
    "software_effect": "Arco-íris",
    "key_colors": {},
    "apply_on_start": True,
}


def load():
    cfg = dict(DEFAULT)
    try:
        with open(PATH) as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    cfg["zones"] = [tuple(c) for c in cfg["zones"]]
    cfg["key_colors"] = {k: tuple(v) for k, v in cfg.get("key_colors", {}).items()}
    cfg["color"] = tuple(cfg["color"])
    return cfg


def save(cfg):
    os.makedirs(DIR, exist_ok=True)
    serializable = dict(cfg)
    serializable["zones"] = [list(c) for c in cfg["zones"]]
    serializable["key_colors"] = {k: list(v) for k, v in cfg["key_colors"].items()}
    serializable["color"] = list(cfg["color"])
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)
    os.replace(tmp, PATH)
