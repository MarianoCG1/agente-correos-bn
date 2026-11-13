# v1 (referencia)

Primera versión de producción: una sola clase de ~2.780 líneas (`correos.py`, tkinter + Outlook por COM) que genera
borradores por agencia con la tabla HTML y el Excel filtrado adjunto.

Se conserva por dos razones: es la línea base contra la que se midió la mejora y **`tests/test_paridad_v1.py` verifica
que la versión actual genera el mismo HTML y los mismos asuntos** que ella. No se mantiene ni se recomienda usarla.

Los nombres y direcciones que aparecían en el código original se reemplazaron por valores de ejemplo.
