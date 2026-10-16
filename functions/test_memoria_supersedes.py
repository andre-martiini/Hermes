"""Testes para P06 sub-entrega 4/N (docs/plano-hermes-autonomo-2026-09-06.md,
pacote P06, passo 4): "Modelar fatos temporais e relação supersedes;
correção invalida derivados e checkpoints de planos afetados."

Cobre:
- `autonomy.temporal`: vocabulário de status e leitura defensiva
  (`memoria_status_de_leitura`), e os payloads puros da transição
  (`payload_documento_historico`/`payload_documento_vivo_apos_substituicao`).
- `copilot_context._format_recent_memories`: um documento `superada` não
  deve aparecer como "memória recente" no contexto de voz.

LIMITAÇÃO DE ESCOPO DESCOBERTA DURANTE ESTA SUB-ENTREGA (registrada também
em docs/autonomia/execucao.md): o desenho original previa fiar
`autonomy.temporal` em `main._save_memory_node` (criar o documento
histórico na substituição) e em `main._find_similar_memory_nodes` (excluir
`superada` da busca de conflito/duplicata) -- ambos IMPLEMENTADOS e
VERIFICADOS localmente (suíte completa passou com as duas fiações ativas),
mas NÃO PUBLICADOS nesta PR: `functions/main.py` tem ~726.000 caracteres,
muito acima do limite de 200.000 caracteres do parâmetro `conteudo` de
`argos_escrever_arquivo_repositorio` (confirmado via probe real contra o
branch desta sub-entrega -- não é só o `maxLength` documentado no schema,
o arquivo realmente não cabe). Esse limite é o MESMO motivo, com a mesma
ordem de grandeza (~64000 tokens de saída por chamada de escrita do Argos),
que levou a modularizar `hermes_core_logic.py`/`telegram_utils.py` no P02
(ver decisão do André de 2026-09-08, citada em `autonomy/context.py`) --
`main.py` nunca foi dividido do mesmo jeito e cresceu além desse teto
também. Isso bloqueia QUALQUER sub-entrega futura que precise editar
`main.py` via esta tool, não só esta. Os dois testes que exercitavam essas
fiações reais (`main._save_memory_node` criando o histórico;
`main._find_similar_memory_nodes` filtrando `superada` via varredura local)
foram escritos, passaram localmente, e foram removidos deste arquivo antes
da publicação -- publicá-los sem o código correspondente em `main.py`
quebraria a suíte de quem rodar os testes contra o repositório real. O
diff completo pretendido para `main.py` está registrado no relatório desta
sub-entrega (texto do agente) e em `docs/autonomia/execucao.md`, para
quando `main.py` for dividido ou a tool de escrita ganhar suporte a arquivo
grande/patch.

Pendência adicional (menor, não bloqueante): o bloco "MEMÓRIA GLOBAL ATIVA"
de `telegram_handlers_core.py` recebeu o MESMO filtro de defesa em
profundidade (`memoria_status_de_leitura`) -- esse arquivo É pequeno o
bastante para ser publicado -- mas não tem teste dedicado aqui: está
embutido em `_process_telegram_message`, uma função grande que exigiria
mockar boa parte do pipeline Gemini/Telegram só para exercitar um filtro de
2 linhas já coberto exaustivamente pelos testes de `autonomy.temporal`
abaixo (mesma função, mesmo comportamento). Risco/custo avaliado como
desproporcional para esta sub-entrega -- decisão registrada aqui e no
diário, não escondida. Hoje esse filtro (e o de `copilot_context.py`) é um
no-op em produção: nada grava `memoria_status=superada` ainda (isso
dependia da fiação em `main.py` que não pôde ser publicada), mas fica
pronto e testado para quando essa fiação for publicada.
"""

import unittest

from test_outbox_aprovacao import _MockDb

from autonomy.temporal import (
    STATUS_ATIVA,
    STATUS_SUPERADA,
    STATUS_VALIDOS,
    memoria_status_de_leitura,
    payload_documento_historico,
    payload_documento_vivo_apos_substituicao,
)
import copilot_context


