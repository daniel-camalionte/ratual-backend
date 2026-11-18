from typing import Optional

from pydantic import BaseModel, Field


class GraficosQuery(BaseModel):
    horas: Optional[str] = Field(None, description="Janela da temperatura, 1 a 168 (padrão 24)")
    dias: Optional[str] = Field(None, description="Janela do compressor, 1 a 31 (padrão 7)")


class TemperaturaPonto(BaseModel):
    data: str = Field(..., description="Horário da coleta, ISO 8601")
    congelados: Optional[float] = None
    resfriados: Optional[float] = None


class CompressorDia(BaseModel):
    dia: str
    hoje: bool
    horas_media: Optional[float] = Field(None, description="null = sem leituras no dia")
    ligado_pct: Optional[int] = None
    aparelhos: int


class GraficosResponse(BaseModel):
    horas: int
    dias: int
    temperatura_media: list[TemperaturaPonto]
    compressor_por_dia: list[CompressorDia]
