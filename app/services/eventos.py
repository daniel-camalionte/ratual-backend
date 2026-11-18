"""Eventos da linha do tempo de cada refrigerador (sem Flask).

- `Detector`: compara a leitura anterior com a nova e decide o que abrir/fechar (função pura, sem
  banco). Usado pela coleta e pelo reprocessamento do histórico, com as mesmas regras.
- Funções de serviço: gravam as decisões e expõem a listagem de /eventos e /alertas.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import Settings
from app.core.auth import is_master
from app.core.errors import AppError
from app.repositories import eventos as repo
from app.services.trava import trava

BRASILIA = timezone(timedelta(hours=-3))
TIPOS = (
    "offline", "fora_faixa", "subida_rapida", "rele_ligado", "rele_desligado",
    "camera_deteccao", "camera_offline",
)  # fmt: skip
TIPOS_ALERTA = ("offline", "fora_faixa", "camera_offline")
LIMITE_MAX = 500


def _agora() -> datetime:
    return datetime.now(BRASILIA).replace(tzinfo=None, microsecond=0)


def _f(v):
    return float(v) if v is not None else None


def _json(v) -> dict:
    if not v:
        return {}
    try:
        return json.loads(v) if isinstance(v, str) else dict(v)
    except ValueError:
        return {}


def _dump(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False, default=_serial)


def _serial(v):
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    raise TypeError(type(v).__name__)


def _temp(v) -> str:
    return f"{v:.1f}".replace(".", ",") if v is not None else "--"


def _duracao(minutos) -> str:
    if minutos is None:
        return ""
    minutos = int(minutos)
    if minutos < 60:
        return f"{minutos} min"
    h, m = divmod(minutos, 60)
    if h < 24:
        return f"{h} h {m} min" if m else f"{h} h"
    d, h = divmod(h, 24)
    return f"{d} d {h} h" if h else f"{d} d"


class Detector:
    """Regras de detecção. Recebe estados e devolve ações; não acessa o banco."""

    def __init__(self, subida_c: float, intervalo_min: int):
        self.subida_c = subida_c
        # leituras mais distantes que isso não são "seguidas" (houve buraco na coleta)
        self.janela_seguida = timedelta(minutes=2 * intervalo_min + 1)

    def avaliar(self, id_disp, ant, atual, faixa, abertos, agora) -> dict:
        """
        ant:     última leitura conhecida {"online", "temperatura", "rele", "data"} ou None
        atual:   leitura desta coleta {"online", "temperatura", "rele"}
        faixa:   {"min", "max", "tolerancia_min", "fora_desde"}
        abertos: {(id_dispositivo, tipo): evento em andamento}
        Retorna {"novos", "fechar": [(id_evento, fim, detalhe)], "pico": [(id_evento, valor)],
        "fora_desde"}
        """
        acoes = {"novos": [], "fechar": [], "pico": [], "fora_desde": faixa.get("fora_desde")}

        def aberto(tipo):
            return abertos.get((id_disp, tipo))

        def novo(tipo, origem, inicio, fim=None, valor=None, detalhe=None):
            acoes["novos"].append(
                {
                    "id_dispositivo": id_disp, "tipo": tipo, "origem": origem, "inicio": inicio,
                    "fim": fim, "valor": valor, "detalhe": detalhe or {},
                }
            )  # fmt: skip

        # ── offline ──────────────────────────────────────────────────────
        off = aberto("offline")
        if not atual["online"]:
            if not off:
                ultima = ant.get("data") if ant else None
                novo(
                    "offline", "sistema", agora,
                    valor=_f(ant.get("temperatura")) if ant else None,
                    detalhe={"ultima_leitura": ultima.strftime("%Y-%m-%d %H:%M:%S") if ultima else None},  # noqa: E501
                )  # fmt: skip
            # offline: temperatura e relé não são confiáveis; o estado fora da faixa fica como está
            return acoes
        if off:
            duracao = int((agora - off["inicio"]).total_seconds() // 60)
            acoes["fechar"].append(
                (off["id_evento"], agora, {**_json(off.get("detalhe")), "duracao_min": duracao})
            )

        seguida = bool(
            ant
            and ant.get("online")
            and ant.get("data")
            and agora - ant["data"] <= self.janela_seguida
        )
        temp = atual.get("temperatura")

        # ── fora da faixa (com tolerância) ───────────────────────────────
        if temp is not None:
            ff = aberto("fora_faixa")
            minimo, maximo = faixa["min"], faixa["max"]
            if temp < minimo or temp > maximo:
                direcao = "acima" if temp > maximo else "abaixo"
                desde = faixa.get("fora_desde") or agora
                acoes["fora_desde"] = desde
                if ff:
                    pico = _f(ff.get("valor"))
                    if (
                        pico is None
                        or (direcao == "acima" and temp > pico)
                        or (direcao == "abaixo" and temp < pico)
                    ):
                        acoes["pico"].append((ff["id_evento"], temp))
                elif agora - desde >= timedelta(minutes=faixa["tolerancia_min"]):
                    novo(
                        "fora_faixa", "sistema", desde, valor=temp,
                        detalhe={"min": minimo, "max": maximo, "direcao": direcao, "tolerancia_min": faixa["tolerancia_min"]},  # noqa: E501
                    )  # fmt: skip
            else:
                acoes["fora_desde"] = None
                if ff:
                    duracao = int((agora - ff["inicio"]).total_seconds() // 60)
                    acoes["fechar"].append(
                        (
                            ff["id_evento"],
                            agora,
                            {
                                **_json(ff.get("detalhe")),
                                "duracao_min": duracao,
                                "normalizou_em": temp,
                            },
                        )
                    )

            # ── subida rápida (possível porta aberta) ────────────────────
            # com o compressor desligado a subida é esperada (degelo, ciclo do termostato): não registra  # noqa: E501
            compressor_desligado = atual.get("rele") is not None and not bool(atual["rele"])
            if seguida and ant.get("temperatura") is not None and not compressor_desligado:
                delta = round(temp - _f(ant["temperatura"]), 1)
                if delta >= self.subida_c:
                    novo(
                        "subida_rapida", "sistema", agora, fim=agora, valor=temp,
                        detalhe={"de": _f(ant["temperatura"]), "para": temp, "delta": delta},
                    )  # fmt: skip

        # ── relé mudou sem comando do app (app eWeLink, temporizador, loop) ──
        if (
            seguida
            and ant.get("rele") is not None
            and atual.get("rele") is not None
            and bool(ant["rele"]) != bool(atual["rele"])
        ):
            novo(
                "rele_ligado" if atual["rele"] else "rele_desligado", "externo", agora, fim=agora, valor=temp,  # noqa: E501
                detalhe={"obs": "fora do app (app eWeLink, temporizador ou loop)"},
            )  # fmt: skip

        return acoes


def _detector(settings: Settings) -> Detector:
    return Detector(settings.evento_subida_rapida_c, settings.ewelink_coleta_intervalo_min)


def descrever(e: dict) -> str:
    """Texto pronto para a tela (pt-BR)."""
    d = _json(e.get("detalhe"))
    tipo, ativo = e["tipo"], e.get("fim") is None
    hora = (
        e["inicio"].strftime("%H:%M")
        if isinstance(e["inicio"], datetime)
        else str(e["inicio"])[11:16]
    )

    if tipo == "offline":
        return (
            f"Sem comunicação desde {hora}"
            if ativo
            else f"Ficou offline por {_duracao(d.get('duracao_min'))}"
        )
    if tipo == "fora_faixa":
        faixa = f"{_temp(_f(d.get('min')))} a {_temp(_f(d.get('max')))} °C"
        pico = f"pico {_temp(_f(e.get('valor')))} °C"
        lado = "acima" if d.get("direcao") == "acima" else "abaixo"
        if ativo:
            return f"Temperatura {lado} da faixa ({faixa}) desde {hora} · {pico}"
        return f"Ficou {lado} da faixa ({faixa}) por {_duracao(d.get('duracao_min'))} · {pico}"
    if tipo == "camera_deteccao":
        return f"Câmera {d.get('camera') or ''} detectou movimento/pessoa".replace("  ", " ")
    if tipo == "camera_offline":
        camera = d.get("camera") or "da câmara"
        if ativo:
            return f"Câmera {camera} sem comunicação desde {hora}"
        return f"Câmera {camera} ficou offline por {_duracao(d.get('duracao_min'))}"
    if tipo == "subida_rapida":
        return (
            f"Subida rápida de {_temp(_f(d.get('de')))} para {_temp(_f(d.get('para')))} °C "
            f"(+{_temp(_f(d.get('delta')))} °C): possível porta aberta"
        )
    acao = "ligado" if tipo == "rele_ligado" else "desligado"
    if e.get("origem") == "app":
        return f"Compressor {acao} por {e.get('usuario') or 'usuário do app'}"
    return f"Compressor {acao} fora do app (app eWeLink, temporizador ou loop)"


# ── gravação ─────────────────────────────────────────────────────────────


def _gravar(acoes: dict, id_disp: int, fora_desde_antes) -> tuple:
    """Persiste as ações do detector. Retorna (abertos, fechados)."""
    for n in acoes["novos"]:
        repo.criar(
            n["id_dispositivo"],
            n["tipo"],
            n["origem"],
            n["inicio"],
            n["fim"],
            n["valor"],
            _dump(n["detalhe"]),
        )
    for id_evento, fim, detalhe in acoes["fechar"]:
        repo.fechar(id_evento, fim, _dump(detalhe))
    for id_evento, valor in acoes["pico"]:
        repo.atualizar_pico(id_evento, valor)
    if acoes["fora_desde"] != fora_desde_antes:
        repo.atualizar_fora_desde(id_disp, acoes["fora_desde"])
    return sum(1 for n in acoes["novos"] if n["fim"] is None), len(acoes["fechar"])


def processar_coleta(settings: Settings, anteriores: dict, atuais: dict, agora: datetime) -> str:
    """Chamado pela coleta. anteriores: {id_dispositivo: linha do dispositivo antes da coleta};
    atuais: {id_dispositivo: {"online", "temperatura", "rele"}}. Retorna resumo para o log."""
    abertos = repo.abertos()
    det = _detector(settings)
    novos = n_abertos = fechados = 0
    for id_disp, atual in atuais.items():
        ant = anteriores.get(id_disp)
        if ant is None:
            continue  # aparelho novo: ainda não há estado anterior para comparar
        faixa = {
            "min": _f(ant["temp_min"]), "max": _f(ant["temp_max"]),
            "tolerancia_min": ant["tolerancia_min"], "fora_desde": ant["fora_faixa_desde"],
        }  # fmt: skip
        anterior = {
            "online": ant["online"], "temperatura": ant["temperatura"],
            "rele": ant["rele"], "data": ant["data_leitura"],
        }  # fmt: skip
        acoes = det.avaliar(id_disp, anterior, atual, faixa, abertos, agora)
        a, f = _gravar(acoes, id_disp, ant["fora_faixa_desde"])
        novos += len(acoes["novos"])
        n_abertos += a
        fechados += f
    return f"eventos: {novos} novos ({n_abertos} alertas abertos), {fechados} encerrados"


def registrar_comando(
    id_dispositivo: int, ligado: bool, id_usuario: int, id_comando: Optional[int], temperatura
) -> int:
    """Comando feito pelo app: evento com o usuário que executou."""
    agora = _agora()
    return repo.criar(
        id_dispositivo, "rele_ligado" if ligado else "rele_desligado", "app", agora, agora,
        temperatura, "{}", id_usuario=id_usuario, id_comando=id_comando or None,
    )  # fmt: skip


def reprocessar_historico(settings: Settings) -> dict:
    """Recria os eventos de sistema/externo a partir de todas as leituras (usa a faixa atual).
    Eventos de comandos do app (origem app) e os das câmeras são preservados."""
    with trava() as conseguiu:
        if not conseguiu:
            raise AppError(
                "Coleta em andamento, tente de novo em instantes", status_code=409, code="conflict"
            )

        faixas = {d["id_dispositivo"]: d for d in repo.faixas_dispositivos()}
        leituras = repo.todas_leituras()
        repo.apagar_eventos_de_sistema()

        det = _detector(settings)
        seq = 0
        eventos: dict = {}
        estado: dict = {}  # por dispositivo
        for leitura in leituras:
            id_disp = leitura["id_dispositivo"]
            f = faixas.get(id_disp)
            if f is None:
                continue
            st = estado.setdefault(id_disp, {"ant": None, "fora_desde": None, "abertos": {}})
            faixa = {
                "min": _f(f["temp_min"]), "max": _f(f["temp_max"]),
                "tolerancia_min": f["tolerancia_min"], "fora_desde": st["fora_desde"],
            }  # fmt: skip
            atual = {
                "online": bool(leitura["online"]),
                "temperatura": _f(leitura["temperatura"]),
                "rele": leitura["rele"],
            }
            agora = leitura["data_leitura"]
            acoes = det.avaliar(id_disp, st["ant"], atual, faixa, st["abertos"], agora)

            for n in acoes["novos"]:
                seq += 1
                n["id_evento"] = seq
                eventos[seq] = n
                if n["fim"] is None:
                    st["abertos"][(id_disp, n["tipo"])] = n
            for id_evento, fim, detalhe in acoes["fechar"]:
                ev = eventos[id_evento]
                ev["fim"], ev["detalhe"] = fim, detalhe
                st["abertos"].pop((id_disp, ev["tipo"]), None)
            for id_evento, valor in acoes["pico"]:
                eventos[id_evento]["valor"] = valor
            st["fora_desde"] = acoes["fora_desde"]
            if atual["online"]:
                st["ant"] = {**atual, "data": agora}
            elif st["ant"]:
                st["ant"] = {**st["ant"], "online": False}

        for ev in eventos.values():
            repo.criar(
                ev["id_dispositivo"],
                ev["tipo"],
                ev["origem"],
                ev["inicio"],
                ev["fim"],
                ev["valor"],
                _dump(ev["detalhe"]),
            )
        for id_disp, st in estado.items():
            repo.atualizar_fora_desde(id_disp, st["fora_desde"])

        por_tipo: dict = {}
        for ev in eventos.values():
            por_tipo[ev["tipo"]] = por_tipo.get(ev["tipo"], 0) + 1
        return {
            "msg": "Histórico reprocessado",
            "leituras": len(leituras),
            "eventos": len(eventos),
            "por_tipo": por_tipo,
            "ativos": sum(1 for ev in eventos.values() if ev["fim"] is None),
        }


# ── leitura (rotas) ──────────────────────────────────────────────────────


def listar(
    usuario: dict, tipo: Optional[str], deviceid: Optional[str], ativos: Optional[str],
    inicio: Optional[str], fim: Optional[str], limite, offset, somente_alertas: bool = False,
) -> dict:  # fmt: skip
    tipos = TIPOS_ALERTA if somente_alertas else None
    if not somente_alertas and tipo:
        tipos = [t for t in tipo.split(",") if t]
        invalidos = [t for t in tipos if t not in TIPOS]
        if invalidos:
            raise AppError(
                f"tipo inválido: {', '.join(invalidos)}. Use: {', '.join(TIPOS)}", status_code=400
            )
    try:
        limite = min(LIMITE_MAX, max(1, int(limite if limite not in (None, "") else 100)))
        offset = max(0, int(offset if offset not in (None, "") else 0))
    except ValueError:
        raise AppError("limite e offset devem ser inteiros", status_code=400) from None

    rows = repo.listar(
        id_empresa=None if is_master(usuario) else usuario["id_empresa"],
        deviceid=deviceid,
        tipos=tipos,
        ativos=somente_alertas or ativos in ("1", "true"),
        inicio=inicio,
        fim=fim,
        limite=limite,
        offset=offset,
    )
    agora = _agora()
    eventos = []
    for r in rows:
        detalhe = _json(r["detalhe"])
        duracao = detalhe.get("duracao_min")
        if r["fim"] is None:
            duracao = int((agora - r["inicio"]).total_seconds() // 60)
        eventos.append(
            {
                "id_evento": r["id_evento"],
                "tipo": r["tipo"],
                "origem": r["origem"],
                "ativo": r["fim"] is None,
                "inicio": r["inicio"],
                "fim": r["fim"],
                "duracao_min": duracao,
                "valor": _f(r["valor"]),
                "detalhe": detalhe,
                "descricao": descrever(r),
                "usuario": r["usuario"],
                "dispositivo": {
                    "deviceid": r["deviceid"],
                    "nome": (r["dispositivo"] or "").strip(),
                },
                "empresa": {"id_empresa": r["id_empresa"], "nome": r["empresa"]}
                if r["id_empresa"]
                else None,
            }
        )
    return {"total": len(eventos), "limite": limite, "offset": offset, "eventos": eventos}
