# -*- coding: utf-8 -*-
"""`python -m simulador_nt8 --entorno=pruebas [--dir-sockets DIR] [--fichero-info F]`

Arranca `ServidorNT8Simulado` como proceso independiente. Ver
`simulador_nt8/LEEME.md` antes de usar esto -- NO es el adaptador real."""
from .servidor import main

if __name__ == "__main__":
    main()
