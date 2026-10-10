"""Perfil salvo em ~/.config/controlfanrgb/config.json."""
import json
import os

from . import effects, themes, validation

DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "controlfanrgb")
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
    try:
        with open(PATH) as f:
            raw = json.load(f)
    except (OSError, ValueError):
        raw = {}
    cfg = validation.normalize_state(
        raw, DEFAULT, {cls.nome for cls in effects.SOFTWARE_EFFECTS})
    if not isinstance(raw, dict):
        raw = {}
    if isinstance(raw.get("theme"), str) and raw["theme"] in themes.THEMES:
        cfg["theme"] = raw["theme"]
    if isinstance(raw.get("apply_on_start"), bool):
        cfg["apply_on_start"] = raw["apply_on_start"]
    painted = raw.get("key_colors")
    cfg["key_colors"] = {}
    if isinstance(painted, dict):
        for key, value in list(painted.items())[:200]:
            if isinstance(key, str):
                try:
                    cfg["key_colors"][key] = tuple(validation.color(value))
                except ValueError:
                    pass
    cfg["zones"] = [tuple(c) for c in cfg["zones"]]
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
