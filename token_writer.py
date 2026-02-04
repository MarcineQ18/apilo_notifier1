import re
from pathlib import Path
from typing import Optional


def _replace_or_append(content: str, var: str, value: str) -> str:
    """
    Szuka linii typu:
      VAR = "..."
      VAR='...'
    i podmienia wartość. Jak nie znajdzie - dopisuje na końcu.
    """
    # Utrzymujemy cudzysłowy jak w pliku (prefer "...")
    pattern = rf"^(?P<prefix>\s*{re.escape(var)}\s*=\s*)(?P<q>['\"])(?P<val>.*?)(?P=q)\s*$"
    lines = content.splitlines()

    for i, line in enumerate(lines):
        m = re.match(pattern, line)
        if m:
            q = m.group("q")
            lines[i] = f"{m.group('prefix')}{q}{value}{q}"
            return "\n".join(lines) + ("\n" if content.endswith("\n") else "")

    # nie znaleziono - dopisz
    lines.append(f'{var} = "{value}"')
    return "\n".join(lines) + "\n"


def save_tokens_to_settings_py(
    settings_path: str,
    access_token: str,
    refresh_token: str,
    access_var: str = "APILO_TOKEN",
    refresh_var: str = "APILO_REFRESH_TOKEN",
) -> None:
    p = Path(settings_path)
    if not p.exists():
        raise FileNotFoundError(f"Nie znaleziono settings.py: {settings_path}")

    content = p.read_text(encoding="utf-8")

    content = _replace_or_append(content, access_var, access_token)
    content = _replace_or_append(content, refresh_var, refresh_token)

    p.write_text(content, encoding="utf-8")