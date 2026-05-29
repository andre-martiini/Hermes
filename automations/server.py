import subprocess
import sys
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import os

app = FastAPI(title="Hermes Automations API")

# Habilitar CORS para permitir que o React converse com esta API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Na prática, você colocaria "http://localhost:3025"
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from execucao_pgd import preencher_execucao_pgd

class PgdData(BaseModel):
    mes_ano: str
    entregas: list

def executar_script(nome_script: str):
    try:
        subprocess.run([sys.executable, nome_script], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Erro ao executar {nome_script}: {e}")
    except Exception as e:
         print(f"Erro inesperado: {e}")

@app.post("/api/automations/ponto-eletronico")
async def run_ponto_eletronico(background_tasks: BackgroundTasks):
    try:
        background_tasks.add_task(executar_script, "ponto_eletronico.py")
        return {"status": "success", "message": "Automação de Ponto Eletrônico iniciada!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/automations/executar-pgd")
async def run_execucao_pgd(data: PgdData, background_tasks: BackgroundTasks):
    try:
        # Repassa o dicionário para a função do script
        background_tasks.add_task(preencher_execucao_pgd, data.model_dump())
        return {"status": "success", "message": "Automação do PGD enviada para execução!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/automations/logs")
async def get_logs():
    async def log_generator():
        log_file = "pgd_automation.log"
        # Garante que o arquivo exista
        if not os.path.exists(log_file):
            open(log_file, 'w', encoding='utf-8').close()
            
        with open(log_file, 'r', encoding='utf-8') as f:
            # Pula para o final do arquivo ao se conectar (ou não, se quiser ver o histórico todo)
            # Para o PGD o ideal é esvaziar/ler desde o começo a cada conexão? Como o DualLogger sobreescreve (open com 'w') ao iniciar, vamos ler do começo.
            while True:
                line = f.readline()
                if line:
                    yield f"data: {line}\n\n"
                else:
                    await asyncio.sleep(0.5)

    return StreamingResponse(log_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000)