class TestMemoriaStatusDeLeitura(unittest.TestCase):
    def test_documento_none_e_ativa(self):
        self.assertEqual(memoria_status_de_leitura(None), STATUS_ATIVA)

    def test_documento_vazio_e_ativa(self):
        self.assertEqual(memoria_status_de_leitura({}), STATUS_ATIVA)

    def test_campo_ausente_e_ativa(self):
        """Todo documento gravado antes de qualquer sub-entrega de P06 nunca
        teve `memoria_status` -- precisa continuar lido como ativo."""
        self.assertEqual(memoria_status_de_leitura({"texto_memoria": "x"}), STATUS_ATIVA)

    def test_valor_ativa_e_preservado(self):
        self.assertEqual(memoria_status_de_leitura({"memoria_status": "ativa"}), STATUS_ATIVA)

    def test_valor_superada_e_preservado(self):
        self.assertEqual(memoria_status_de_leitura({"memoria_status": "superada"}), STATUS_SUPERADA)

    def test_valor_desconhecido_cai_em_ativa(self):
        """Diferente de `origem_fato_de_leitura` (que tem um marcador
        explícito de legado, `legacy_unknown`), aqui o default seguro de um
        valor fora da taxonomia é o MESMO `STATUS_ATIVA` -- não existe
        marcador de 'status desconhecido' porque todo documento sem o campo
        sempre foi, por definição, ativo."""
        self.assertEqual(
            memoria_status_de_leitura({"memoria_status": "valor_do_futuro"}), STATUS_ATIVA
        )

    def test_valor_none_cai_em_ativa(self):
        self.assertEqual(memoria_status_de_leitura({"memoria_status": None}), STATUS_ATIVA)

    def test_valor_tipo_lista_nao_lanca_e_cai_em_ativa(self):
        """Mesmo achado de robustez de `origem_fato_de_leitura`
        (`autonomy/context.py`): `valor in STATUS_VALIDOS` sem checar o tipo
        antes lançaria `TypeError: unhashable type` para uma lista."""
        self.assertEqual(memoria_status_de_leitura({"memoria_status": ["x"]}), STATUS_ATIVA)

    def test_valor_tipo_dict_nao_lanca_e_cai_em_ativa(self):
        self.assertEqual(memoria_status_de_leitura({"memoria_status": {"a": 1}}), STATUS_ATIVA)

    def test_valor_tipo_numero_nao_lanca_e_cai_em_ativa(self):
        self.assertEqual(memoria_status_de_leitura({"memoria_status": 123}), STATUS_ATIVA)

    def test_status_validos_contem_os_dois_valores(self):
        self.assertEqual(STATUS_VALIDOS, frozenset({STATUS_ATIVA, STATUS_SUPERADA}))


