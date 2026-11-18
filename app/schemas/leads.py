"""Contatos da landing page (formulário público)."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LeadBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    nome: str = Field(..., min_length=1, max_length=120)
    empresa: str = Field(..., min_length=1, max_length=150)
    telefone: str = Field(..., min_length=1, max_length=30, description="WhatsApp com DDD")
    cidade: Optional[str] = Field(None, max_length=100)
    negocio: Optional[str] = Field(None, max_length=60)
    quantidade: Optional[str] = Field(None, max_length=30)
    plano: Optional[str] = Field(None, max_length=40)
    site: Optional[str] = Field(
        None, max_length=500, description="Campo invisível (anti-robô): deixe vazio"
    )


class LeadResponse(BaseModel):
    msg: str
    id_lead: Optional[int] = None
