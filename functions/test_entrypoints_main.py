"""Toda Cloud Function publicada precisa existir em `main` com o proprio nome.

O deploy descobre as funcoes pelos membros de `main` e registra cada uma pelo
nome dela (`__firebase_endpoint__.entryPoint`); na partida, o servidor procura
exatamente esse nome em `main`. Importar com apelido
(`from x import f as f_apelido`) passa no deploy e derruba o conteiner: foi o
que aconteceu com `fechar_mes_financeiro` em 13/10/2026 — deploy verde, funcao
sem subir e o job do Cloud Scheduler nunca criado.
"""

import inspect
import unittest

import main


class TestEntrypoints(unittest.TestCase):
    def test_toda_funcao_publicada_existe_com_o_proprio_nome(self):
        divergentes = []
        for nome, funcao in inspect.getmembers(main, inspect.isfunction):
            endpoint = getattr(funcao, "__firebase_endpoint__", None)
            if endpoint is None:
                continue
            if getattr(main, endpoint.entryPoint, None) is not funcao:
                divergentes.append(f"{nome} -> procurada como {endpoint.entryPoint}")
        self.assertEqual(divergentes, [])


if __name__ == "__main__":
    unittest.main()
