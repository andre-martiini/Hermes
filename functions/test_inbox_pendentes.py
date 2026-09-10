import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, '.')

from inbox_pendentes import atualizar_whatsapp_em_lote, backfill_whatsapp_inicial, coletar


class Doc:
    def __init__(self, doc_id, data):
        self.id, self.data, self.exists = doc_id, data, data is not None
    def to_dict(self): return dict(self.data or {})
    def get(self): return self


class Query:
    def __init__(self, docs): self.docs = docs
    def stream(self): return list(self.docs)
    def document(self, wanted):
        return next((d for d in self.docs if d.id == wanted), Doc(wanted, None))


class Db:
    def __init__(self, collections): self.collections = collections
    def collection(self, name):
        return Query([Doc(key, value) for key, value in self.collections.get(name, {}).items()])


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
        self.assertEqual(result['filtrados'], {'automaticos': 0, 'encerramentos': 1, 'sem_texto': 1, 'informativo': 0, 'tratado_na_acao': 0})
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


if __name__ == '__main__':
    unittest.main()
