# -*- coding: utf-8 -*-
"""Shim del paquete de ingenieria: le dice a motor_exp donde estan las series.
En el laboratorio original esto vive en core/datos.py del repo del bot."""
import os
def carpeta():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'modelo', 'datos')
