"""Regras de dispositivos (refrigeradores): listagem por empresa e calibração pelo master."""

from typing import Optional

from app.core.auth import is_master
from app.core.errors import AppError
from app.repositories import auditoria
from app.repositories import dispositivos as repo

TIPOS = ("congelado", "resfriado")
# limites de sanidade para evitar faixa digitada errada (ex.: 400 em vez de 4.0)
TEMP_LIMITE_INFERIOR = -60
TEMP_LIMITE_SUPERIOR = 30
TOLERANCIA_MAX_MIN = 24 * 60


def _float(v):
    return float(v) if v is not None else None


def _bool(v):
    return None if v is None else bool(v)


def _iso(v):
    return v.isoformat() if v is not None else None


def _faixa(r: dict) -> dict:
    return {
        "min": _float(r["temp_min"]),
        "max": _float(r["temp_max"]),
        "tolerancia_min": r["tolerancia_min"],
    }


def _bad(msg: str) -> AppError:
    return AppError(msg, status_code=400, code="bad_request")


def parse_flag(valor: Optional[str]) -> bool:
    return valor in ("1", "true")


def listar(usuario: dict, intervalo_coleta_min: int, incluir_inativos: bool = False) -> dict:
    """Último estado de cada dispositivo, lido do banco (gravado pela coleta).

    Master vê todos; cliente só os da própria empresa.
    """
    master = is_master(usuario)
    rows = repo.listar_com_empresa(
        None if master else usuario["id_empresa"], incluir_inativos=master and incluir_inativos
    )
    dispositivos = [
        {
            "deviceid": r["deviceid"],
            "nome": (r["nome"] or "").strip(),
            "modelo": r["modelo"],
            "marca": r["marca"],
            "tipo": r["tipo"],
            "faixa": _faixa(r),
            "online": bool(r["online"]),
            "temperatura": _float(r["temperatura"]),
            "umidade": _float(r["umidade"]),
            "rele": _bool(r["rele"]),
            "sinal": r["sinal"],
            # alarmes configurados no próprio termostato (informativo; a faixa que vale é a de cima)
            "limite_min": _float(r["limite_min"]),
            "limite_max": _float(r["limite_max"]),
            "data_leitura": _iso(r["data_leitura"]),
            "empresa": {"id_empresa": r["id_empresa"], "nome": r["empresa"]}
            if r["id_empresa"]
            else None,
            "ativo": bool(r["ativo"]),
            "camera": (
                {"id_camera": r["id_camera"], "online": bool(r["camera_online"])}
                if r["id_camera"]
                else None
            ),
        }
        for r in rows
    ]
    return {
        "total": len(dispositivos),
        "intervalo_coleta_min": intervalo_coleta_min,
        "dispositivos": dispositivos,
    }


def _validar_faixa(body: dict) -> dict:
    campos: dict = {}
    if "tipo" in body:
        if body["tipo"] not in TIPOS:
            raise _bad(f"tipo deve ser um de: {', '.join(TIPOS)}")
        campos["tipo"] = body["tipo"]
    for chave in ("temp_min", "temp_max"):
        if chave in body:
            valor = body[chave]
            if valor is None:
                raise _bad(f"{chave} deve ser um número")
            if not TEMP_LIMITE_INFERIOR <= valor <= TEMP_LIMITE_SUPERIOR:
                raise _bad(
                    f"{chave} deve estar entre {TEMP_LIMITE_INFERIOR} e {TEMP_LIMITE_SUPERIOR} °C"
                )
            campos[chave] = round(float(valor), 1)
    if "tolerancia_min" in body:
        valor = body["tolerancia_min"]
        if valor is None or not 0 <= valor <= TOLERANCIA_MAX_MIN:
            raise _bad(f"tolerancia_min deve ser um inteiro entre 0 e {TOLERANCIA_MAX_MIN}")
        campos["tolerancia_min"] = valor
    return campos


def _validar_vinculo(body: dict) -> dict:
    campos: dict = {}
    if "id_empresa" in body:
        id_empresa = body["id_empresa"]
        if id_empresa is not None:
            empresa = repo.buscar_empresa_ativa(id_empresa)
            if not empresa:
                raise _bad("Empresa não encontrada ou inativa")
            if empresa["tipo"] == "master":
                raise _bad("Vincule o refrigerador a um cliente (a master já vê todos)")
        campos["id_empresa"] = id_empresa
    if "ativo" in body:
        if body["ativo"] is None:
            raise _bad("ativo deve ser true ou false")
        campos["ativo"] = 1 if body["ativo"] else 0
    return campos


def atualizar(autor: dict, deviceid: str, body: dict) -> dict:
    """Master calibra tipo/faixa/tolerância e gerencia vínculo (id_empresa) e ativo.

    `body` só traz os campos enviados (campos omitidos não mudam).
    """
    atual = repo.buscar_por_deviceid(deviceid)
    if not atual:
        raise AppError("Dispositivo não encontrado", status_code=404, code="not_found")

    campos = _validar_faixa(body)
    vinculo = _validar_vinculo(body)
    if not campos and not vinculo:
        raise _bad(
            "Envie ao menos um campo: tipo, temp_min, temp_max, tolerancia_min, id_empresa, ativo"
        )

    # valida a faixa resultante (pode vir só um dos lados) antes de gravar qualquer coisa
    if "temp_min" in campos or "temp_max" in campos:
        minimo = campos.get("temp_min", _float(atual["temp_min"]))
        maximo = campos.get("temp_max", _float(atual["temp_max"]))
        if minimo is not None and maximo is not None and minimo >= maximo:
            raise _bad(f"temp_min ({minimo}) deve ser menor que temp_max ({maximo})")

    if vinculo:
        repo.atualizar(atual["id_dispositivo"], vinculo)
        auditoria.registrar(
            autor["id_usuario"],
            "dispositivo_alterado",
            "dispositivo",
            deviceid,
            {"antes": {k: atual[k] for k in vinculo}, "depois": vinculo},
        )
    if not campos:
        return {"msg": "Refrigerador atualizado", "deviceid": deviceid, **vinculo}

    repo.atualizar(atual["id_dispositivo"], campos)
    auditoria.registrar(
        autor["id_usuario"],
        "faixa_alterada",
        "dispositivo",
        deviceid,
        {"antes": {k: atual[k] for k in campos}, "depois": campos},
    )
    novo = {**atual, **campos}
    return {
        "msg": "Refrigerador atualizado",
        "deviceid": deviceid,
        "tipo": novo["tipo"],
        "faixa": _faixa(novo),
    }
