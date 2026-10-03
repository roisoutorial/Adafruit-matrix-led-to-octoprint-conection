# boot.py
# Este archivo solo se ejecuta al arrancar/reiniciar la placa (no al guardar code.py).
# Activa un segundo puerto USB serie ("data") separado del REPL, para
# comunicarnos con el PC sin interferir con la consola.

import usb_cdc

usb_cdc.enable(console=True, data=True)
