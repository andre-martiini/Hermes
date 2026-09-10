import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, '.')

from inbox_pendentes import (
    DISPENSA_COLLECTION,
    LLM_CLASSIFICACAO_COLLECTION,
    _LLM_MAX_CLASSIFICACOES_POR_PASSADA,
    _chave_cache_classificacao,
    _chave_item_dispensavel,
    _classificar_necessidade_resposta,
    atualizar_whatsapp_em_lote,
    backfill_whatsapp_inicial,
    coletar,
    dispensar,
)


class Doc:
    def __init__(self, doc_id, data):
        self.id, self.data, self.exists = doc_id, data, data is not None
    def to_dict(self): return dict(self.data or {})
    def get(self): return self
    def set(self, fields, merge=False):
        # DEV-2026-0004 sub-entrega 7/9: suporte a escrita, usado pelo cache
        # do classificador LLM (`_classificar_necessidade_resposta`). Nenhum
        # teste anterior a esta sub-entrega chamava `.set()` neste fake --
        # adicionado sem mudar o comportamento de leitura já existente.
        self.data = {**(self.data or {}), **fields} if merge else dict(fields)
        self.exists = True


class Query:
    # DEV-2026-0004 sub-entrega 7/9: recebe (e devolve, via `document()`) o
    # MESMO dict de Docs vivos da coleção -- não uma lista nova a cada
    # chamada -- para que um `.set()` feito por uma chamada anterior a
    # `db.collection(name)` fique visível para a próxima. Antes desta
    # sub-entrega nada aqui escrevia, então a diferença é invisível para os
    # testes já existentes (mesmo conteúdo, mesma ordem de `.stream()`).
    def __init__(self, docs_by_id): self.docs_by_id = docs_by_id
    def stream(self): return list(self.docs_by_id.values())
    def document(self, wanted):
        if wanted not in self.docs_by_id:
            self.docs_by_id[wanted] = Doc(wanted, None)
        return self.docs_by_id[wanted]


class Db:
    def __init__(self, collections):
        self.collections = collections
        self._live = {}
    def collection(self, name):
        if name not in self._live:
            self._live[name] = {k: Doc(k, v) for k, v in self.collections.get(name, {}).items()}
        return Query(self._live[name])


