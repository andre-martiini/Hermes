"""Conta o passivo: acoes concluidas que nao apontam para nenhum objetivo.

Contexto: o detector de subproduto passou a olhar acoes concluidas na varredura
semanal, mas so as concluidas desde a ultima varredura. Tudo que foi concluido
antes disso e passivo, e a decisao sobre passa-lo de uma vez depende de volume:
uma passagem unica sobre um passivo grande deixa a fila ilegivel, e uma fila que
ninguem le mata o modulo. Este script existe para dar o numero antes da decisao.

Por que um script e nao uma consulta: o Firestore nao consulta ausencia de
campo. Nao ha `where("estrategia_objetivo_id", "==", None)` que pegue tambem os
documentos onde a chave simplesmente nao existe — e a maioria dos documentos
antigos nao tem a chave. Entao a unica forma correta e ler as concluidas e
contar do lado de ca.

So le. Nao grava nada.

Uso: python scripts/contar_concluidas_sem_vinculo.py [--listar ANO[,ANO...]]

Com --listar, imprime titulo, area, data e se tem corpo das concluidas daqueles
anos. Serve para conferir se sao acoes reais antes de deixa-las entrar na fila:
concluida de 2015 num sistema que comecou depois cheira a dado migrado ou a data
retroagida, e sugestao em cima disso e ruido que gasta a confianca do modulo.
"""
import sys
from collections import Counter

import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'

STATUS_CONCLUIDO = 'concluído'


def init_db():
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()


def tem_vinculo(dados):
    """Vazio, nulo e ausente sao todos "sem vinculo" — e ausente e o caso comum."""
    return bool(str(dados.get('estrategia_objetivo_id') or '').strip())


def tem_corpo(dados):
    """O mesmo criterio do detector, sem importar o modulo (que vive em functions/).

    Aproximacao deliberada: conta anexo de texto, diario longo ou etapas feitas.
    Serve para separar "passivo" de "passivo que geraria sugestao", que e o
    numero que importa para decidir sobre a passagem unica.
    """
    extensoes = ('.md', '.markdown', '.txt', '.doc', '.docx', '.odt', '.tex')
    for item in (dados.get('pool_dados') or []):
        if not isinstance(item, dict) or item.get('tipo') != 'arquivo':
            continue
        nome = str(item.get('nome') or item.get('titulo') or '').lower()
        if nome.endswith(extensoes):
            return True
    diario = '\n'.join(
        str(e.get('nota') or '') for e in (dados.get('acompanhamento') or [])
        if isinstance(e, dict))
    if len(diario) >= 1200:
        return True
    # Mesma deducao de `subtarefas.estado_de`: `estado` quando existir, senao
    # `completed`. Contar so `completed` erraria nas etapas gravadas no formato
    # novo, que e o da maioria das acoes recentes.
    def feita(passo):
        if not isinstance(passo, dict):
            return False
        estado = str(passo.get('estado') or '').strip().lower()
        return estado == 'feito' if estado else bool(passo.get('completed'))

    return sum(1 for p in (dados.get('plano_acao') or []) if feita(p)) >= 3


def anos_pedidos():
    for i, arg in enumerate(sys.argv):
        if arg == '--listar' and i + 1 < len(sys.argv):
            return {a.strip() for a in sys.argv[i + 1].split(',') if a.strip()}
    return set()


def main():
    db = init_db()
    listar = anos_pedidos()
    total = com_vinculo = sem_vinculo = sem_vinculo_com_corpo = 0
    sem_data = 0
    por_ano = Counter()
    listadas = []

    for doc in db.collection('tarefas').where('status', '==', STATUS_CONCLUIDO).stream():
        dados = doc.to_dict() or {}
        total += 1
        if listar and str(dados.get('data_conclusao') or '')[:4] in listar:
            listadas.append((
                str(dados.get('data_conclusao') or '')[:10],
                doc.id,
                str(dados.get('titulo') or '(sem titulo)'),
                str(dados.get('area_tematica') or dados.get('area') or '-'),
                'com corpo' if tem_corpo(dados) else 'sem corpo',
                str(dados.get('data_criacao') or '')[:10],
            ))
        if tem_vinculo(dados):
            com_vinculo += 1
            continue
        sem_vinculo += 1
        data = str(dados.get('data_conclusao') or '')[:4]
        if data:
            por_ano[data] += 1
        else:
            sem_data += 1
        if tem_corpo(dados):
            sem_vinculo_com_corpo += 1

    print(f'Acoes concluidas no total:            {total}')
    print(f'  com vinculo estrategico:            {com_vinculo}')
    print(f'  SEM vinculo (o passivo):            {sem_vinculo}')
    print(f'  destas, com corpo (gerariam card):  {sem_vinculo_com_corpo}')
    print(f'  sem data_conclusao gravada:         {sem_data}')
    if por_ano:
        print('\nPassivo por ano de conclusao:')
        for ano in sorted(por_ano):
            print(f'  {ano}: {por_ano[ano]}')
    print('\nO numero que decide o ritmo e "com corpo": e quantos cards a fila '
          'receberia se o passivo entrasse de uma vez.')

    if listar:
        print(f'\nConcluidas de {", ".join(sorted(listar))} ({len(listadas)}):')
        print(f'  {"conclusao":<12} {"criacao":<12} {"corpo":<10} {"area":<12} titulo')
        for data, task_id, titulo, area, corpo, criacao in sorted(listadas):
            print(f'  {data:<12} {criacao:<12} {corpo:<10} {area[:12]:<12} {titulo[:70]}')
        print('\nConfira se sao acoes reais. Data de conclusao muito anterior a de '
              'criacao e sinal de retroacao ou migracao.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
