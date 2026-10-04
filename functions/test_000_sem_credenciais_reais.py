"""Os testes nunca alcançam o Google de verdade.

Este módulo tem o nome que o põe em primeiro lugar na descoberta do unittest
(a da CI) e, ao ser importado, aponta a credencial padrão do Google para um
arquivo inexistente — antes que qualquer teste crie um cliente do Firestore. No
pytest o mesmo vale pelo conftest.py.

Por quê: neste computador as credenciais padrão do gcloud apontam para a
produção. Em 04/10/2026 havia ~2.100 chamadas falsas de usuários de teste
(dono-uid, uid-de-teste...) no `mcp_audit_log` de produção, gravadas por testes
que chegavam a `firestore.client()` sem mock.
"""

import os
import unittest

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_credencial_inexistente_nos_testes.json")


class TestSemCredenciaisReais(unittest.TestCase):
    def test_credencial_padrao_aponta_para_arquivo_inexistente(self):
        caminho = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        self.assertTrue(caminho)
        self.assertFalse(os.path.exists(caminho), "a credencial dos testes não pode existir")

    def test_cliente_do_google_nao_consegue_credencial(self):
        import google.auth
        from google.auth.exceptions import DefaultCredentialsError

        with self.assertRaises(DefaultCredentialsError):
            google.auth.default()


if __name__ == "__main__":
    unittest.main()
