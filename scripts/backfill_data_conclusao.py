"""Backfill pontual: preenche `data_conclusao` nas acoes concluidas que nao tem.

Contexto: a varredura de elevacao encontra acoes concluidas por janela de data
(`data_conclusao >= corte`). Acao concluida sem esse campo nao aparece na
consulta de concluidas nem na de vivas — fica invisivel para a varredura, e
invisivel para sempre, porque nenhuma janela futura vai alcanca-la.

Sao 5 acoes hoje. O conjunto e fechado: os seis caminhos que concluem acao
(handler central de index.tsx, confirmarEdicaoAcao, confirmarEdicaoEmLote, a
callable do Telegram, a sincronizacao do Google Tasks e hermes-voice-bridge)
gravam o campo, o ultimo deles a partir de 29/08/2026. Entao isto e um acerto de
uma vez, nao um processo recorrente.

Por que um script e nao uma consulta: o Firestore nao consulta ausencia de campo.
Nao ha `where("data_conclusao", "==", None)` que pegue tambem os documentos onde
a chave nao existe — e nao existir e justamente o caso. A varredura tem de ser
do lado de ca.

De onde vem a data: `data_atualizacao`, que e gravada por todos os caminhos de
escrita. Nao e a data real da conclusao — e a da ultima mexida — mas e a melhor
aproximacao disponivel e erra para o lado seguro: coloca a acao mais perto do
presente, onde ela sera vista, em vez de enterra-la no passivo antigo. Quando nem
`data_atualizacao` existir, cai em `data_criacao`; sem as duas, o script reporta e
nao inventa.

Uso: python scripts/backfill_data_conclusao.py [--apply]
Sem --apply, roda em modo dry-run (so mostra o que faria).
"""
import sys

import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'

STATUS_CONCLUIDO = 'concluído'


def init_db():
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()


def data_de_reposicao(dados):
    for campo in ('data_atualizacao', 'data_criacao'):
        valor = str(dados.get(campo) or '').strip()
        if valor:
            return valor, campo
    return None, None


def main():
    aplicar = '--apply' in sys.argv
    db = init_db()

    sem_data, sem_nada = [], []
    for doc in db.collection('tarefas').where('status', '==', STATUS_CONCLUIDO).stream():
        dados = doc.to_dict() or {}
        if str(dados.get('data_conclusao') or '').strip():
            continue
        valor, origem = data_de_reposicao(dados)
        alvo = sem_data if valor else sem_nada
        alvo.append((doc.id, str(dados.get('titulo') or '(sem titulo)'), valor, origem))

    print(f'Concluidas sem data_conclusao: {len(sem_data) + len(sem_nada)}')
    for task_id, titulo, valor, origem in sem_data:
        print(f'  {task_id}  {titulo[:60]:<60}  -> {valor}  (de {origem})')
    for task_id, titulo, _v, _o in sem_nada:
        print(f'  {task_id}  {titulo[:60]:<60}  -> SEM DATA NENHUMA, nao tocado')

    if not aplicar:
        print('\nDry-run. Rode com --apply para gravar.')
        return 0

    for task_id, _titulo, valor, _origem in sem_data:
        db.collection('tarefas').document(task_id).update({'data_conclusao': valor})
    print(f'\n{len(sem_data)} acao(oes) atualizada(s).')
    if sem_nada:
        print(f'{len(sem_nada)} sem data de origem — precisam de decisao manual.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
