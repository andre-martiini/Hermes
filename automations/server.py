from __future__ import annotations

import asyncio
import contextlib
import io
import subprocess
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from criacao_plano_pgd import (
    criar_plano_pgd,
    finalizar_plano_pgd,
    preparar_plano_pgd,
)
from execucao_pgd import preencher_execucao_pgd


BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "pgd_automation.log"
LOG_LOCK = threading.Lock()
SESSION_LOCK = threading.Lock()
PLAN_SESSIONS: dict[str, dict] = {}
SESSION_TTL_SECONDS = 30 * 60

app = FastAPI(title="Hermes Automations API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://gestao-hermes.web.app",
        "https://gestao-hermes.firebaseapp.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RegistroPgd(BaseModel):
    descricao_atividade: str
    data_inicio: str
    data_fim: str


class EntregaExecucao(BaseModel):
    nome_entrega: str
    registros: list[RegistroPgd]


class ExecucaoPgdData(BaseModel):
    mes_ano: str
    entregas: list[EntregaExecucao]


class EntregaPlano(BaseModel):
    origem: str
    unidade: str = ""
    entrega: str
    descricao: str
    percentual: int = Field(ge=5, le=100, multiple_of=5)
    plano_entrega_codigo: str | None = None


class CriacaoPlanoData(BaseModel):
    sessao_id: str | None = None
    mes_ano: str
    data_inicio: str
    data_fim: str
    unidade: str = "CLC-BSF"
    modalidade: str = "Teletrabalho (Integral)"
    entregas: list[EntregaPlano]


class PreparacaoPlanoData(BaseModel):
    mes_ano: str
    data_inicio: str
    data_fim: str
    unidade: str = "CLC-BSF"
    modalidade: str = "Teletrabalho (Integral)"


class _Tee(io.TextIOBase):
    def __init__(self, arquivo, terminal):
        self.arquivo = arquivo
        self.terminal = terminal

    def write(self, data):
        self.arquivo.write(data)
        self.arquivo.flush()
        self.terminal.write(data)
        self.terminal.flush()
        return len(data)

    def flush(self):
        self.arquivo.flush()
        self.terminal.flush()


def _executar_com_log(funcao, payload: dict) -> None:
    with LOG_LOCK:
        with LOG_FILE.open("w", encoding="utf-8") as arquivo:
            tee = _Tee(arquivo, sys.__stdout__)
            with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
                try:
                    funcao(payload)
                except Exception as exc:
                    print(f"[FALHA] {type(exc).__name__}: {exc}")


def _executar_sessao_com_log(driver, payload: dict) -> None:
    with LOG_LOCK:
        with LOG_FILE.open("w", encoding="utf-8") as arquivo:
            tee = _Tee(arquivo, sys.__stdout__)
            with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
                try:
                    finalizar_plano_pgd(driver, payload)
                except Exception as exc:
                    print(f"[FALHA] {type(exc).__name__}: {exc}")
                    traceback.print_exc()


def _encerrar_driver(driver) -> None:
    try:
        driver.quit()
    except Exception:
        pass


def _limpar_sessoes_expiradas() -> None:
    limite = time.time() - SESSION_TTL_SECONDS
    expiradas = []
    with SESSION_LOCK:
        for sessao_id, sessao in list(PLAN_SESSIONS.items()):
            if sessao["criada_em"] < limite:
                expiradas.append(PLAN_SESSIONS.pop(sessao_id))
    for sessao in expiradas:
        _encerrar_driver(sessao["driver"])


def _executar_script(nome_script: str) -> None:
    subprocess.run(
        [sys.executable, str(BASE_DIR / nome_script)],
        cwd=BASE_DIR,
        check=True,
    )


@app.get("/api/automations/health")
async def health():
    return {"status": "ok"}


@app.post("/api/automations/ponto-eletronico")
async def run_ponto_eletronico(background_tasks: BackgroundTasks):
    script = BASE_DIR / "ponto_eletronico.py"
    if not script.exists():
        raise HTTPException(
            status_code=404,
            detail="O script ponto_eletronico.py não está disponível.",
        )
    background_tasks.add_task(_executar_script, script.name)
    return {"status": "success"}


@app.post("/api/automations/executar-pgd")
async def run_execucao_pgd(
    data: ExecucaoPgdData,
    background_tasks: BackgroundTasks,
):
    background_tasks.add_task(
        _executar_com_log,
        preencher_execucao_pgd,
        data.model_dump(),
    )
    return {"status": "success", "message": "Execução PGD iniciada."}


@app.post("/api/automations/criar-plano-pgd")
async def run_criacao_plano(
    data: CriacaoPlanoData,
    background_tasks: BackgroundTasks,
):
    total = sum(item.percentual for item in data.entregas)
    if total != 100:
        raise HTTPException(
            status_code=422,
            detail=f"A soma dos percentuais deve ser 100%; recebido: {total}%.",
        )
    if data.sessao_id:
        with SESSION_LOCK:
            sessao = PLAN_SESSIONS.get(data.sessao_id)
        if not sessao:
            raise HTTPException(
                status_code=410,
                detail="A sessão do Petrvs expirou. Consulte as entregas novamente.",
            )
        if sessao["mes_ano"] != data.mes_ano:
            raise HTTPException(
                status_code=409,
                detail="O mês foi alterado. Consulte as entregas novamente.",
            )
        indisponiveis = [
            item.entrega
            for item in data.entregas
            if item.origem == "Própria Unidade"
            and item.entrega not in sessao["entregas"]
        ]
        if indisponiveis:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Estas entregas não estão mais disponíveis na sessão: "
                    + "; ".join(indisponiveis)
                ),
            )
        with SESSION_LOCK:
            PLAN_SESSIONS.pop(data.sessao_id, None)
        background_tasks.add_task(
            _executar_sessao_com_log,
            sessao["driver"],
            data.model_dump(exclude={"sessao_id"}),
        )
        return {
            "status": "success",
            "message": "Criação do plano PGD iniciada na sessão consultada.",
        }
    background_tasks.add_task(
        _executar_com_log,
        criar_plano_pgd,
        data.model_dump(),
    )
    return {"status": "success", "message": "Criação do plano PGD iniciada."}


