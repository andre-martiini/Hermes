"""Verifica (e opcionalmente remove) credenciais gravadas no documento do robo.

Contexto: `NFSeGenerator` grava `params.portal_login` e `params.portal_senha` em
`automations/hermes_robot` para o `robot_bridge.py` consumir. Como o Firestore
guarda o documento em repouso e o app usa cache persistente, a credencial fica
no servidor e no IndexedDB do navegador.

Ate o PR #137 o painel que aciona a emissao era codigo morto e o botao era
inalcancavel, entao provavelmente nunca houve escrita. "Provavelmente" nao serve
para credencial: este script confere.

## O que este script NAO faz

Remover o campo aqui NAO desfaz a exposicao. O valor ja trafegou ate o servidor,
pode estar em backup ou em ponto de recuperacao do projeto, e pode estar no
IndexedDB de qualquer navegador que abriu o app. Se houver senha gravada, o
unico encerramento real e TROCAR a senha no portal.

Isto e uma limpeza, nao um conserto. O conserto e a credencial deixar de passar
pelo Firestore, e depende do `robot_bridge.py`, que roda localmente.

## Sobre nao imprimir o valor

O script diz se o campo existe, nunca o que ele contem — inclusive porque a
saida costuma ir parar em terminal, log ou captura de tela.

Uso:
  python scripts/auditar_credenciais_robo.py            # so verifica
  python scripts/auditar_credenciais_robo.py --limpar   # remove os campos
"""
import sys

import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'

DOC = ('automations', 'hermes_robot')
CAMPOS_CREDENCIAL = ('portal_login', 'portal_senha')

# Estados em que o robo ainda esta trabalhando. Espelha `STATUS_ROBO_ATIVO` em
# `src/components/NFSeGenerator.tsx`: apagar `params` no meio de uma execucao
# tiraria o chao da ponte.
STATUS_ATIVOS = ('requested', 'processing', 'login_confirmed')


def init_db():
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()


def main():
    limpar = '--limpar' in sys.argv
    db = init_db()

    ref = db.collection(DOC[0]).document(DOC[1])
    snap = ref.get()
    if not snap.exists:
        print(f'Documento {DOC[0]}/{DOC[1]} nao existe. Nada gravado.')
        return

    dados = snap.to_dict() or {}
    params = dados.get('params') or {}
    status = str(dados.get('status') or '(sem status)')
    presentes = [c for c in CAMPOS_CREDENCIAL if params.get(c) not in (None, '')]

    print(f'Documento: {DOC[0]}/{DOC[1]}')
    print(f'Status:    {status}')
    print(f'Gravado:   {dados.get("timestamp") or "(sem timestamp)"}')
    print()
    for campo in CAMPOS_CREDENCIAL:
        print(f'  {campo}: {"PRESENTE" if campo in presentes else "ausente"}')

    if not presentes:
        print('\nNenhuma credencial gravada. Nada a fazer.')
        return

    print('\n*** HA CREDENCIAL GRAVADA NESTE DOCUMENTO. ***')
    print('Troque a senha do portal. Remover o campo nao desfaz a exposicao:')
    print('o valor ja passou pelo servidor e pode estar em backup e no cache')
    print('do navegador.')

    if not limpar:
        print('\nRode com --limpar para remover os campos do documento.')
        return

    if status in STATUS_ATIVOS:
        print(f'\nNAO removido: o robo esta em "{status}", ou seja, em execucao.')
        print('Apagar `params` agora derruba a emissao em andamento. Espere')
        print('terminar e rode de novo.')
        sys.exit(1)

    ref.update({f'params.{c}': firestore.DELETE_FIELD for c in presentes})
    print(f'\nRemovidos do documento: {", ".join(presentes)}.')
    print('Lembre: isto e limpeza, nao conserto. Troque a senha do portal.')


if __name__ == '__main__':
    main()
