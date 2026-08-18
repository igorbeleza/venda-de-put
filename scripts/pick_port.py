"""Escolhe a porta 8765 (padrão do projeto) se estiver livre, senão uma
porta aleatória livre. Usado por iniciar-dashboard.bat — imprime só o
número da porta em stdout, uma linha, nada mais."""

import socket

DEFAULT_PORT = 8765


def _is_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def pick_port() -> int:
    if _is_free(DEFAULT_PORT):
        return DEFAULT_PORT
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


if __name__ == "__main__":
    print(pick_port())
