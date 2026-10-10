"""Validação dos valores persistidos e dos argumentos recebidos pelo daemon."""
import math


def integer(value, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"valor inteiro fora de {low}..{high}: {value!r}")
    return value


def color(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("cor deve ter três canais RGB")
    return [integer(c, 0, 255) for c in value]


def zones(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("são necessárias exatamente quatro zonas")
    return [color(c) for c in value]


def audio(level, bands):
    if not isinstance(bands, (list, tuple)) or len(bands) != 4:
        raise ValueError("áudio deve ter exatamente quatro bandas")
    values = [level, *bands]
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError("níveis de áudio precisam ser finitos")
    return max(0.0, min(1.0, float(level))), [
        max(0.0, min(1.0, float(v))) for v in bands]


def normalize_state(raw, defaults, effect_names):
    """Descarta somente campos inválidos de um perfil salvo."""
    result = dict(defaults)
    if not isinstance(raw, dict):
        return result
    checks = {
        "zones": zones,
        "brightness": lambda v: integer(v, 0, 100),
        "firmware_mode": lambda v: integer(v, 0, 5),
        "speed": lambda v: integer(v, 0, 9),
        "direction": lambda v: integer(v, 1, 2),
        "color": color,
        "idle_timeout": lambda v: integer(v, 15, 86400),
    }
    for key, check in checks.items():
        if key in raw:
            try:
                result[key] = check(raw[key])
            except ValueError:
                pass
    if raw.get("mode") in ("zones", "firmware", "software"):
        result["mode"] = raw["mode"]
    if isinstance(raw.get("software_effect"), str) and raw["software_effect"] in effect_names:
        result["software_effect"] = raw["software_effect"]
    if isinstance(raw.get("idle_blank"), bool):
        result["idle_blank"] = raw["idle_blank"]
    if result["mode"] == "software" and result["software_effect"] not in effect_names:
        result["mode"] = "zones"
    return result
