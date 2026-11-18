"""Contatos da landing page. Rota pública (sem login), com limite de taxa por IP."""

from flask import current_app, request
from flask_openapi3 import APIBlueprint, Tag

from app.core.background import em_segundo_plano
from app.schemas.common import ErrorResponse as ErrorSchema
from app.schemas.leads import LeadBody, LeadResponse
from app.services import leads as service

# propositalmente SEM require_login_for_blueprint: o formulário do site é público
bp = APIBlueprint("leads", __name__, url_prefix="/v1/leads", abp_tags=[Tag(name="Leads")])


@bp.post(
    "",
    summary="Registra um contato vindo do site (público)",
    responses={201: LeadResponse, 400: ErrorSchema, 429: ErrorSchema},
)
def criar(body: LeadBody):
    """Grava o contato e avisa a equipe comercial por e-mail. Máximo de 5 envios por hora por IP."""
    resposta, lead = service.criar(body.model_dump(), request.remote_addr or "")
    if lead is not None:
        em_segundo_plano(
            service.enviar_aviso,
            resposta["id_lead"],
            lead,
            current_app.extensions["settings"].lead_emails,
        )
    return resposta, 201
