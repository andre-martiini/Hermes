import os
import sys
import json
import time
import subprocess
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# Configuração do Firebase (Usa as mesmas chaves do hermes_cli)
KEY_FILE = 'firebase_service_account_key.json'

# Globals para controle do processo
robot_process = None

def init_db():
    if not os.path.exists(KEY_FILE):
        print(f"❌ ERRO: Arquivo de chave {KEY_FILE} não encontrado no diretório raiz.")
        sys.exit(1)
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()

def run_nfse_robot(data):
    """
    Executa o script de automação como um subprocesso com suporte a STDIN
    """
    global robot_process
    print(f"\n🚀 TRABALHANDO: Iniciando robô NFS-e para CNPJ {data.get('cnpj_tomador')}...")
    
    # Prepara o JSON para o comando CLI
    json_data = json.dumps(data)
    
    # Caminho do script de automação
    script_path = os.path.join(os.path.dirname(__file__), "emissor_nfse.py")
    
    try:
        # Abrimos com stdin=PIPE para permitir que a ponte envie comandos (como o ENTER do login)
        robot_process = subprocess.Popen([
            sys.executable, script_path, "--data", json_data
        ], stdin=subprocess.PIPE)
        print(f"✅ Robô em execução (PID: {robot_process.pid}). Aguardando conclusão ou interação...")
        return True
    except Exception as e:
        print(f"❌ Erro ao disparar subprocesso: {e}")
        return False

def watch_robot_commands(db):
    print("\n" + "="*40)
    print("🤖 HERMES ROBOT BRIDGE: OPERANTE")
    print(f"Aguardando comandos via Firestore (automations/hermes_robot)")
    print("="*40 + "\n")
    
    doc_ref = db.collection('automations').document('hermes_robot')
    
    def on_snapshot(doc_snapshot, changes, read_time):
        for doc in doc_snapshot:
            data = doc.to_dict()
            if not data: continue
            
            # Caso 1: Novo comando de disparo
            if data.get('status') == 'requested':
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 📥 Novo comando de emissão recebido!")
                
                # Limpa o status para não re-disparar enquanto processa
                doc.reference.update({'status': 'processing', 'last_triggered': datetime.now().isoformat()})
                
                # Executa a tarefa
                params = data.get('params', {})
                params['url'] = "https://www.nfse.gov.br/EmissorNacional/Login?ReturnUrl=%2fEmissorNacional"
                
                success = run_nfse_robot(params)
                
                if success:
                    doc.reference.update({'status': 'processing'})
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Ponte finalizada. Robô assumiu o controle.")
                else:
                    doc.reference.update({'status': 'error', 'error_msg': 'Falha ao iniciar robô'})
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Falha catastrófica ao abrir o robô.")

            # Caso 2: Confirmação de Login vinda da Interface
            elif data.get('status') == 'login_confirmed' and robot_process:
                if robot_process.poll() is None: # Se o processo ainda está rodando
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⌨️  Recebido sinal de LOGIN CONFIRMADO. Enviando 'ENTER' para o Robô...")
                    try:
                        robot_process.stdin.write(b'\n')
                        robot_process.stdin.flush()
                        doc.reference.update({'status': 'processing'})
                    except Exception as e:
                        print(f"⚠️ Erro ao enviar comando para o processo: {e}")
                else:
                    print("⚠️ Usuário confirmou login mas o robô já não está mais em execução.")
                    doc.reference.update({'status': 'idle'})

    # Inicia o observador
    doc_watch = doc_ref.on_snapshot(on_snapshot)
    
    # Mantém o script rodando
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nBridge encerrado pelo usuário.")
        sys.exit(0)

if __name__ == "__main__":
    db = init_db()
    watch_robot_commands(db)
