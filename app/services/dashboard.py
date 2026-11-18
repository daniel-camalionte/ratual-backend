"""Séries do painel, calculadas sobre as leituras reais (só aparelhos ativos e online)."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.auth import is_master
from app.core.errors import AppError
from app.repositories import leituras

BRASILIA = timezone(timedelta(hours=-3))


def _f(v):
    return float(v) if v is not None else None


def agora_brasilia() -> datetime:
    return datetime.now(BRASILIA).replace(tzinfo=None, microsecond=0)


def graficos(
    usuario: dict,
    intervalo_coleta_min: int,
    horas: Optional[str] = None,
    dias: Optional[str] = None,
    agora: Optional[datetime] = None,
) -> dict:
    """- temperatura_media: média por tipo (congelados/resfriados) a cada coleta nas últimas `horas`
    - compressor_por_dia: horas com compressor ligado por dia (média por aparelho), `dias` dias
    Master considera todos os aparelhos; cliente, só os da própria empresa.
    """
    try:
        n_horas = min(168, max(1, int(horas or 24)))
        n_dias = min(31, max(1, int(dias or 7)))
    except ValueError:
        raise AppError(
            "horas e dias devem ser inteiros", status_code=400, code="bad_request"
        ) from None

    agora = agora or agora_brasilia()
    id_empresa = None if is_master(usuario) else usuario["id_empresa"]

    temperatura = leituras.temperatura_por_coleta(agora - timedelta(hours=n_horas), id_empresa)
    inicio_dias = (agora - timedelta(days=n_dias - 1)).replace(hour=0, minute=0, second=0)
    compressor = leituras.compressor_por_dia(inicio_dias, id_empresa)

    # temperatura: uma linha por horário de coleta, com uma coluna por tipo
    series: dict = {}
    for r in temperatura:
        chave = r["data_leitura"].isoformat()
        series.setdefault(chave, {"data": chave, "congelados": None, "resfriados": None})
        series[chave]["congelados" if r["tipo"] == "congelado" else "resfriados"] = _f(r["media"])

    # compressor: cada amostra vale o intervalo da coleta; média entre os aparelhos do dia
    intervalo_h = intervalo_coleta_min / 60
    por_dia: dict = {}
    for r in compressor:
        d = por_dia.setdefault(r["dia"], {"horas": [], "ligadas": 0, "amostras": 0})
        d["horas"].append(int(r["ligadas"]) * intervalo_h)
        d["ligadas"] += int(r["ligadas"])
        d["amostras"] += int(r["amostras"])

    dias_lista = []
    for i in range(n_dias):
        dia = (inicio_dias + timedelta(days=i)).date()
        d = por_dia.get(dia)
        dias_lista.append(
            {
                "dia": dia.isoformat(),
                "hoje": dia == agora.date(),
                # None = sem leituras nesse dia (ex.: antes do início do monitoramento)
                "horas_media": round(sum(d["horas"]) / len(d["horas"]), 1) if d else None,
                "ligado_pct": round(d["ligadas"] / d["amostras"] * 100)
                if d and d["amostras"]
                else None,
                "aparelhos": len(d["horas"]) if d else 0,
            }
        )

    return {
        "horas": n_horas,
        "dias": n_dias,
        "temperatura_media": list(series.values()),
        "compressor_por_dia": dias_lista,
    }
