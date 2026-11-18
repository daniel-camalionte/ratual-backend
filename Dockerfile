# Ambiente local de teste — mesma versão de Python da KingHost (3.9).
# Em produção a app roda sob mod_wsgi; aqui usamos gunicorn só para exercitar o mesmo
# contrato WSGI (wsgi:application).
FROM python:3.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install -r requirements.txt gunicorn==23.0.0

COPY app ./app
COPY wsgi.py ./

# usuário sem privilégios (espelha a ausência de root na hospedagem)
RUN useradd --system --no-create-home appuser
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).status == 200 else 1)"

CMD ["gunicorn", "wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-"]
