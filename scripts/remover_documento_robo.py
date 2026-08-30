"""Apaga o documento orfao do robo de NFS-e, credencial inclusive.

O gerador de NFS-e foi removido do Hermes: o portal da prefeitura mudou e o
recurso era usado raramente. Com o componente fora, `automations/hermes_robot`
nao tem mais nenhum escritor nem nenhum leitor do lado do app — e o documento
guarda `params.portal_login` e `params.portal_senha`.

## Por que apagar o documento inteiro, e nao so `params`

Verificado em 30/08: o documento estava com as duas credenciais e travado em
`status: processing` desde 19/03/2026. Cinco meses.

Isso condena a mitigacao que se cogitou antes — limpar `params` quando o robo
saisse de `requested`. Num documento travado em `processing` esse gatilho nunca
dispara, e foi exatamente por isso que a credencial ficou la. Limpeza que
depende de uma transicao de estado nao protege nada quando o estado nao
transiciona.

Sem componente nao ha o que preservar no documento: nem status, nem params, nem
timestamp. O documento inteiro sai.

## O que este script NAO faz

Apagar aqui nao desfaz a exposicao. O valor trafegou ate o servidor, pode estar
em backup ou ponto de recuperacao do projeto, e esta no IndexedDB de qualquer
navegador que abriu o app (o Firestore roda com cache persistente). O
encerramento real e TROCAR a senha no portal, e limpar os dados do site no
navegador.

Isto remove o dado de onde ele ainda esta acessivel; nao apaga o passado.

## Sobre nao imprimir o valor

O script diz se o campo existe, nunca o que ele contem — a saida vai parar em
terminal, log ou captura de tela.

Uso:
  python scripts/remover_documento_robo.py            # dry-run: so mostra
  python scripts/remover_documento_robo.py --apply    # apaga o documento
"""
import sys

import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'

COLECAO, DOCUMENTO = 'automations', 'hermes_robot'
CAMPOS_CREDENCIAL = ('portal_login', 'portal_senha')


def init_db():
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()


def main():
    aplicar = '--apply' in sys.argv
    db = init_db()

    ref = db.collection(COLECAO).document(DOCUMENTO)
    snap = ref.get()
    if not snap.exists:
        print(f'{COLECAO}/{DOCUMENTO} nao existe. Nada a fazer.')
        return

    dados = snap.to_dict() or {}
    params = dados.get('params') or {}
    presentes = [c for c in CAMPOS_CREDENCIAL if params.get(c) not in (None, '')]

    print(f'Documento: {COLECAO}/{DOCUMENTO}')
    print(f'Status:    {dados.get("status") or "(sem status)"}')
    print(f'Gravado:   {dados.get("timestamp") or "(sem timestamp)"}')
    print(f'Campos:    {", ".join(sorted(dados.keys())) or "(vazio)"}')
    print()
    for campo in CAMPOS_CREDENCIAL:
        print(f'  params.{campo}: {"PRESENTE" if campo in presentes else "ausente"}')

    if presentes:
        print('\n*** HA CREDENCIAL NESTE DOCUMENTO. ***')
        print('Apagar o documento nao desfaz a exposicao: o valor ja passou pelo')
        print('servidor, pode estar em backup, e esta no cache do navegador.')
        print('TROQUE A SENHA DO PORTAL e limpe os dados do site no navegador.')

    if not aplicar:
        print('\nDry-run. Rode com --apply para apagar o documento.')
        return

    ref.delete()
    print(f'\nDocumento {COLECAO}/{DOCUMENTO} apagado.')
    if presentes:
        print('Se ainda nao trocou a senha do portal, troque agora.')


if __name__ == '__main__':
    main()