class TestPayloadDocumentoHistorico(unittest.TestCase):
    def test_preserva_todos_os_campos_do_conteudo_anterior(self):
        anterior = {
            "texto_memoria": "fato antigo",
            "tipo": "preferencia",
            "embedding": [0.1, 0.2],
            "data_criacao": "2026-01-01T00:00:00+00:00",
            "origem_fato": "declaracao_humana",
        }
        payload = payload_documento_historico(
            conteudo_anterior=anterior, novo_id="hist-1",
            supersedido_por="mem-viva", agora="2026-10-14T12:00:00+00:00",
        )
        self.assertEqual(payload["texto_memoria"], "fato antigo")
        self.assertEqual(payload["tipo"], "preferencia")
        self.assertEqual(payload["embedding"], [0.1, 0.2])
        self.assertEqual(payload["origem_fato"], "declaracao_humana")
        # data_criacao do fato ORIGINAL não é tocada pela transição.
        self.assertEqual(payload["data_criacao"], "2026-01-01T00:00:00+00:00")

    def test_sobrescreve_campos_de_status_relacao_e_id(self):
        anterior = {
            "texto_memoria": "fato antigo",
            "memoria_status": "ativa",
            # Todo documento vivo grava "id" igual ao PRÓPRIO id de
            # documento ("mem-viva") -- nunca o de um histórico ainda a
            # nascer. `novo_id` precisa sobrescrever isso.
            "id": "mem-viva",
        }
        payload = payload_documento_historico(
            conteudo_anterior=anterior, novo_id="hist-1",
            supersedido_por="mem-viva", agora="2026-10-14T12:00:00+00:00",
        )
        self.assertEqual(payload["memoria_status"], STATUS_SUPERADA)
        self.assertEqual(payload["superada_por"], "mem-viva")
        self.assertEqual(payload["validade_fim"], "2026-10-14T12:00:00+00:00")
        self.assertEqual(payload["data_atualizacao"], "2026-10-14T12:00:00+00:00")
        # Achado real de revisão adversarial: sem a sobrescrita de "id", o
        # histórico ficaria com "id": "mem-viva" (herdado), em vez do seu
        # PRÓPRIO id ("hist-1").
        self.assertEqual(payload["id"], "hist-1")

    def test_preserva_cadeia_de_supersedes_de_uma_substituicao_anterior(self):
        """Se `conteudo_anterior` já é, ele próprio, o resultado de uma
        substituição anterior (tem `supersedes` apontando para um histórico
        AINDA mais antigo), esse campo deve ser preservado -- a lineage
        completa não se perde."""
        anterior = {
            "texto_memoria": "fato V2 (já havia substituído V1)",
            "supersedes": "hist-v1",
            "validade_inicio": "2026-05-01T00:00:00+00:00",
        }
        payload = payload_documento_historico(
            conteudo_anterior=anterior, novo_id="hist-v2",
            supersedido_por="mem-viva", agora="2026-10-14T12:00:00+00:00",
        )
        self.assertEqual(payload["supersedes"], "hist-v1")
        self.assertEqual(payload["validade_inicio"], "2026-05-01T00:00:00+00:00")

    def test_nao_modifica_o_dict_original(self):
        """Cópia defensiva -- o dict `current` lido do Firestore por
        `_save_memory_node` não deve ser mutado por este payload (ele ainda
        é usado depois, para `previous_text`)."""
        anterior = {"texto_memoria": "fato antigo"}
        payload_documento_historico(
            conteudo_anterior=anterior, novo_id="hist-1",
            supersedido_por="mem-viva", agora="2026-10-14T12:00:00+00:00",
        )
        self.assertNotIn("memoria_status", anterior)
        self.assertNotIn("superada_por", anterior)
        self.assertNotIn("id", anterior)


class TestPayloadDocumentoVivoAposSubstituicao(unittest.TestCase):
    def test_contem_so_os_campos_da_relacao(self):
        payload = payload_documento_vivo_apos_substituicao("mem-historico", "2026-10-14T12:00:00+00:00")
        self.assertEqual(
            payload,
            {"supersedes": "mem-historico", "validade_inicio": "2026-10-14T12:00:00+00:00"},
        )


class TestFormatRecentMemoriesIgnoraSuperada(unittest.TestCase):
    def test_memoria_superada_nao_aparece_no_contexto_de_voz(self):
        db = _MockDb()
        db.collection("knowledge_nodes").document("mem-ativa").set({
            "tipo": "preferencia",
            "texto_memoria": "André prefere reuniões pela manhã.",
            "data_criacao": "2026-10-01T00:00:00+00:00",
        })
        db.collection("knowledge_nodes").document("mem-superada").set({
            "tipo": "preferencia",
            "texto_memoria": "André prefere reuniões pela tarde.",
            "data_criacao": "2026-10-14T00:00:00+00:00",
            "memoria_status": "superada",
        })

        resultado = copilot_context._format_recent_memories(db)

        self.assertIn("reuniões pela manhã", resultado)
        self.assertNotIn("reuniões pela tarde", resultado)


if __name__ == "__main__":
    unittest.main()