@app.post("/api/automations/preparar-plano-pgd")
def preparar_criacao_plano(data: PreparacaoPlanoData):
    _limpar_sessoes_expiradas()
    try:
        driver, entregas = preparar_plano_pgd(data.model_dump())
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Não foi possível consultar o Petrvs: {exc}",
        ) from exc
    sessao_id = uuid.uuid4().hex
    with SESSION_LOCK:
        PLAN_SESSIONS[sessao_id] = {
            "driver": driver,
            "criada_em": time.time(),
            "mes_ano": data.mes_ano,
            "entregas": entregas,
        }
    return {
        "status": "success",
        "sessao_id": sessao_id,
        "mes_ano": data.mes_ano,
        "entregas": entregas,
        "expira_em_segundos": SESSION_TTL_SECONDS,
    }


@app.delete("/api/automations/sessoes-plano-pgd/{sessao_id}")
def cancelar_sessao_plano(sessao_id: str):
    with SESSION_LOCK:
        sessao = PLAN_SESSIONS.pop(sessao_id, None)
    if sessao:
        _encerrar_driver(sessao["driver"])
    return {"status": "success", "encerrada": bool(sessao)}


@app.get("/api/automations/logs")
async def get_logs():
    async def log_generator():
        LOG_FILE.touch(exist_ok=True)
        with LOG_FILE.open("r", encoding="utf-8") as arquivo:
            while True:
                linha = arquivo.readline()
                if linha:
                    yield f"data: {linha.rstrip()}\n\n"
                else:
                    await asyncio.sleep(0.5)

    return StreamingResponse(log_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
