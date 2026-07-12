"""Invoca lambda_handler directamente para probar sin desplegar.

Necesita credenciales de AWS reales resueltas localmente (`aws login`),
porque `ChatBedrockConverse` las valida al construirse, en el primer invoke.

Uso:
    .venv\\Scripts\\python.exe scripts\\run_local.py "quiero contratar facturacion electronica"
"""

import json
import sys

from connect_nlu_router_menu.handler import lambda_handler


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)

    response = lambda_handler({"message": sys.argv[1]}, None)
    print(json.dumps(response))


if __name__ == "__main__":
    main()
