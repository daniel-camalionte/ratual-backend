"""Modelos compartilhados (também alimentam a documentação OpenAPI)."""

from typing import Optional

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str = Field(
        ..., examples=["not_found"], description="Código estável para tratamento no cliente"
    )
    message: str = Field(..., examples=["Recurso não encontrado."])
    request_id: Optional[str] = Field(None, description="Use ao reportar um problema")


class ErrorResponse(BaseModel):
    error: ErrorBody
