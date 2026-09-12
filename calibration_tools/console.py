"""
Utilidad de Consola: salida segura en terminales que no son UTF-8.

Los scripts del proyecto imprimen emojis. En una consola de Windows con codificación cp1252
(`cmd`, Git Bash, o cualquier CI sin `PYTHONIOENCODING` definido) eso aborta el proceso:

    UnicodeEncodeError: 'charmap' codec can't encode character '\\U0001f3af'

El fallo es especialmente engañoso porque depende del terminal: en PowerShell funciona, así que
el mismo comando falla o no según dónde se ejecute. `threshold_tuner` llegaba a completar todo
el barrido y reventaba justo al imprimir su conclusión, perdiendo el resultado.

Llamar a `enable_unicode_output()` al inicio de cada script de línea de comandos.
"""
import sys


def enable_unicode_output() -> None:
    """
    Reconfigura stdout y stderr a UTF-8, degradando a un carácter de reemplazo si la consola
    no puede representar algún símbolo, en lugar de abortar el proceso.

    No falla nunca: si el flujo no admite `reconfigure` (por ejemplo si está redirigido a un
    objeto que no es un TextIOWrapper), se deja tal cual.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # Flujo ya cerrado o sin soporte de reconfiguración: no es motivo para abortar.
            pass