class InboxPendentesTest(unittest.TestCase):
    def test_filtro_de_ruido_conta_e_preserva_pergunta_e_legenda(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['a', 'b', 'c', 'd']}}},
            'perfil_pessoas': {}, 'tarefas': {}, 'email_action_suggestions': {},
            'inbox_pendentes': {
                'a': {'tipo': 'whatsapp', 'chat_id': 'a', 'trecho': 'Ok', 'desde': '2026-09-01T08:00:00+00:00'},
                'b': {'tipo': 'whatsapp', 'chat_id': 'b', 'trecho': '/9j/4AAQ', 'desde': '2026-09-01T08:00:00+00:00'},
                'c': {'tipo': 'whatsapp', 'chat_id': 'c', 'trecho': 'Você pode confirmar? Obrigada', 'desde': '2026-09-01T08:00:00+00:00'},
                'd': {'tipo': 'whatsapp', 'chat_id': 'd', 'trecho': 'segue a planilha', 'desde': '2026-09-01T08:00:00+00:00'},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(result['filtrados'], {'automaticos': 0, 'encerramentos': 1, 'sem_texto': 1, 'informativo': 0,
                                                'informativo_llm': 0, 'encerramentos_llm': 0,
                                                'tratado_na_acao': 0, 'tratado_em_outro_canal': 0, 'dispensados': 0})
        self.assertEqual({x['trecho'] for x in result['itens']}, {'Você pode confirmar? Obrigada', 'segue a planilha'})

    def test_auditoria_inclui_itens_filtrados(self):
        db = Db({'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['a']}}}, 'perfil_pessoas': {}, 'tarefas': {}, 'email_action_suggestions': {},
                 'inbox_pendentes': {'a': {'tipo': 'whatsapp', 'chat_id': 'a', 'trecho': 'Ok', 'desde': '2026-09-01T08:00:00+00:00'}}})
        self.assertEqual(len(coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc), incluir_filtrados=True)['itens']), 1)

    def test_data_textual_e_remetente_com_nome(self):
        db = Db({'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}}, 'perfil_pessoas': {},
                 'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
                 'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'trecho': 'Data: 5 de setembro, confirma?', 'desde': '2026-09-01T08:00:00+00:00'}},
                 'email_action_suggestions': {'e': {'canal': 'email', 'status': 'applied', 'task_id': 't', 'sender': 'Newsletter <newsletter@example.com>', 'snippet': 'oferta', 'internal_date': '2026-09-01T08:00:00+00:00'}}})
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual([x['trecho'] for x in result['itens']], ['Data: 5 de setembro, confirma?'])
        self.assertEqual(result['filtrados']['automaticos'], 1)
    def test_lista_tres_recebidas_ordem_e_exclui_enviada_pausada(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['a', 'b', 'c', 'd', 'e']}}},
            'perfil_pessoas': {'a': {'nome': 'Gabriela', 'whatsapp_chat_id': 'a'}},
            'tarefas': {},
            'email_action_suggestions': {},
            'inbox_pendentes': {
                'a': {'tipo': 'whatsapp', 'chat_id': 'a', 'desde': '2026-09-01T06:00:00+00:00', 'trecho': 'A'},
                'b': {'tipo': 'whatsapp', 'chat_id': 'b', 'chat_name': 'Ezequiel', 'desde': '2026-09-01T08:00:00+00:00', 'trecho': 'B'},
                'c': {'tipo': 'whatsapp', 'chat_id': 'c', 'chat_name': 'Marcelo', 'desde': '2026-09-01T10:00:00+00:00', 'trecho': 'C'},
                'd': {'tipo': 'whatsapp', 'chat_id': 'd', 'ultima_de_andre': True, 'desde': '2026-09-01T01:00:00+00:00'},
                'e': {'tipo': 'whatsapp', 'chat_id': 'e', 'desde': '2026-09-01T00:00:00+00:00', 'pausada_ate': '2026-09-02T00:00:00+00:00'},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual([x['contato'] for x in result['itens']], ['Gabriela', 'Ezequiel', 'Marcelo'])

    def test_grupo_sem_acao_ativa_e_excluido_na_regra_conservadora(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['g']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {},
            'tarefas': {},
            'inbox_pendentes': {'g': {'tipo': 'whatsapp', 'chat_id': 'g', 'is_group': True,
                'trecho': 'precisamos decidir', 'desde': '2026-09-01T10:00:00+00:00'}},
        })
        self.assertEqual(coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))['itens'], [])

    def test_status_stand_by_alias_mantem_grupo_vinculado(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['g']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'stand by', 'whatsapp_vinculos': [{'chat_id': 'g'}]}},
            'inbox_pendentes': {'g': {'tipo': 'whatsapp', 'chat_id': 'g', 'is_group': True,
                'trecho': 'precisamos decidir', 'desde': '2026-09-01T10:00:00+00:00'}},
        })
        self.assertEqual([x['contato'] for x in coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))['itens']], ['g'])

    def test_email_respondido_fecha_toda_a_thread(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': []}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {},
            'email_action_suggestions': {
                'old': {'canal': 'email', 'status': 'applied', 'task_id': 't', 'gmail_thread_id': 'thread',
                        'internal_date': '2026-09-01T08:00:00+00:00', 'sender': 'proad'},
                'new': {'canal': 'email', 'status': 'applied', 'task_id': 't', 'gmail_thread_id': 'thread',
                        'internal_date': '2026-09-01T10:00:00+00:00', 'ultima_mensagem_de_andre': True, 'sender': 'proad'},
            },
        })
        self.assertEqual(coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))['itens'], [])

    def test_grupo_com_resposta_a_andre_entra_sem_acao(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['g']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {}, 'tarefas': {},
            'inbox_pendentes': {'g': {'tipo': 'whatsapp', 'chat_id': 'g', 'chat_name': 'Equipe',
                'is_group': True, 'quoted_msg_id': 'old', 'quoted_from_me': True,
                'trecho': 'precisamos decidir', 'desde': '2026-09-01T10:00:00+00:00'}},
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual([x['contato'] for x in result['itens']], ['Equipe'])

    def test_grupos_aplicam_regra_fina_e_motivo(self):
        db = Db({'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['a', 'b', 'c', 'd', 'e'], 'andre_chat_ids': ['andre@c.us']}}},
                 'perfil_pessoas': {}, 'email_action_suggestions': {},
                 'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento', 'whatsapp_vinculos': [{'chat_id': 'a'}, {'chat_id': 'b'}, {'chat_id': 'c'}]}},
                 'inbox_pendentes': {
                    'a': {'tipo': 'whatsapp', 'chat_id': 'a', 'is_group': True, 'mentioned_ids': ['andre@c.us'], 'trecho': 'Andre veja', 'desde': '2026-09-01T10:00:00+00:00'},
                    'b': {'tipo': 'whatsapp', 'chat_id': 'b', 'is_group': True, 'mentioned_ids': [], 'quoted_from_me': False, 'trecho': 'conversa alheia', 'desde': '2026-09-01T10:00:00+00:00'},
                    'c': {'tipo': 'whatsapp', 'chat_id': 'c', 'is_group': True, 'trecho': 'metadado antigo', 'desde': '2026-09-01T10:00:00+00:00'},
                    'd': {'tipo': 'whatsapp', 'chat_id': 'd', 'is_group': True, 'quoted_from_me': True, 'trecho': 'respondendo', 'desde': '2026-09-01T10:00:00+00:00'},
                    'e': {'tipo': 'whatsapp', 'chat_id': 'e', 'is_group': True, 'quoted_msg_id': 'q', 'quoted_author': 'andre@c.us', 'trecho': 'respondendo', 'desde': '2026-09-01T10:00:00+00:00'},
                 }})
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))['itens']
        self.assertEqual({x['contato']: x['motivo_inclusao'] for x in result}, {'a': 'mencao', 'c': 'grupo_vinculado', 'd': 'resposta_a_mim', 'e': 'resposta_a_mim'})

    def test_encerramentos_pegam_todos_os_exemplos_do_achado_b4(self):
        """DEV-2026-0004 sub-entrega 3/9 -- os 9 exemplos reais do achado B4 da
        demanda (Fabíola, Silvia, Dério, Mariane, Marcos Marinho, Flávia,
        SollyvanRM, Patrícia Vizinha, +55 61 3424-7018) que o filtro anterior
        (frase inteira precisava ser, ao pé da letra, um item do set) deixava
        passar como falsa resposta pendente."""
        from inbox_pendentes import _DEFAULT_ENDINGS, _noise_reason

        exemplos = [
            "Obrigada pelo retorno",
            "Mto obrigada",
            "Muito obrigado",
            "Blz",
            "Bom dia.\nOk",
            "Ufaaaaa",
            "Boa noite e fique com Deus",
            "Ok, obrigada por avisar",
            "De nada, André!",
        ]
        for trecho in exemplos:
            with self.subTest(trecho=trecho):
                reason = _noise_reason(
                    trecho=trecho, sender="", is_email=False,
                    has_contact=True, has_task=False,
                    domains=set(), endings=_DEFAULT_ENDINGS,
                )
                self.assertEqual(reason, "encerramentos", f"esperava encerramentos para {trecho!r}, veio {reason!r}")

    def test_pergunta_com_palavra_de_encerramento_nao_e_filtrada(self):
        """Regressão: '?' sempre bloqueia a classificação como encerramento,
        mesmo com palavras do léxico presentes no texto."""
        from inbox_pendentes import _DEFAULT_ENDINGS, _noise_reason

        reason = _noise_reason(
            trecho="Perfeito, você pode confirmar o horário?", sender="",
            is_email=False, has_contact=True, has_task=False,
            domains=set(), endings=_DEFAULT_ENDINGS,
        )
        self.assertIsNone(reason)

    def test_pedido_de_verdade_com_palavra_de_encerramento_nao_e_filtrado(self):
        """Achado da (primeira) revisão adversarial desta sub-entrega: a
        versão inicial bastava UMA palavra da mensagem bater no léxico (ou
        uma frase aparecer como substring solta) para classificar como
        encerramento -- isso escondia pedidos de verdade sem '?' que só
        continham uma palavra do léxico em meio a outras. `_is_closing_message`
        agora exige a mensagem INTEIRA seja coberta por itens do léxico."""
        from inbox_pendentes import _DEFAULT_ENDINGS, _noise_reason

        pedidos_reais = [
            "Ok, pode me ligar agora",
            "Entendi, me manda de novo",
            "Combinado, me manda o PIX depois",
            "Entendido, favor enviar o boleto",
            "Bom dia, poderia me confirmar isso",
            "Boa noite, manda o relatorio",
        ]
        for trecho in pedidos_reais:
            with self.subTest(trecho=trecho):
                reason = _noise_reason(
                    trecho=trecho, sender="", is_email=False,
                    has_contact=True, has_task=False,
                    domains=set(), endings=_DEFAULT_ENDINGS,
                )
                self.assertIsNone(reason, f"{trecho!r} é um pedido de verdade, não devia ser filtrado (veio {reason!r})")

    def test_email_so_em_cc_e_classificado_como_informativo(self):
        """Achado B, caso 2 da demanda: Diretoria de Ensino BSF -- e-mail
        endereçado a dae.rei@ifes.edu.br com André só em cópia."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': []}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {},
            'email_action_suggestions': {
                'e': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'sender': 'Diretoria de Ensino <dae.rei@ifes.edu.br>',
                      'snippet': 'Segue o comunicado para conhecimento.',
                      'internal_date': '2026-09-01T08:00:00+00:00',
                      'andre_em_to': False},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(result['itens'], [])
        self.assertEqual(result['filtrados']['informativo'], 1)

    def test_email_com_andre_em_to_nao_e_filtrado_como_informativo(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': []}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {},
            'email_action_suggestions': {
                'e': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'sender': 'Gabriela <gabriela@ifes.edu.br>',
                      'snippet': 'Poderia revisar o anexo até sexta?',
                      'internal_date': '2026-09-01T08:00:00+00:00',
                      'andre_em_to': True},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result['itens']), 1)
        self.assertEqual(result['filtrados']['informativo'], 0)

    def test_email_sem_andre_em_to_gravado_nao_e_filtrado_por_seguranca(self):
        """Sugestão antiga (gravada antes desta sub-entrega) não tem o campo
        `andre_em_to` -- o padrão (None) nunca filtra, para não gerar falsos
        positivos em dados existentes até o próximo refresh preenchê-lo."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': []}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {},
            'email_action_suggestions': {
                'e': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'sender': 'Gabriela <gabriela@ifes.edu.br>',
                      'snippet': 'Poderia revisar o anexo até sexta?',
                      'internal_date': '2026-09-01T08:00:00+00:00'},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result['itens']), 1)

    def test_email_tratado_na_acao_apos_a_mensagem_e_resolvido(self):
        """DEV-2026-0004 sub-entrega 4/9, achado B caso 3: DAE/Proen -- e-mail
        informativo com anexo ('segue a planilha') já tratado na ação
        vinculada, com entrada de diário GENUÍNA posterior à mensagem."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': []}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento',
                               'acompanhamento': [{'data': '2026-09-01T11:00:00+00:00', 'nota': 'Planilha conferida e arquivada.'}]}},
            'inbox_pendentes': {},
            'email_action_suggestions': {
                'e': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'sender': 'DAE/Proen <dae@ifes.edu.br>',
                      'snippet': 'Segue a planilha em anexo.',
                      'internal_date': '2026-09-01T08:00:00+00:00'},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(result['itens'], [])
        self.assertEqual(result['filtrados']['tratado_na_acao'], 1)

    def test_diario_anterior_a_mensagem_nao_resolve(self):
        """Uma nota de diário ANTERIOR à mensagem não é tratamento dela --
        pode ser um follow-up novo que chegou depois e ainda precisa de
        resposta. Só entrada POSTERIOR conta (`>` estrito)."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': []}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento',
                               'acompanhamento': [{'data': '2026-09-01T07:00:00+00:00', 'nota': 'Primeira tratativa.'}]}},
            'inbox_pendentes': {},
            'email_action_suggestions': {
                'e': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'sender': 'Gabriela <gabriela@ifes.edu.br>',
                      'snippet': 'Novidade: precisa de retorno.',
                      'internal_date': '2026-09-01T08:00:00+00:00'},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result['itens']), 1)
        self.assertEqual(result['filtrados']['tratado_na_acao'], 0)

    def test_diario_no_mesmo_instante_da_mensagem_nao_resolve(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': []}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento',
                               'acompanhamento': [{'data': '2026-09-01T08:00:00+00:00', 'nota': 'Nota simultânea.'}]}},
            'inbox_pendentes': {},
            'email_action_suggestions': {
                'e': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'sender': 'Gabriela <gabriela@ifes.edu.br>',
                      'snippet': 'Mensagem.',
                      'internal_date': '2026-09-01T08:00:00+00:00'},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result['itens']), 1)

    def test_entrada_email_json_de_vinculo_nao_conta_como_tratamento(self):
        """A entrada `EMAIL::JSON::` só registra o INSTANTE em que o e-mail
        foi vinculado à ação -- não é evidência de que André tratou o
        assunto. Sem essa exclusão, todo e-mail vinculado seria
        imediatamente 'tratado', já que o próprio vínculo sempre acontece
        depois da mensagem que o originou."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': []}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento',
                               'acompanhamento': [{'data': '2026-09-01T09:00:00+00:00',
                                                    'nota': 'EMAIL::JSON::{"v": "msgid1"}'}]}},
            'inbox_pendentes': {},
            'email_action_suggestions': {
                'msgid1': {'canal': 'email', 'status': 'applied',
                           'sender': 'Gabriela <gabriela@ifes.edu.br>',
                           'snippet': 'Poderia revisar o anexo até sexta?',
                           'internal_date': '2026-09-01T08:00:00+00:00'},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result['itens']), 1)
        self.assertEqual(result['filtrados']['tratado_na_acao'], 0)

    def test_email_json_mais_nota_genuina_posterior_e_resolvido(self):
        """Mesmo vínculo do teste anterior, mas com uma segunda entrada,
        genuína, registrada DEPOIS -- essa sim conta."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': []}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento',
                               'acompanhamento': [
                                   {'data': '2026-09-01T09:00:00+00:00', 'nota': 'EMAIL::JSON::{"v": "msgid1"}'},
                                   {'data': '2026-09-01T11:00:00+00:00', 'nota': 'Despacho enviado ao setor.'},
                               ]}},
            'inbox_pendentes': {},
            'email_action_suggestions': {
                'msgid1': {'canal': 'email', 'status': 'applied',
                           'sender': 'Marcos Marinho <marcos@tjes.jus.br>',
                           'snippet': 'Segue o despacho em anexo.',
                           'internal_date': '2026-09-01T08:00:00+00:00'},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(result['itens'], [])
        self.assertEqual(result['filtrados']['tratado_na_acao'], 1)

    def test_whatsapp_tratado_na_acao_apos_mensagem_e_resolvido(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento',
                               'whatsapp_vinculos': [{'chat_id': 'w'}],
                               'acompanhamento': [{'data': '2026-09-01T11:00:00+00:00', 'nota': 'Já resolvi por telefone.'}]}},
            'email_action_suggestions': {},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'trecho': 'segue a planilha',
                                       'desde': '2026-09-01T08:00:00+00:00'}},
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(result['itens'], [])
        self.assertEqual(result['filtrados']['tratado_na_acao'], 1)

    def test_vinculo_de_outra_conversa_whatsapp_na_mesma_acao_nao_esconde_pendencia_real(self):
        """Cenário concreto do achado da revisão adversarial: a ação `t` tem
        DUAS conversas vinculadas -- `chat_a` (Gabriela, pergunta real às
        08h ainda sem resposta) e `chat_b` (grupo de status). Às 11h André
        aprova, com um clique só, o vínculo de uma mensagem de `chat_b` à
        mesma ação -- isso grava só o marcador `WHATSAPP::JSON::` (sem
        evidenciar tratamento nenhum da pergunta da Gabriela). A pergunta
        dela tem que continuar pendente."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['chat_a', 'chat_b']}}},
            'perfil_pessoas': {'chat_a': {'nome': 'Gabriela', 'whatsapp_chat_id': 'chat_a'}},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento',
                               'whatsapp_vinculos': [{'chat_id': 'chat_a'}, {'chat_id': 'chat_b'}],
                               'acompanhamento': [{'data': '2026-09-01T11:00:00+00:00',
                                                    'nota': 'WHATSAPP::JSON::{"n": "grupo de status"}'}]}},
            'email_action_suggestions': {},
            'inbox_pendentes': {
                'chat_a': {'tipo': 'whatsapp', 'chat_id': 'chat_a', 'trecho': 'Pode revisar isso até amanhã?',
                           'desde': '2026-09-01T08:00:00+00:00'},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual([x['contato'] for x in result['itens']], ['Gabriela'])
        self.assertEqual(result['filtrados']['tratado_na_acao'], 0)

    def test_auditoria_inclui_item_tratado_na_acao(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento',
                               'whatsapp_vinculos': [{'chat_id': 'w'}],
                               'acompanhamento': [{'data': '2026-09-01T11:00:00+00:00', 'nota': 'Já resolvi por telefone.'}]}},
            'email_action_suggestions': {},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'trecho': 'segue a planilha',
                                       'desde': '2026-09-01T08:00:00+00:00'}},
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc), incluir_filtrados=True)
        self.assertEqual(len(result['itens']), 1)

    def test_diario_mais_recente_ignora_marcador_de_vinculo_email_json(self):
        from inbox_pendentes import _diario_mais_recente
        acompanhamento = [
            {'data': '2026-09-01T09:00:00+00:00', 'nota': 'EMAIL::JSON::{"v": "x"}'},
            {'data': '2026-09-01T07:00:00+00:00', 'nota': 'Nota genuína mais antiga.'},
        ]
        self.assertEqual(_diario_mais_recente(acompanhamento).isoformat(), '2026-09-01T07:00:00+00:00')

    def test_diario_mais_recente_sem_entradas_genuinas_devolve_none(self):
        from inbox_pendentes import _diario_mais_recente
        acompanhamento = [{'data': '2026-09-01T09:00:00+00:00', 'nota': 'EMAIL::JSON::{"v": "x"}'}]
        self.assertIsNone(_diario_mais_recente(acompanhamento))

    def test_diario_mais_recente_ignora_marcador_whatsapp_json(self):
        """Achado da revisão adversarial desta sub-entrega: a primeira versão
        só excluía `EMAIL::JSON::`, mas `_build_diary_note` grava o mesmo
        tipo de marcador automático (sem evidenciar tratamento nenhum) ao
        vincular uma conversa de WhatsApp a uma ação -- mesmo fluxo de um
        clique só, mesmo problema."""
        from inbox_pendentes import _diario_mais_recente
        acompanhamento = [{'data': '2026-09-01T09:00:00+00:00', 'nota': 'WHATSAPP::JSON::{"n": "conversa"}'}]
        self.assertIsNone(_diario_mais_recente(acompanhamento))

    def test_diario_mais_recente_ignora_marcador_generico_de_outros_canais(self):
        """Mesmo achado, para o terceiro formato de `_build_diary_note`
        (sipac/calendar/pagina/demais canais): `"[{icone} Hermes] {rótulo}:
        ..."` -- também automático, também sem evidência de tratamento."""
        from inbox_pendentes import _diario_mais_recente
        acompanhamento = [{'data': '2026-09-01T09:00:00+00:00', 'nota': '[📋 Hermes] Processo SIPAC: Requerimento 123'}]
        self.assertIsNone(_diario_mais_recente(acompanhamento))

    def test_diario_mais_recente_escolhe_a_mais_recente_entre_varias_genuinas(self):
        from inbox_pendentes import _diario_mais_recente
        acompanhamento = [
            {'data': '2026-09-01T07:00:00+00:00', 'nota': 'Primeira nota genuína.'},
            {'data': '2026-09-01T09:00:00+00:00', 'nota': 'WHATSAPP::JSON::{"n": "conversa"}'},
            {'data': '2026-09-01T11:00:00+00:00', 'nota': 'Segunda nota genuína, mais recente.'},
            {'data': '2026-09-01T08:00:00+00:00', 'nota': 'Terceira nota genuína, no meio.'},
        ]
        self.assertEqual(_diario_mais_recente(acompanhamento).isoformat(), '2026-09-01T11:00:00+00:00')

    def test_diario_mais_recente_nao_ignora_notas_genuinas_de_copiloto_ou_telegram(self):
        """Achado da SEGUNDA rodada de revisão adversarial: um coringa
        genérico (`\\[\\S+ Hermes\\]`) na primeira correção também casava
        com prefixos de notas GENUÍNAS e confirmadas -- "[Copiloto Hermes]"
        (main.py/editar_plano_acao, editar_acao) e "[Telegram Hermes]"
        (tools/telegram_extended.py) -- excluindo tratamento de verdade da
        comparação (falha no sentido oposto ao achado da primeira rodada:
        em vez de esconder uma pendência real, o auto-resolve deixaria de
        disparar quando deveria). A classe de caracteres restrita aos
        ícones reais de `_CANAL_ICONS` (+ fallback "🔔") corrige isso -- "C"
        de "Copiloto" e "T" de "Telegram" não estão nela."""
        from inbox_pendentes import _diario_mais_recente
        for nota in [
            "[Copiloto Hermes] Plano de ação atualizado: revisão concluída.",
            "[Copiloto Hermes] Ação editada via card de confirmação. Campos alterados: status.",
            "[Telegram Hermes] Plano de ação atualizado: etapa marcada como feita.",
            "[Telegram Hermes] Lembrete agendado para amanhã.",
        ]:
            with self.subTest(nota=nota):
                acompanhamento = [{'data': '2026-09-01T09:00:00+00:00', 'nota': nota}]
                self.assertEqual(
                    _diario_mais_recente(acompanhamento).isoformat(), '2026-09-01T09:00:00+00:00',
                    f"{nota!r} é uma nota genuína, não devia ser tratada como marcador automático",
                )

    def test_resolved_by_diario_compara_a_data_ja_calculada_da_task(self):
        from inbox_pendentes import _resolved_by_diario
        task = {'diario_mais_recente': datetime(2026, 9, 1, 11, tzinfo=timezone.utc)}
        self.assertTrue(_resolved_by_diario(task, datetime(2026, 9, 1, 8, tzinfo=timezone.utc)))
        self.assertFalse(_resolved_by_diario(task, datetime(2026, 9, 1, 12, tzinfo=timezone.utc)))

    def test_resolved_by_diario_sem_task_ou_sem_data_da_mensagem_devolve_false(self):
        from inbox_pendentes import _resolved_by_diario
        self.assertFalse(_resolved_by_diario(None, datetime(2026, 9, 1, 8, tzinfo=timezone.utc)))
        self.assertFalse(_resolved_by_diario({'diario_mais_recente': datetime(2026, 9, 1, 11, tzinfo=timezone.utc)}, None))

    # -- DEV-2026-0004 sub-entrega 5/9, proposta (c)(ii): auto-resolução por
    # canal cruzado (André já respondeu ao MESMO contato pelo OUTRO canal). --

    def test_whatsapp_respondido_por_email_apos_mensagem_e_resolvido(self):
        """Cenário Wagner/Vetor do achado B6: pendência de WhatsApp, mas
        André já tratou por e-mail com o mesmo contato depois da mensagem."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {'p': {'nome': 'Wagner', 'whatsapp_chat_id': 'w', 'email': 'wagner@vetor.com.br'}},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'trecho': 'Já tratamos isso?',
                                       'desde': '2026-09-01T08:00:00+00:00'}},
            'email_action_suggestions': {
                'e': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'origem_sinal': 'Wagner <wagner@vetor.com.br>',
                      'ultima_mensagem_de_andre': True,
                      'internal_date': '2026-09-01T10:00:00+00:00'},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(result['itens'], [])
        self.assertEqual(result['filtrados']['tratado_em_outro_canal'], 1)

    def test_outgoing_email_por_contato_exige_acao_ativa(self):
        """DEV-2026-0004 sub-entrega 5/9: achado da SEGUNDA rodada de revisão
        adversarial -- a primeira versão de `_outgoing_email_by_contact` não
        exigia ação ATIVA vinculada, ao contrário de `_resolved_by_diario` e
        de `emails_by_thread`. Sem essa exigência, um e-mail respondido numa
        ação já CONCLUÍDA (ou sem ação nenhuma) contava como tratamento para
        uma pendência de WhatsApp completamente diferente do mesmo contato.
        Aqui a ação 't' está CONCLUÍDA -- a pendência de WhatsApp tem que
        continuar de pé."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {'p': {'nome': 'Wagner', 'whatsapp_chat_id': 'w', 'email': 'wagner@vetor.com.br'}},
            'tarefas': {'t': {'titulo': 'Ação antiga', 'status': 'concluída'}},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'trecho': 'Já tratamos isso?',
                                       'desde': '2026-09-01T08:00:00+00:00'}},
            'email_action_suggestions': {
                'e': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'origem_sinal': 'Wagner <wagner@vetor.com.br>',
                      'ultima_mensagem_de_andre': True,
                      'internal_date': '2026-09-01T10:00:00+00:00'},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result['itens']), 1)
        self.assertEqual(result['filtrados']['tratado_em_outro_canal'], 0)

    def test_email_respondido_por_whatsapp_apos_mensagem_e_resolvido(self):
        """Mesmo cenário, invertido: pendência de e-mail já tratada por
        WhatsApp com o mesmo contato depois da mensagem."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {'p': {'nome': 'Wagner', 'whatsapp_chat_id': 'w', 'email': 'wagner@vetor.com.br'}},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'ultima_de_andre': True,
                                       'desde': '2026-09-01T10:00:00+00:00'}},
            'email_action_suggestions': {
                'e': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'sender': 'Wagner <wagner@vetor.com.br>',
                      'snippet': 'Confirma pra mim?',
                      'internal_date': '2026-09-01T08:00:00+00:00'},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(result['itens'], [])
        self.assertEqual(result['filtrados']['tratado_em_outro_canal'], 1)

    def test_cross_channel_resposta_anterior_a_mensagem_nao_resolve(self):
        """Uma resposta no OUTRO canal ANTES da mensagem pendente não conta
        -- só uma resposta posterior é evidência de tratamento."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {'p': {'nome': 'Wagner', 'whatsapp_chat_id': 'w', 'email': 'wagner@vetor.com.br'}},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'trecho': 'Novidade, precisa de retorno',
                                       'desde': '2026-09-01T10:00:00+00:00'}},
            'email_action_suggestions': {
                'e': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'origem_sinal': 'Wagner <wagner@vetor.com.br>',
                      'ultima_mensagem_de_andre': True,
                      'internal_date': '2026-09-01T08:00:00+00:00'},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result['itens']), 1)
        self.assertEqual(result['filtrados']['tratado_em_outro_canal'], 0)

    def test_cross_channel_no_mesmo_instante_nao_resolve(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {'p': {'nome': 'Wagner', 'whatsapp_chat_id': 'w', 'email': 'wagner@vetor.com.br'}},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'trecho': 'Mensagem',
                                       'desde': '2026-09-01T08:00:00+00:00'}},
            'email_action_suggestions': {
                'e': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'origem_sinal': 'Wagner <wagner@vetor.com.br>',
                      'ultima_mensagem_de_andre': True,
                      'internal_date': '2026-09-01T08:00:00+00:00'},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result['itens']), 1)

    def test_cross_channel_sem_vinculo_de_perfil_nao_resolve(self):
        """`perfil_pessoas` só tem `whatsapp_chat_id`, sem `email` -- sem a
        dupla confirmação, não há como ligar o e-mail que respondeu a esse
        chat; a pendência de WhatsApp continua de pé mesmo que exista um
        e-mail 'respondido' coincidentemente com o mesmo nome."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {'p': {'nome': 'Wagner', 'whatsapp_chat_id': 'w'}},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'trecho': 'Já tratamos isso?',
                                       'desde': '2026-09-01T08:00:00+00:00'}},
            'email_action_suggestions': {
                'e': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'origem_sinal': 'Wagner <wagner@vetor.com.br>',
                      'ultima_mensagem_de_andre': True,
                      'internal_date': '2026-09-01T10:00:00+00:00'},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result['itens']), 1)
        self.assertEqual(result['filtrados']['tratado_em_outro_canal'], 0)

    def test_auditoria_inclui_item_tratado_em_outro_canal(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {'p': {'nome': 'Wagner', 'whatsapp_chat_id': 'w', 'email': 'wagner@vetor.com.br'}},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'trecho': 'Já tratamos isso?',
                                       'desde': '2026-09-01T08:00:00+00:00'}},
            'email_action_suggestions': {
                'e': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'origem_sinal': 'Wagner <wagner@vetor.com.br>',
                      'ultima_mensagem_de_andre': True,
                      'internal_date': '2026-09-01T10:00:00+00:00'},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc), incluir_filtrados=True)
        self.assertEqual(len(result['itens']), 1)

    def test_contacts_liga_email_e_chat_id_so_quando_ambos_presentes(self):
        from inbox_pendentes import _contacts
        db = Db({'perfil_pessoas': {
            'p1': {'nome': 'Wagner', 'whatsapp_chat_id': 'w1', 'email': 'Wagner@Vetor.com.br'},
            'p2': {'nome': 'SóChat', 'whatsapp_chat_id': 'w2'},
            'p3': {'nome': 'SóEmail', 'email': 'so-email@example.com'},
        }})
        nomes, email_por_chat, chat_por_email = _contacts(db)
        self.assertEqual(nomes, {'w1': 'Wagner', 'w2': 'SóChat'})
        self.assertEqual(email_por_chat, {'w1': 'wagner@vetor.com.br'})
        self.assertEqual(chat_por_email, {'wagner@vetor.com.br': 'w1'})

    def test_outgoing_email_by_contact_ignora_thread_sem_ultima_de_andre(self):
        from inbox_pendentes import _outgoing_email_by_contact
        db = Db({'email_action_suggestions': {
            'a': {'canal': 'email', 'status': 'applied', 'task_id': 't', 'origem_sinal': 'x <x@ex.com>',
                  'internal_date': '2026-09-01T08:00:00+00:00'},
            'b': {'canal': 'email', 'status': 'applied', 'task_id': 't', 'origem_sinal': 'y <y@ex.com>',
                  'ultima_mensagem_de_andre': True, 'internal_date': '2026-09-01T09:00:00+00:00'},
        }})
        by_id = {'t': {'id': 't', 'titulo': 'Ação'}}
        self.assertEqual(_outgoing_email_by_contact(db, {}, by_id), {'y@ex.com': datetime(2026, 9, 1, 9, tzinfo=timezone.utc)})

    def test_outgoing_email_by_contact_escolhe_a_mais_recente_entre_varias_threads(self):
        from inbox_pendentes import _outgoing_email_by_contact
        db = Db({'email_action_suggestions': {
            'a': {'canal': 'email', 'status': 'applied', 'task_id': 't', 'origem_sinal': 'x <x@ex.com>',
                  'ultima_mensagem_de_andre': True, 'internal_date': '2026-09-01T08:00:00+00:00'},
            'b': {'canal': 'email', 'status': 'applied_reactivated', 'task_id': 't', 'origem_sinal': 'X <x@ex.com>',
                  'ultima_mensagem_de_andre': True, 'internal_date': '2026-09-01T11:00:00+00:00'},
        }})
        by_id = {'t': {'id': 't', 'titulo': 'Ação'}}
        self.assertEqual(_outgoing_email_by_contact(db, {}, by_id), {'x@ex.com': datetime(2026, 9, 1, 11, tzinfo=timezone.utc)})

    def test_outgoing_email_by_contact_sem_acao_resolvida_e_ignorado(self):
        """DEV-2026-0004 sub-entrega 5/9: achado da segunda rodada de revisão
        adversarial -- sem `task_id` resolvido em `by_email`/`by_id` (ação
        inexistente, concluída, ou vínculo nunca aplicado a uma ação ativa),
        a thread não conta como evidência de tratamento."""
        from inbox_pendentes import _outgoing_email_by_contact
        db = Db({'email_action_suggestions': {
            'a': {'canal': 'email', 'status': 'applied', 'task_id': 'inexistente', 'origem_sinal': 'x <x@ex.com>',
                  'ultima_mensagem_de_andre': True, 'internal_date': '2026-09-01T09:00:00+00:00'},
        }})
        self.assertEqual(_outgoing_email_by_contact(db, {}, {}), {})

    def test_resolved_cross_channel_compara_estrito_e_ignora_sem_vinculo(self):
        from inbox_pendentes import _resolved_cross_channel
        outgoing = {'x@ex.com': datetime(2026, 9, 1, 10, tzinfo=timezone.utc)}
        self.assertTrue(_resolved_cross_channel(
            contact_key='x@ex.com', message_when=datetime(2026, 9, 1, 8, tzinfo=timezone.utc), outgoing_by_contact=outgoing))
        self.assertFalse(_resolved_cross_channel(
            contact_key='x@ex.com', message_when=datetime(2026, 9, 1, 10, tzinfo=timezone.utc), outgoing_by_contact=outgoing))
        self.assertFalse(_resolved_cross_channel(contact_key=None, message_when=datetime(2026, 9, 1, 8, tzinfo=timezone.utc), outgoing_by_contact=outgoing))
        self.assertFalse(_resolved_cross_channel(contact_key='x@ex.com', message_when=None, outgoing_by_contact=outgoing))
        self.assertFalse(_resolved_cross_channel(contact_key='ausente@ex.com', message_when=datetime(2026, 9, 1, 8, tzinfo=timezone.utc), outgoing_by_contact=outgoing))

    def test_cross_channel_e_diario_sao_independentes_qualquer_um_resolve(self):
        """Regressão de composição: o item pode ser resolvido por diário OU
        por canal cruzado -- os dois caminhos não se atrapalham, e o
        primeiro que casar já é suficiente (aqui, só o canal cruzado se
        aplica; a ação nem tem diário genuíno)."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {'p': {'nome': 'Wagner', 'whatsapp_chat_id': 'w', 'email': 'wagner@vetor.com.br'}},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento', 'whatsapp_vinculos': [{'chat_id': 'w'}]}},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'trecho': 'Já tratamos isso?',
                                       'desde': '2026-09-01T08:00:00+00:00'}},
            'email_action_suggestions': {
                'e': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'origem_sinal': 'Wagner <wagner@vetor.com.br>',
                      'ultima_mensagem_de_andre': True,
                      'internal_date': '2026-09-01T10:00:00+00:00'},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(result['itens'], [])
        self.assertEqual(result['filtrados']['tratado_na_acao'], 0)
        self.assertEqual(result['filtrados']['tratado_em_outro_canal'], 1)


class _MemorySnap:
    def __init__(self, ref): self.ref, self.exists = ref, ref.data is not None
    def to_dict(self): return dict(self.ref.data or {})


class _MemoryRef:
    def __init__(self, ident, data=None): self.id, self.data, self.set_calls = ident, data, []
    def get(self): return _MemorySnap(self)
    def set(self, data, merge=False): self.set_calls.append((data, merge)); self.data = {**(self.data or {}), **data} if merge else data


class _MemoryCollection:
    def __init__(self): self.refs = {}
    def document(self, ident): return self.refs.setdefault(ident, _MemoryRef(ident))


class _Batch:
    def __init__(self): self.ops = []; self.committed = False
    def set(self, ref, data, merge=False): self.ops.append((ref, data, merge))
    def commit(self):
        self.committed = True
        for ref, data, merge in self.ops: ref.set(data, merge=merge)


class _MemoryDb:
    def __init__(self): self.inbox, self.batches = _MemoryCollection(), []
    def collection(self, name):
        assert name == 'inbox_pendentes'
        return self.inbox
    def batch(self):
        batch = _Batch(); self.batches.append(batch); return batch


class InboxBatchTest(unittest.TestCase):
    def test_lote_colapsa_por_chat_e_grava_em_batch(self):
        db = _MemoryDb()
        count = atualizar_whatsapp_em_lote(db, [
            {'chat_id': 'a', 'timestamp': '2026-09-01T08:00:00+00:00', 'content': 'antiga'},
            {'chat_id': 'a', 'timestamp': '2026-09-01T10:00:00+00:00', 'content': 'nova'},
            {'chat_id': 'b', 'timestamp': '2026-09-01T09:00:00+00:00', 'content': 'outra'},
        ])
        self.assertEqual(count, 2)
        self.assertEqual(len(db.batches), 1)
        self.assertEqual(len(db.batches[0].ops), 2)
        self.assertEqual(db.inbox.document('wa_YQ').data['trecho'], 'nova')


class _Chain:
    def __init__(self, docs): self.docs = docs
    def order_by(self, *args, **kwargs): return self
    def start_after(self, *args, **kwargs): return self
    def where(self, *args, **kwargs): return self
    def limit(self, *args, **kwargs): return self
    def stream(self): return list(self.docs)


class _BackfillDb:
    def __init__(self):
        self.marker = _MemoryRef('inbox_pendentes_backfill')
        self.chats = _Chain([Doc('chat-a', {'chat_id': 'a'})])
        self.messages = _Chain([Doc('m1', {'chat_id': 'a', 'timestamp': '2026-09-01T10:00:00+00:00'})])
    def collection(self, name):
        if name == 'system': return type('System', (), {'document': lambda _, ident: self.marker})()
        if name == 'whatsapp_chats': return self.chats
        if name == 'whatsapp_messages': return self.messages
        raise AssertionError(name)


class InboxBackfillTest(unittest.TestCase):
    def test_backfill_usa_ultima_mensagem_de_cada_chat_e_marca_progresso(self):
        from unittest import mock
        db = _BackfillDb()
        with mock.patch('inbox_pendentes.atualizar_whatsapp_em_lote') as update:
            self.assertTrue(backfill_whatsapp_inicial(db))
        self.assertEqual(update.call_args.args[1], [{'chat_id': 'a', 'timestamp': '2026-09-01T10:00:00+00:00'}])
        self.assertTrue(db.marker.data['completed_at'])


class _FakeGeminiResponse:
    def __init__(self, text):
        self.text = text


class _FakeGeminiModels:
    def __init__(self, response_text=None, error=None):
        self._response_text = response_text
        self._error = error
        self.calls = []

    def generate_content(self, *, model, contents, **kwargs):
        self.calls.append({'model': model, 'contents': contents})
        if self._error:
            raise self._error
        return _FakeGeminiResponse(self._response_text)


class _FakeGeminiClient:
    """DEV-2026-0004 sub-entrega 7/9: dublê mínimo do client `google.genai`
    real -- só precisa de `.models.generate_content(model=, contents=, **kw)`,
    que é tudo que `generate_content_logged` (gemini_cost_controls.py) chama.
    Os demais efeitos de `generate_content_logged` (log de uso, agregação em
    Firestore) já são auto-contidos em try/except lá dentro e não precisam de
    dublê -- ver `log_gemini_usage`."""
    def __init__(self, response_text=None, error=None):
        self.models = _FakeGeminiModels(response_text=response_text, error=error)


def _boom(*_args, **_kwargs):
    raise AssertionError("get_client não deveria ser chamado aqui")


class ClassificadorLLMTest(unittest.TestCase):
    """DEV-2026-0004 sub-entrega 7/9, proposta (b)(ii): testes diretos de
    `_classificar_necessidade_resposta` -- cache (chave via
    `_chave_cache_classificacao`, que inclui um fingerprint do texto -- ver
    seu docstring para o achado CRÍTICO da revisão adversarial que motivou
    isso), chamada ao Gemini Flash Lite, orçamento por passada, e acima de
    tudo que toda falha (sem client, JSON malformado, rótulo desconhecido,
    erro de rede, orçamento esgotado) devolve None, NUNCA um rótulo que
    filtraria a mensagem. Ver a integração com `coletar()` em
    `ColetarClassificadorLLMTest` abaixo."""

    def test_usa_cache_quando_ja_classificado_nunca_chama_get_client(self):
        chave = _chave_cache_classificacao('msg-1', 'Obrigada!', False)
        db = Db({LLM_CLASSIFICACAO_COLLECTION: {chave: {'rotulo': 'encerramento', 'justificativa': 'x'}}})
        rotulo = _classificar_necessidade_resposta(db, _boom, message_id='msg-1', texto='Obrigada!', is_email=False)
        self.assertEqual(rotulo, 'encerramento')

    def test_sem_message_id_nao_classifica_e_nao_chama_get_client(self):
        db = Db({})
        rotulo = _classificar_necessidade_resposta(db, _boom, message_id='', texto='Oi, tudo bem?', is_email=False)
        self.assertIsNone(rotulo)

    def test_sem_texto_nao_classifica_e_nao_chama_get_client(self):
        db = Db({})
        rotulo = _classificar_necessidade_resposta(db, _boom, message_id='m1', texto='   ', is_email=False)
        self.assertIsNone(rotulo)

    def test_classifica_via_llm_e_grava_cache_quando_sem_cache(self):
        db = Db({})
        client = _FakeGeminiClient(response_text='{"rotulo": "pedido", "justificativa": "pede confirmacao"}')
        rotulo = _classificar_necessidade_resposta(
            db, lambda: client, message_id='msg-2', texto='Pode confirmar o horário?', is_email=False)
        self.assertEqual(rotulo, 'pedido')
        self.assertEqual(len(client.models.calls), 1)
        chave = _chave_cache_classificacao('msg-2', 'Pode confirmar o horário?', False)
        cached = db.collection(LLM_CLASSIFICACAO_COLLECTION).document(chave)
        self.assertTrue(cached.exists)
        self.assertEqual(cached.data['rotulo'], 'pedido')

    def test_segunda_chamada_usa_cache_gravado_pela_primeira_e_nao_chama_llm_de_novo(self):
        db = Db({})
        client = _FakeGeminiClient(response_text='{"rotulo": "encerramento", "justificativa": "agradecimento"}')
        r1 = _classificar_necessidade_resposta(db, lambda: client, message_id='msg-3', texto='Obrigada!', is_email=False)
        r2 = _classificar_necessidade_resposta(db, _boom, message_id='msg-3', texto='Obrigada!', is_email=False)
        self.assertEqual(r1, 'encerramento')
        self.assertEqual(r2, 'encerramento')
        self.assertEqual(len(client.models.calls), 1)

    def test_mesmo_message_id_com_texto_diferente_nao_reaproveita_cache(self):
        """Achado CRÍTICO da revisão adversarial: `email_action_suggestions`
        reescreve `snippet` no MESMO doc (mesmo `doc.id`/`message_id`) a cada
        refresh de `email_action_linker.atualizar_direcao_emails_aplicados`,
        para refletir a mensagem mais recente da thread. Se o cache fosse
        chaveado só por `message_id`, uma classificação antiga
        ("encerramento") vazaria para um texto novo e completamente
        diferente que chegou depois na mesma thread -- ver
        `_chave_cache_classificacao`. Este teste prova que isso NÃO
        acontece: texto novo, mesmo message_id, classificador é chamado de
        novo."""
        db = Db({})
        client1 = _FakeGeminiClient(response_text='{"rotulo": "encerramento", "justificativa": "agradecimento"}')
        r1 = _classificar_necessidade_resposta(db, lambda: client1, message_id='msg-thread',
                                                texto='Obrigada, ficamos assim então', is_email=True)
        self.assertEqual(r1, 'encerramento')
        client2 = _FakeGeminiClient(response_text='{"rotulo": "pergunta", "justificativa": "pergunta nova"}')
        r2 = _classificar_necessidade_resposta(db, lambda: client2, message_id='msg-thread',
                                                texto='Na verdade, você pode confirmar o valor final?', is_email=True)
        self.assertEqual(r2, 'pergunta')
        self.assertEqual(len(client2.models.calls), 1)

    def test_falha_aberta_sem_client_disponivel(self):
        db = Db({})
        rotulo = _classificar_necessidade_resposta(db, lambda: None, message_id='msg-4', texto='Pode ligar?', is_email=False)
        self.assertIsNone(rotulo)

    def test_falha_aberta_resposta_json_malformada(self):
        db = Db({})
        client = _FakeGeminiClient(response_text='isso não é json')
        rotulo = _classificar_necessidade_resposta(db, lambda: client, message_id='msg-5', texto='Oi', is_email=False)
        self.assertIsNone(rotulo)

    def test_falha_aberta_rotulo_desconhecido_e_nao_fica_em_cache(self):
        db = Db({})
        client = _FakeGeminiClient(response_text='{"rotulo": "spam", "justificativa": "x"}')
        rotulo = _classificar_necessidade_resposta(db, lambda: client, message_id='msg-6', texto='Oi', is_email=False)
        self.assertIsNone(rotulo)
        # Um rótulo inválido não pode ficar cacheado -- prenderia a mensagem
        # PARA SEMPRE num resultado inútil em vez de tentar de novo na
        # próxima passada.
        chave = _chave_cache_classificacao('msg-6', 'Oi', False)
        self.assertFalse(db.collection(LLM_CLASSIFICACAO_COLLECTION).document(chave).exists)

    def test_falha_aberta_erro_de_rede(self):
        db = Db({})
        client = _FakeGeminiClient(error=RuntimeError("timeout"))
        rotulo = _classificar_necessidade_resposta(db, lambda: client, message_id='msg-7', texto='Oi', is_email=False)
        self.assertIsNone(rotulo)

    def test_aceita_resposta_com_cerca_de_markdown_json(self):
        db = Db({})
        client = _FakeGeminiClient(response_text='```json\n{"rotulo": "pergunta", "justificativa": "pergunta direta"}\n```')
        rotulo = _classificar_necessidade_resposta(db, lambda: client, message_id='msg-8', texto='Você vai?', is_email=False)
        self.assertEqual(rotulo, 'pergunta')

    def test_falha_aberta_orcamento_esgotado_nao_chama_get_client(self):
        db = Db({})
        rotulo = _classificar_necessidade_resposta(
            db, _boom, message_id='msg-9', texto='Oi', is_email=False, pode_classificar=lambda: False)
        self.assertIsNone(rotulo)

    def test_orcamento_nao_e_consultado_em_cache_hit(self):
        chave = _chave_cache_classificacao('msg-10', 'Obrigada!', False)
        db = Db({LLM_CLASSIFICACAO_COLLECTION: {chave: {'rotulo': 'encerramento', 'justificativa': 'x'}}})
        def _orcamento_nao_deveria_ser_chamado():
            raise AssertionError("cache-hit não deveria consultar orçamento")
        rotulo = _classificar_necessidade_resposta(
            db, _boom, message_id='msg-10', texto='Obrigada!', is_email=False,
            pode_classificar=_orcamento_nao_deveria_ser_chamado)
        self.assertEqual(rotulo, 'encerramento')


class ColetarClassificadorLLMTest(unittest.TestCase):
    """DEV-2026-0004 sub-entrega 7/9: integração do classificador dentro de
    `coletar()` -- só o rótulo do LLM muda o resultado aqui (a heurística
    sozinha deixaria as mensagens abaixo passarem, exatamente o cenário que
    a proposta (b)(ii) pede: um segundo estágio mais forte que a
    heurística)."""

    def test_coletar_filtra_whatsapp_informativo_detectado_so_pelo_llm(self):
        from unittest import mock
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'message_id': 'wa-1',
                'trecho': 'Segue o comprovante do pagamento de hoje', 'desde': '2026-09-01T08:00:00+00:00'}},
        })
        client = _FakeGeminiClient(response_text='{"rotulo": "informativo", "justificativa": "so avisa"}')
        with mock.patch('inbox_pendentes._get_llm_client', return_value=client):
            result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(result['itens'], [])
        # Contador PRÓPRIO do classificador LLM (não o mesmo que a heurística
        # usa) -- achado da revisão adversarial, ver `_LLM_ROTULO_PARA_FILTRO`.
        self.assertEqual(result['filtrados']['informativo_llm'], 1)
        self.assertEqual(result['filtrados']['informativo'], 0)

    def test_coletar_preserva_whatsapp_rotulado_pedido_pelo_llm(self):
        from unittest import mock
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'message_id': 'wa-2',
                'trecho': 'Preciso que você decida isso ainda hoje', 'desde': '2026-09-01T08:00:00+00:00'}},
        })
        client = _FakeGeminiClient(response_text='{"rotulo": "pedido", "justificativa": "pede decisao"}')
        with mock.patch('inbox_pendentes._get_llm_client', return_value=client):
            result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result['itens']), 1)
        self.assertEqual(result['filtrados']['informativo_llm'], 0)
        self.assertEqual(result['filtrados']['encerramentos_llm'], 0)
        # Prova que o item sobreviveu PORQUE o classificador rodou e devolveu
        # "pedido" -- não porque ele nunca chegou a ser chamado.
        self.assertEqual(len(client.models.calls), 1)

    def test_coletar_filtra_email_encerramento_detectado_so_pelo_llm(self):
        from unittest import mock
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': []}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {},
            'email_action_suggestions': {
                'msg-em-1': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'sender': 'Gabriela <gabriela@ifes.edu.br>',
                      'snippet': 'Ficamos combinados então, agradeço a atenção de sempre',
                      'internal_date': '2026-09-01T08:00:00+00:00', 'andre_em_to': True},
            },
        })
        client = _FakeGeminiClient(response_text='{"rotulo": "encerramento", "justificativa": "fecha a conversa"}')
        with mock.patch('inbox_pendentes._get_llm_client', return_value=client):
            result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(result['itens'], [])
        self.assertEqual(result['filtrados']['encerramentos_llm'], 1)
        self.assertEqual(result['filtrados']['encerramentos'], 0)
        # Cache gravado com uma chave derivada do `doc.id` de
        # `email_action_suggestions` (o próprio google_message_id) MAIS
        # `internal_date` MAIS um fingerprint do texto -- não o `doc.id`
        # puro, nem `doc.id`+snippet sozinhos (achado da revisão adversarial:
        # dois e-mails diferentes na mesma thread podem ter snippet
        # coincidente -- ver o teste
        # `test_coletar_resposta_nova_com_snippet_coincidente_na_mesma_thread_e_reclassificada`
        # logo abaixo, que prova por que `internal_date` também entra).
        snippet = 'Ficamos combinados então, agradeço a atenção de sempre'
        chave = _chave_cache_classificacao('msg-em-1|2026-09-01T08:00:00+00:00', snippet, True)
        cached = db.collection(LLM_CLASSIFICACAO_COLLECTION).document(chave)
        self.assertTrue(cached.exists)

    def test_coletar_preserva_email_rotulado_pergunta_pelo_llm(self):
        from unittest import mock
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': []}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {},
            'email_action_suggestions': {
                'msg-em-2': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'sender': 'Gabriela <gabriela@ifes.edu.br>',
                      'snippet': 'Você pode revisar o anexo antes de sexta?',
                      'internal_date': '2026-09-01T08:00:00+00:00', 'andre_em_to': True},
            },
        })
        client = _FakeGeminiClient(response_text='{"rotulo": "pergunta", "justificativa": "pergunta direta"}')
        with mock.patch('inbox_pendentes._get_llm_client', return_value=client):
            result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result['itens']), 1)
        self.assertEqual(len(client.models.calls), 1)

    def test_coletar_resposta_nova_na_mesma_thread_de_email_nao_herda_classificacao_antiga(self):
        """Integração ponta a ponta do achado CRÍTICO da revisão adversarial
        (ver `_chave_cache_classificacao`): o MESMO doc de
        `email_action_suggestions` (mesmo `doc.id`) tem seu `snippet`
        reescrito entre duas passadas de `coletar()`, simulando
        `email_action_linker.atualizar_direcao_emails_aplicados` trazendo a
        mensagem mais recente da thread. A resposta nova (uma pergunta de
        verdade) NÃO pode ser escondida pela classificação cacheada da
        mensagem antiga (um encerramento)."""
        from unittest import mock
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': []}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {},
            'email_action_suggestions': {
                'msg-thread-1': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'sender': 'Gabriela <gabriela@ifes.edu.br>',
                      'snippet': 'Perfeito, muito obrigada pela ajuda',
                      'internal_date': '2026-09-01T08:00:00+00:00', 'andre_em_to': True},
            },
        })
        client1 = _FakeGeminiClient(response_text='{"rotulo": "encerramento", "justificativa": "agradecimento"}')
        with mock.patch('inbox_pendentes._get_llm_client', return_value=client1):
            result1 = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(result1['itens'], [])

        # Simula o refresh de `atualizar_direcao_emails_aplicados`: MESMO
        # doc.id, texto novo e completamente diferente (uma pergunta real).
        db.collection('email_action_suggestions').document('msg-thread-1').set(
            {'snippet': 'Na verdade, pode confirmar o valor final da nota fiscal?',
             'internal_date': '2026-09-03T08:00:00+00:00'}, merge=True)

        client2 = _FakeGeminiClient(response_text='{"rotulo": "pergunta", "justificativa": "pergunta direta"}')
        with mock.patch('inbox_pendentes._get_llm_client', return_value=client2):
            result2 = coletar(db, datetime(2026, 9, 3, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result2['itens']), 1)
        self.assertEqual(len(client2.models.calls), 1)

    def test_coletar_resposta_nova_com_snippet_coincidente_na_mesma_thread_e_reclassificada(self):
        """Achado da revisão adversarial (variante mais sutil do teste
        anterior): a chave de cache usava só `doc.id` + fingerprint do
        SNIPPET -- se o snippet da mensagem NOVA coincidisse, por acaso, com
        o da mensagem ANTIGA (plausível para avisos automáticos/
        institucionais formulaicos, onde o texto variável fica fora da
        janela do snippet do Gmail), a classificação antiga era reaplicada
        SEM NUNCA chamar o LLM de novo -- o teste anterior não cobria esse
        caso porque usa um snippet novo e diferente. Aqui o snippet é
        DELIBERADAMENTE igual entre as duas passadas; só `internal_date`
        muda (o único campo que `atualizar_direcao_emails_aplicados` sempre
        atualiza a cada refresh de verdade). A segunda passada tem que
        classificar de novo (chamar o LLM), não reaproveitar o cache da
        primeira."""
        from unittest import mock
        snippet = 'Prezado, segue notificação do processo em andamento.'
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': []}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {},
            'email_action_suggestions': {
                'msg-coincidencia': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'sender': 'SIG/Ifes <sig@ifes.edu.br>',
                      'snippet': snippet,
                      'internal_date': '2026-09-01T08:00:00+00:00', 'andre_em_to': True},
            },
        })
        client1 = _FakeGeminiClient(response_text='{"rotulo": "informativo", "justificativa": "so avisa"}')
        with mock.patch('inbox_pendentes._get_llm_client', return_value=client1):
            result1 = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(result1['itens'], [])
        self.assertEqual(len(client1.models.calls), 1)

        # Refresh de `atualizar_direcao_emails_aplicados`: MESMO doc.id,
        # snippet igual POR COINCIDÊNCIA (mensagem realmente diferente, mas o
        # snippet do Gmail bate) -- só `internal_date` muda.
        db.collection('email_action_suggestions').document('msg-coincidencia').set(
            {'internal_date': '2026-09-03T08:00:00+00:00'}, merge=True)

        client2 = _FakeGeminiClient(response_text='{"rotulo": "pedido", "justificativa": "pede providencia"}')
        with mock.patch('inbox_pendentes._get_llm_client', return_value=client2):
            result2 = coletar(db, datetime(2026, 9, 3, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result2['itens']), 1)
        self.assertEqual(len(client2.models.calls), 1)

    def test_coletar_usa_cache_e_nunca_constroi_client_quando_ja_classificado(self):
        from unittest import mock
        trecho = 'Segue combinado, entendido'
        chave = _chave_cache_classificacao('wa-3', trecho, False)
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'message_id': 'wa-3',
                'trecho': trecho, 'desde': '2026-09-01T08:00:00+00:00'}},
            LLM_CLASSIFICACAO_COLLECTION: {chave: {'rotulo': 'pergunta', 'justificativa': 'x'}},
        })
        with mock.patch('inbox_pendentes._get_llm_client', side_effect=_boom) as get_client:
            result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result['itens']), 1)
        get_client.assert_not_called()

    def test_coletar_constroi_client_uma_unica_vez_para_varias_mensagens_sem_cache(self):
        """Prova o ponto de `_get_llm_client_memo`/`_llm_client_box` em
        `coletar()`: mesmo com DUAS mensagens sem cache (uma de WhatsApp, uma
        de e-mail) numa única passada, o client só é construído uma vez."""
        from unittest import mock
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'message_id': 'wa-6',
                'trecho': 'Segue o comprovante de hoje', 'desde': '2026-09-01T08:00:00+00:00'}},
            'email_action_suggestions': {
                'msg-em-3': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                      'sender': 'Gabriela <gabriela@ifes.edu.br>',
                      'snippet': 'Segue o comunicado para conhecimento',
                      'internal_date': '2026-09-01T08:00:00+00:00', 'andre_em_to': True},
            },
        })
        client = _FakeGeminiClient(response_text='{"rotulo": "informativo", "justificativa": "so avisa"}')
        with mock.patch('inbox_pendentes._get_llm_client', return_value=client) as get_client:
            coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(get_client.call_count, 1)
        self.assertEqual(len(client.models.calls), 2)

    def test_coletar_respeita_orcamento_por_passada_e_nao_classifica_alem_dele(self):
        """Achado HIGH da revisão adversarial: `coletar()` é lido de forma
        SÍNCRONA na abertura de sessão MCP (`morning_summary.gerar()`
        documenta explicitamente "não faz RPC ao WhatsApp/Gmail durante a
        abertura de uma sessão MCP"). Sem limite, um cache frio com um
        backlog grande dispararia uma chamada Gemini por mensagem
        sobrevivente. Este teste semeia mais mensagens sem cache do que
        `_LLM_MAX_CLASSIFICACOES_POR_PASSADA` permite e prova que só esse
        tanto é classificado -- o resto passa sem classificar (falha aberta
        por orçamento, não escondido)."""
        from unittest import mock
        n = _LLM_MAX_CLASSIFICACOES_POR_PASSADA + 3
        inbox = {}
        for i in range(n):
            chat_id = f'w{i}'
            inbox[chat_id] = {'tipo': 'whatsapp', 'chat_id': chat_id, 'message_id': f'wa-orc-{i}',
                               'trecho': f'Segue o comprovante numero {i}', 'desde': '2026-09-01T08:00:00+00:00'}
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': list(inbox.keys())}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': inbox,
        })
        # Todas seriam "informativo" (filtradas) se o orçamento fosse infinito --
        # a diferença entre `n` e as chamadas reais prova o corte pelo orçamento.
        client = _FakeGeminiClient(response_text='{"rotulo": "informativo", "justificativa": "so avisa"}')
        with mock.patch('inbox_pendentes._get_llm_client', return_value=client):
            result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc), incluir_filtrados=False, limite=100)
        self.assertEqual(len(client.models.calls), _LLM_MAX_CLASSIFICACOES_POR_PASSADA)
        # As mensagens além do orçamento não foram classificadas -- falha
        # aberta: continuam visíveis em vez de desaparecerem.
        self.assertEqual(len(result['itens']), n - _LLM_MAX_CLASSIFICACOES_POR_PASSADA)
        self.assertEqual(result['filtrados']['informativo_llm'], _LLM_MAX_CLASSIFICACOES_POR_PASSADA)

    def test_coletar_orcamento_compartilhado_entre_whatsapp_e_email(self):
        """Achado da SEGUNDA rodada de revisão adversarial: o orçamento é UM
        pool só, compartilhado entre os dois laços de `coletar()` (WhatsApp e
        e-mail) -- não um orçamento por laço. Semeia candidatos sem cache dos
        dois canais somando mais que o orçamento e prova que o total de
        chamadas ao LLM (soma dos dois laços) respeita o mesmo limite único."""
        from unittest import mock
        n_wa = _LLM_MAX_CLASSIFICACOES_POR_PASSADA - 2
        inbox = {}
        for i in range(n_wa):
            chat_id = f'w{i}'
            inbox[chat_id] = {'tipo': 'whatsapp', 'chat_id': chat_id, 'message_id': f'wa-mix-{i}',
                               'trecho': f'Segue o comprovante numero {i}', 'desde': '2026-09-01T08:00:00+00:00'}
        n_email = 5
        emails = {}
        for i in range(n_email):
            emails[f'msg-mix-{i}'] = {'canal': 'email', 'status': 'applied', 'task_id': 't',
                'sender': 'Gabriela <gabriela@ifes.edu.br>', 'snippet': f'Segue o comunicado numero {i}',
                'internal_date': '2026-09-01T08:00:00+00:00', 'andre_em_to': True}
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': list(inbox.keys())}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': inbox,
            'email_action_suggestions': emails,
        })
        client = _FakeGeminiClient(response_text='{"rotulo": "informativo", "justificativa": "so avisa"}')
        with mock.patch('inbox_pendentes._get_llm_client', return_value=client):
            coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc), limite=100)
        # n_wa (3, se o orçamento default for 5) + n_email (5) = 8 candidatos
        # sem cache, mas só `_LLM_MAX_CLASSIFICACOES_POR_PASSADA` chamadas no
        # TOTAL -- não esse limite em CADA laço (o que daria até 2x mais).
        self.assertEqual(len(client.models.calls), _LLM_MAX_CLASSIFICACOES_POR_PASSADA)

    def test_coletar_modo_auditoria_pula_o_classificador_llm(self):
        """`incluir_filtrados=True` existe para inspecionar o que os filtros
        ESTÃO fazendo (auditoria), não para gastar chamadas de LLM extras
        sem afetar o resultado -- ver comentário em `coletar()`."""
        from unittest import mock
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'message_id': 'wa-4',
                'trecho': 'Segue o comprovante do pagamento de hoje', 'desde': '2026-09-01T08:00:00+00:00'}},
        })
        with mock.patch('inbox_pendentes._get_llm_client', side_effect=_boom) as get_client:
            result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc), incluir_filtrados=True)
        self.assertEqual(len(result['itens']), 1)
        get_client.assert_not_called()

    def test_coletar_llm_indisponivel_nao_filtra_mensagem_real(self):
        """Falha aberta ponta a ponta: sem client (chave não configurada,
        erro de import, etc.), a mensagem tem que continuar visível -- nunca
        some da fila por causa de uma falha do classificador."""
        from unittest import mock
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'message_id': 'wa-5',
                'trecho': 'Segue o comprovante do pagamento de hoje', 'desde': '2026-09-01T08:00:00+00:00'}},
        })
        with mock.patch('inbox_pendentes._get_llm_client', return_value=None):
            result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result['itens']), 1)


class DispensarTest(unittest.TestCase):
    """DEV-2026-0004 sub-entrega 8/9, proposta (d): testes diretos de
    `dispensar()` -- validação de entrada e a gravação em si. A integração
    com `coletar()` (o item de fato sumir da fila, e SÓ até o conteúdo
    mudar) está em `ColetarDispensaTest` abaixo."""

    def test_dispensa_grava_e_devolve_ok(self):
        db = Db({})
        item_id = _chave_item_dispensavel('w', 'Já tratamos isso?', False)
        resultado = dispensar(db, item_id=item_id, motivo='Já resolvi por telefone')
        self.assertEqual(resultado, {'status': 'ok', 'id': item_id, 'motivo': 'Já resolvi por telefone'})
        doc = db.collection(DISPENSA_COLLECTION).document(item_id)
        self.assertTrue(doc.exists)
        self.assertEqual(doc.data['motivo'], 'Já resolvi por telefone')
        self.assertEqual(doc.data['item_id'], item_id)

    def test_dispensa_sem_item_id_devolve_erro_e_nao_grava(self):
        db = Db({})
        resultado = dispensar(db, item_id='', motivo='Motivo qualquer')
        self.assertIn('erro', resultado)
        self.assertEqual(len(db.collection(DISPENSA_COLLECTION).docs_by_id), 0)

    def test_dispensa_com_item_id_mal_formado_devolve_erro(self):
        """`item_id` tem que vir de `coletar()` (formato
        `{canal}:{identificador}:{fingerprint}`, 2 dois-pontos) -- nunca
        montado à mão pelo chamador. Um valor sem essa forma (aqui, um nome
        de contato solto) é rejeitado em vez de aceito e gravado do jeito
        errado."""
        db = Db({})
        resultado = dispensar(db, item_id='Wagner', motivo='Já tratei')
        self.assertIn('erro', resultado)

    def test_dispensa_sem_motivo_devolve_erro_e_nao_grava(self):
        db = Db({})
        item_id = _chave_item_dispensavel('w', 'Já tratamos isso?', False)
        resultado = dispensar(db, item_id=item_id, motivo='   ')
        self.assertIn('erro', resultado)
        self.assertEqual(len(db.collection(DISPENSA_COLLECTION).docs_by_id), 0)


class ColetarDispensaTest(unittest.TestCase):
    """DEV-2026-0004 sub-entrega 8/9: integração da dispensa dentro de
    `coletar()` -- o item some da fila depois de dispensado, tanto para
    WhatsApp quanto para e-mail, mas SÓ enquanto o trecho/snippet que o
    originou não mudar (ver `_chave_item_dispensavel`: a dispensa é presa ao
    CONTEÚDO, não à conversa/thread inteira -- uma mensagem nova no mesmo
    chat/thread tem um `id` diferente e continua aparecendo normalmente)."""

    def test_coletar_expoe_id_previsivel_no_item_whatsapp(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {}, 'tarefas': {},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w',
                'trecho': 'Pode revisar isso hoje?', 'desde': '2026-09-01T08:00:00+00:00'}},
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        esperado = _chave_item_dispensavel('w', 'Pode revisar isso hoje?', False)
        self.assertEqual(result['itens'][0]['id'], esperado)

    def test_coletar_expoe_id_previsivel_no_item_email(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': []}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {},
            'email_action_suggestions': {
                'msg-1': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                          'gmail_thread_id': 'thread-xyz',
                          'sender': 'Gabriela <gabriela@ifes.edu.br>',
                          'snippet': 'Poderia revisar o anexo até sexta?',
                          'internal_date': '2026-09-01T08:00:00+00:00', 'andre_em_to': True},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        # DEV-2026-0004 sub-entrega 8/9, achado HIGH da segunda rodada de
        # revisão adversarial: o texto fingerprintado do lado e-mail inclui
        # `internal_date` além do snippet -- ver o comentário no call site em
        # `coletar()` (`item_id_email`) para o motivo (sem isso, dois
        # e-mails DIFERENTES na mesma thread com snippet coincidente
        # colidiriam, já que `email_action_suggestions` não guarda nenhum id
        # de mensagem que mude a cada refresh como o `message_id` do
        # WhatsApp).
        esperado = _chave_item_dispensavel(
            'thread-xyz', '2026-09-01T08:00:00+00:00|Poderia revisar o anexo até sexta?', True)
        self.assertEqual(result['itens'][0]['id'], esperado)

    def test_coletar_email_motivo_inclusao_e_vinculado_a_acao(self):
        """Achado da própria demanda (proposta d): `motivo_inclusao` de todo
        item de e-mail era fixo em 'conversa_direta', sem relação com a razão
        real. Todo item deste laço exige uma ação ATIVA vinculada -- ver
        `emails_by_thread` em `coletar()` -- 'vinculado_a_acao' descreve isso
        de fato."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': []}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {},
            'email_action_suggestions': {
                'msg-1': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                          'sender': 'Gabriela <gabriela@ifes.edu.br>',
                          'snippet': 'Poderia revisar o anexo até sexta?',
                          'internal_date': '2026-09-01T08:00:00+00:00', 'andre_em_to': True},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(result['itens'][0]['motivo_inclusao'], 'vinculado_a_acao')

    def test_coletar_omite_item_whatsapp_dispensado_e_conta_no_filtrados(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {}, 'tarefas': {},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w',
                'trecho': 'Já tratamos isso?', 'desde': '2026-09-01T08:00:00+00:00'}},
        })
        item_id = _chave_item_dispensavel('w', 'Já tratamos isso?', False)
        dispensar(db, item_id=item_id, motivo='Já resolvi por telefone')
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(result['itens'], [])
        self.assertEqual(result['filtrados']['dispensados'], 1)

    def test_coletar_omite_item_email_dispensado_e_conta_no_filtrados(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': []}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {},
            'email_action_suggestions': {
                'msg-1': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                          'gmail_thread_id': 'thread-xyz',
                          'sender': 'Wagner <wagner@vetor.com.br>',
                          'snippet': 'Já tratamos isso, Wagner?',
                          'internal_date': '2026-09-01T08:00:00+00:00', 'andre_em_to': True},
            },
        })
        # `item_id` lido do próprio `coletar()` (não montado à mão) -- mais
        # robusto a qualquer mudança futura na fórmula exata (ver achado HIGH
        # documentado em `test_coletar_expoe_id_previsivel_no_item_email`).
        item_id = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))['itens'][0]['id']
        dispensar(db, item_id=item_id, motivo='André confirmou que já tratou por telefone')
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(result['itens'], [])
        self.assertEqual(result['filtrados']['dispensados'], 1)

    def test_coletar_emails_diferentes_com_snippet_coincidente_na_mesma_thread_nao_colidem(self):
        """Achado HIGH da SEGUNDA rodada de revisão adversarial: sem
        `internal_date` no texto fingerprintado, dois e-mails DIFERENTES na
        MESMA thread cujo snippet do Gmail coincidisse (plausível para
        avisos automáticos/institucionais formulaicos -- mesma classe de
        risco do achado CRÍTICO do lado WhatsApp) teriam o MESMO `id`, já
        que `email_action_suggestions` não guarda nenhum id de mensagem que
        mude a cada refresh (ao contrário do `message_id` do WhatsApp). Este
        teste simula exatamente como `email_action_linker.
        atualizar_direcao_emails_aplicados` reescreve o MESMO doc a cada
        refresh -- mesmo `doc.id`/`gmail_thread_id`, `internal_date` novo --
        com um snippet que POR COINCIDÊNCIA é idêntico ao anterior, e prova
        que a dispensa do primeiro e-mail não esconde o segundo."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': []}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {},
            'email_action_suggestions': {
                'msg-1': {'canal': 'email', 'status': 'applied', 'task_id': 't',
                          'gmail_thread_id': 'thread-coincidencia',
                          'sender': 'SIG/Ifes <sig@ifes.edu.br>',
                          'snippet': 'Prezado, segue notificação do processo em andamento.',
                          'internal_date': '2026-09-01T08:00:00+00:00', 'andre_em_to': True},
            },
        })
        result1 = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        item_id_1 = result1['itens'][0]['id']
        dispensar(db, item_id=item_id_1, motivo='Já resolvi, e-mail informativo de rotina')
        self.assertEqual(coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))['itens'], [])

        # Refresh de `atualizar_direcao_emails_aplicados`: MESMO doc.id,
        # MESMA thread, snippet igual POR COINCIDÊNCIA (mensagem realmente
        # diferente, mas o snippet do Gmail bate) -- só `internal_date` muda,
        # exatamente como aconteceria de verdade.
        db.collection('email_action_suggestions').document('msg-1').set(
            {'internal_date': '2026-09-03T08:00:00+00:00'}, merge=True)

        result2 = coletar(db, datetime(2026, 9, 3, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result2['itens']), 1)
        self.assertNotEqual(result2['itens'][0]['id'], item_id_1)
        self.assertEqual(result2['filtrados']['dispensados'], 0)

    def test_coletar_mensagem_nova_no_mesmo_chat_apos_dispensa_nao_fica_escondida(self):
        """Regressão CRÍTICA (mesma classe do achado que motivou o fingerprint
        de texto na sub-entrega 7/9, agora do lado da dispensa): dispensar a
        mensagem de HOJE do Wagner não pode silenciar uma mensagem NOVA e
        diferente que chegue depois no MESMO chat -- isso seria o "achado A"
        desta demanda de novo (exclusão indevida por dado obsoleto), só que
        criado pelo próprio André sem querer."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {}, 'tarefas': {},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w',
                'trecho': 'Já tratamos isso?', 'desde': '2026-09-01T08:00:00+00:00'}},
        })
        item_id_antigo = _chave_item_dispensavel('w', 'Já tratamos isso?', False)
        dispensar(db, item_id=item_id_antigo, motivo='Já resolvi por telefone')
        self.assertEqual(coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))['itens'], [])

        # Mensagem NOVA e diferente chega no MESMO chat (mesmo doc, chat_id
        # 'w'), simulando o índice sendo atualizado por `atualizar_whatsapp`.
        db.collection('inbox_pendentes').document('w').set({
            'tipo': 'whatsapp', 'chat_id': 'w',
            'trecho': 'Na verdade, preciso que você decida isso hoje',
            'desde': '2026-09-02T08:00:00+00:00',
        }, merge=True)

        result = coletar(db, datetime(2026, 9, 2, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result['itens']), 1)
        self.assertEqual(result['itens'][0]['trecho'], 'Na verdade, preciso que você decida isso hoje')
        self.assertEqual(result['filtrados']['dispensados'], 0)

    def test_coletar_mensagens_diferentes_com_mesmo_prefixo_truncado_nao_colidem(self):
        """Achado CRÍTICO da revisão adversarial: `trecho` já chega em
        `coletar()` truncado a 120 caracteres (por `_whatsapp_payload`, fora
        deste módulo) -- duas mensagens DIFERENTES que só compartilham o
        mesmo prefixo de 120 caracteres (comum em pedidos institucionais
        formulaicos) tinham o MESMO fingerprint de texto e, combinado com
        `chat_id` sozinho como identificador, o MESMO `id` -- dispensar uma
        escondia a outra para sempre (o "achado A" desta demanda de novo).
        Corrigido usando `message_id` (por mensagem) como identificador
        preferencial em `coletar()` -- mesmo campo que o classificador LLM já
        usa (sub-entrega 7/9). Este teste prova que duas mensagens com o
        MESMO trecho truncado, mas `message_id` diferente, recebem `id`s
        diferentes e que dispensar a primeira NÃO esconde a segunda."""
        prefixo_120 = ("Bom dia Andre, peco encaminhamento do processo referente ao requerimento "
                       "protocolado na secretaria. " * 2)[:120]
        self.assertEqual(len(prefixo_120), 120)  # sanity: exatamente o limite de truncamento
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {}, 'tarefas': {},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'message_id': 'wa-msg-1',
                'trecho': prefixo_120, 'desde': '2026-09-01T08:00:00+00:00'}},
        })
        result1 = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        item_id_1 = result1['itens'][0]['id']
        dispensar(db, item_id=item_id_1, motivo='Já resolvi essa primeira')
        self.assertEqual(coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))['itens'], [])

        # Mensagem NOVA e DIFERENTE chega no MESMO chat, com o MESMO trecho
        # truncado a 120 chars (o texto completo era diferente, mas ambos
        # truncam igual) -- só o `message_id` muda, como aconteceria de
        # verdade (cada mensagem do WhatsApp tem o seu).
        db.collection('inbox_pendentes').document('w').set({
            'tipo': 'whatsapp', 'chat_id': 'w', 'message_id': 'wa-msg-2',
            'trecho': prefixo_120, 'desde': '2026-09-02T08:00:00+00:00',
        }, merge=True)
        result2 = coletar(db, datetime(2026, 9, 2, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result2['itens']), 1)
        self.assertNotEqual(result2['itens'][0]['id'], item_id_1)
        self.assertEqual(result2['filtrados']['dispensados'], 0)

    def test_coletar_dispensa_por_chat_id_ainda_funciona_para_dado_legado_sem_message_id(self):
        """Mensagens antigas, gravadas antes de `message_id` existir no
        payload (`_whatsapp_payload`, campo adicionado na sub-entrega 7/9),
        continuam suportando dispensa -- só com o fallback por `chat_id`
        (mesmo risco de colisão por truncamento aceito como resíduo de dado
        legado, ver docstring de `_chave_item_dispensavel`)."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {}, 'tarefas': {},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w',
                'trecho': 'Já tratamos isso?', 'desde': '2026-09-01T08:00:00+00:00'}},
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        item_id = result['itens'][0]['id']
        self.assertEqual(item_id, _chave_item_dispensavel('w', 'Já tratamos isso?', False))
        dispensar(db, item_id=item_id, motivo='Já resolvi por telefone')
        self.assertEqual(coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))['itens'], [])

    def test_coletar_modo_auditoria_inclui_item_dispensado_sem_contar(self):
        """Mesmo padrão dos outros filtros deste módulo: `incluir_filtrados=True`
        existe para inspecionar o que ESTÁ sendo filtrado -- o item dispensado
        continua no resultado, mas o contador não sobe (só sobe quando o item
        de fato é omitido)."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {}, 'tarefas': {},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w',
                'trecho': 'Já tratamos isso?', 'desde': '2026-09-01T08:00:00+00:00'}},
        })
        item_id = _chave_item_dispensavel('w', 'Já tratamos isso?', False)
        dispensar(db, item_id=item_id, motivo='Já resolvi por telefone')
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc), incluir_filtrados=True)
        self.assertEqual(len(result['itens']), 1)
        self.assertEqual(result['filtrados']['dispensados'], 0)

    def test_coletar_rotulo_classificador_none_quando_nao_classificado(self):
        """Sem client de LLM disponível (chave ausente no ambiente de teste),
        `rotulo_classificador` tem que vir None -- nunca inventar um rótulo
        para um item que não foi de fato classificado."""
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {}, 'tarefas': {},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w',
                'trecho': 'Você pode confirmar o horário?', 'desde': '2026-09-01T08:00:00+00:00'}},
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result['itens']), 1)
        self.assertIsNone(result['itens'][0]['rotulo_classificador'])

    def test_coletar_rotulo_classificador_reflete_rotulo_do_llm(self):
        from unittest import mock
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['w']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {}, 'tarefas': {},
            'inbox_pendentes': {'w': {'tipo': 'whatsapp', 'chat_id': 'w', 'message_id': 'wa-9',
                'trecho': 'Preciso que você decida isso ainda hoje', 'desde': '2026-09-01T08:00:00+00:00'}},
        })
        client = _FakeGeminiClient(response_text='{"rotulo": "pedido", "justificativa": "pede decisao"}')
        with mock.patch('inbox_pendentes._get_llm_client', return_value=client):
            result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(result['itens'][0]['rotulo_classificador'], 'pedido')


if __name__ == '__main__':
    unittest.main()
