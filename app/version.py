SERVICE_NAME = "ratual-backend"
__version__ = "0.1.0"


def build_id() -> str:
    """Identificador do pacote enviado ao servidor (gerado por scripts/package.py em app/BUILD).

    Aparece no cabeçalho `X-Build` de toda resposta, para conferir de fora qual versão está no ar.
    Fora de um pacote (desenvolvimento) vale "dev".
    """
    from pathlib import Path

    try:
        return (Path(__file__).with_name("BUILD")).read_text(encoding="utf-8").strip() or "dev"
    except OSError:
        return "dev"
