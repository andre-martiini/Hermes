"""Testes de functions/autonomy/ledger.py (P04 sub-entrega 2/N -- passo 3
do pacote: "criar ledger de operações e checkpoints com limites de
tamanho", seção 4.5, itens 6, 9 e 10 do plano de autonomia)."""

import dataclasses
import unittest
from datetime import datetime, timedelta, timezone

from autonomy.ledger import (
    MAX_CHECKPOINT_BYTES,
    MAX_CHECKPOINTS_BYTES_TOTAL,
    MAX_CHECKPOINTS_POR_OPERACAO,
    Checkpoint,
    CheckpointMuitoGrande,
    ConflitoIdempotencia,
    LedgerEntry,
    ReentregaStatus,
    adicionar_checkpoint,
    consultar_reentrega,
    criar_entrada,
    criar_ou_reusar_entrada,
    hash_canonico,
    registrar_resultado,
)

UTC = timezone.utc
AGORA = datetime(2026, 9, 25, 12, 0, 0, tzinfo=UTC)


class TestHashCanonico(unittest.TestCase):
    def test_mesmo_conteudo_ordem_diferente_de_chaves_produz_mesmo_hash(self):
        self.assertEqual(
            hash_canonico({"a": 1, "b": 2}),
            hash_canonico({"b": 2, "a": 1}),
        )

    def test_conteudo_diferente_produz_hash_diferente(self):
        self.assertNotEqual(
            hash_canonico({"a": 1}),
            hash_canonico({"a": 2}),
        )

    def test_aninhamento_tambem_e_ordenado(self):
        self.assertEqual(
            hash_canonico({"x": {"a": 1, "b": 2}}),
            hash_canonico({"x": {"b": 2, "a": 1}}),
        )

    def test_e_deterministico_entre_chamadas(self):
        payload = {"idempotency_key": "abc", "args": [1, 2, 3]}
        self.assertEqual(hash_canonico(payload), hash_canonico(payload))

    def test_payload_nao_serializavel_levanta_typeerror(self):
        with self.assertRaises(TypeError):
            hash_canonico({"x": object()})

    def test_string_vazia_e_ausencia_de_chave_sao_diferentes(self):
        self.assertNotEqual(hash_canonico({"a": ""}), hash_canonico({}))

    def test_bool_e_int_produzem_hashes_diferentes(self):
        # json.dumps serializa True como "true" e 1 como "1" -- não deveriam
        # colidir apesar de bool ser subclasse de int em Python.
        self.assertNotEqual(hash_canonico({"a": True}), hash_canonico({"a": 1}))

    def test_dict_aninhado_com_chaves_de_tipos_mistos_nao_levanta_typeerror(self):
        # Antes do fix (1a rodada de revisão adversarial): sort_keys=True
        # tentava comparar chave int com chave str e levantava TypeError,
        # mesmo o payload sendo perfeitamente serializável em JSON.
        resultado = hash_canonico({"grupo": {1: "a", "b": "c"}})
        self.assertIsInstance(resultado, str)

    def test_chaves_mistas_e_deterministico(self):
        self.assertEqual(
            hash_canonico({"grupo": {1: "a", "b": "c"}}),
            hash_canonico({"grupo": {1: "a", "b": "c"}}),
        )

    def test_chave_int_e_chave_str_equivalente_colidem_apos_normalizacao(self):
        # Comportamento aceito: como toda chave é normalizada para str antes
        # de serializar (JSON de verdade só tem chave string mesmo), a
        # chave 1 (int) e a chave "1" (str) produzem o MESMO hash --
        # documentado aqui para não ser uma surpresa silenciosa.
        self.assertEqual(
            hash_canonico({"grupo": {1: "a"}}),
            hash_canonico({"grupo": {"1": "a"}}),
        )

    def test_int_e_float_equivalentes_produzem_hashes_diferentes(self):
        # RISCO ACEITO documentado na docstring de hash_canonico: 1 (int) e
        # 1.0 (float) são payloads DIFERENTES para este módulo, apesar de
        # JSON não distinguir tipo numérico na leitura.
        self.assertNotEqual(hash_canonico({"n": 1}), hash_canonico({"n": 1.0}))

    def test_chaves_colidentes_no_mesmo_dict_levantam_valueerror(self):
        # Achado da 2a rodada de revisão adversarial: sem esta checagem, um
        # dict com chave int 1 e chave str "1" (valores DIFERENTES) perdia
        # uma das duas entradas silenciosamente na normalização -- dois
        # payloads objetivamente diferentes produziam o MESMO hash.
        with self.assertRaises(ValueError):
            hash_canonico({"grupo": {1: "from_int_key", "1": "from_str_key"}})

    def test_chaves_colidentes_com_mesmo_valor_tambem_levantam_valueerror(self):
        # Mesmo quando o valor colidido é igual, a colisão em si (não o
        # valor) é o que deve ser rejeitada -- não corrigir para o caso
        # "sortudo" de valores iguais e deixar passar seria inconsistente.
        with self.assertRaises(ValueError):
            hash_canonico({"grupo": {1: "a", "1": "a"}})

    def test_chave_bool_usa_a_mesma_grafia_que_um_round_trip_json_real(self):
        # Achado do Codex (P2) na PR #328: str(True) == "True", mas um
        # round-trip JSON real produz a chave "true" (minúsculo) -- sem
        # isto, uma reentrega legítima (mesmo payload, depois de passar por
        # serialização/desserialização JSON de verdade em algum ponto do
        # transporte) virava ConflitoIdempotencia.
        self.assertEqual(
            hash_canonico({"a": {True: "x"}}),
            hash_canonico({"a": {"true": "x"}}),
        )
        self.assertEqual(
            hash_canonico({"a": {False: "x"}}),
            hash_canonico({"a": {"false": "x"}}),
        )

    def test_chave_none_usa_a_mesma_grafia_que_um_round_trip_json_real(self):
        # str(None) == "None", mas o round-trip real produz "null".
        self.assertEqual(
            hash_canonico({"a": {None: "x"}}),
            hash_canonico({"a": {"null": "x"}}),
        )

    def test_chave_none_e_chave_string_none_nao_colidem_mais(self):
        # Antes do fix (str(None) == "None"), {None: "a", "None": "b"} era
        # rejeitado como colisão -- mas depois de um round-trip JSON real
        # só "null" (a chave None) e "None" (a chave string) sobrevivem, e
        # são DIFERENTES -- não deveria ser tratado como colisão.
        resultado = hash_canonico({None: "a", "None": "b"})
        self.assertIsInstance(resultado, str)


class TestCriarEntrada(unittest.TestCase):
    def test_cria_com_hash_do_payload(self):
        entrada = criar_entrada("k1", {"a": 1}, agora=AGORA)
        self.assertEqual(entrada.idempotency_key, "k1")
        self.assertEqual(entrada.payload_hash, hash_canonico({"a": 1}))
        self.assertEqual(entrada.criado_em, AGORA)
        self.assertEqual(entrada.checkpoints, ())
        self.assertIsNone(entrada.resultado_registrado_em)

    def test_idempotency_key_e_normalizada(self):
        entrada = criar_entrada("  k1  ", {}, agora=AGORA)
        self.assertEqual(entrada.idempotency_key, "k1")

    def test_idempotency_key_vazia_levanta_valueerror(self):
        with self.assertRaises(ValueError):
            criar_entrada("", {}, agora=AGORA)

    def test_idempotency_key_so_espacos_levanta_valueerror(self):
        with self.assertRaises(ValueError):
            criar_entrada("   ", {}, agora=AGORA)

    def test_sem_agora_usa_relogio_real_tz_aware(self):
        entrada = criar_entrada("k1", {})
        self.assertIsNotNone(entrada.criado_em.tzinfo)

    def test_agora_naive_levanta_valueerror(self):
        with self.assertRaises(ValueError):
            criar_entrada("k1", {}, agora=datetime(2026, 9, 25, 12, 0, 0))

    def test_agora_normalizado_para_utc(self):
        from datetime import timezone as tz

        fuso_menos3 = tz(timedelta(hours=-3))
        agora_local = datetime(2026, 9, 25, 9, 0, 0, tzinfo=fuso_menos3)
        entrada = criar_entrada("k1", {}, agora=agora_local)
        self.assertEqual(entrada.criado_em, AGORA)
        self.assertEqual(entrada.criado_em.tzinfo, UTC)


class TestCriarOuReusarEntrada(unittest.TestCase):
    def test_sem_entrada_existente_cria_nova(self):
        entrada = criar_ou_reusar_entrada("k1", {"a": 1}, None, agora=AGORA)
        self.assertEqual(entrada.payload_hash, hash_canonico({"a": 1}))

    def test_mesmo_payload_reusa_a_mesma_entrada_sem_alterar_nada(self):
        original = criar_entrada("k1", {"a": 1}, agora=AGORA)
        reusada = criar_ou_reusar_entrada("k1", {"a": 1}, original, agora=AGORA + timedelta(hours=1))
        self.assertIs(reusada, original)
        # criado_em NÃO muda para o "agora" da segunda chamada -- é reuso, não recriação.
        self.assertEqual(reusada.criado_em, AGORA)

    def test_mesmo_payload_ordem_diferente_de_chaves_tambem_reusa(self):
        original = criar_entrada("k1", {"a": 1, "b": 2}, agora=AGORA)
        reusada = criar_ou_reusar_entrada("k1", {"b": 2, "a": 1}, original)
        self.assertIs(reusada, original)

    def test_payload_diferente_levanta_conflito(self):
        original = criar_entrada("k1", {"a": 1}, agora=AGORA)
        with self.assertRaises(ConflitoIdempotencia) as ctx:
            criar_ou_reusar_entrada("k1", {"a": 2}, original)
        self.assertEqual(ctx.exception.idempotency_key, "k1")
        self.assertEqual(ctx.exception.hash_existente, hash_canonico({"a": 1}))
        self.assertEqual(ctx.exception.hash_novo, hash_canonico({"a": 2}))

    def test_conflito_nao_altera_entrada_existente(self):
        original = criar_entrada("k1", {"a": 1}, agora=AGORA)
        try:
            criar_ou_reusar_entrada("k1", {"a": 2}, original)
        except ConflitoIdempotencia:
            pass
        self.assertEqual(original.payload_hash, hash_canonico({"a": 1}))

    def test_entrada_existente_de_outra_chave_levanta_valueerror(self):
        original = criar_entrada("k1", {"a": 1}, agora=AGORA)
        with self.assertRaises(ValueError):
            criar_ou_reusar_entrada("k2", {"a": 1}, original)

    def test_idempotency_key_e_normalizada_antes_de_comparar(self):
        original = criar_entrada("k1", {"a": 1}, agora=AGORA)
        reusada = criar_ou_reusar_entrada("  k1  ", {"a": 1}, original)
        self.assertIs(reusada, original)

    def test_agora_naive_levanta_valueerror_no_branch_de_reuso(self):
        # Achado da 2a rodada de revisão adversarial: só o branch
        # "entrada_existente is None" validava agora (via criar_entrada);
        # o branch de reuso aceitava um agora naive silenciosamente.
        original = criar_entrada("k1", {"a": 1}, agora=AGORA)
        with self.assertRaises(ValueError):
            criar_ou_reusar_entrada(
                "k1", {"a": 1}, original, agora=datetime(2026, 9, 25, 12, 0, 0)
            )

    def test_agora_naive_levanta_valueerror_no_branch_de_conflito(self):
        original = criar_entrada("k1", {"a": 1}, agora=AGORA)
        with self.assertRaises(ValueError):
            criar_ou_reusar_entrada(
                "k1", {"a": 2}, original, agora=datetime(2026, 9, 25, 12, 0, 0)
            )

    def test_agora_naive_e_validado_antes_de_qualquer_branch(self):
        # A validação roda ANTES de checar entrada_existente/hash -- um
        # agora naive é rejeitado mesmo quando entrada_existente é None.
        with self.assertRaises(ValueError):
            criar_ou_reusar_entrada(
                "k1", {"a": 1}, None, agora=datetime(2026, 9, 25, 12, 0, 0)
            )


class TestConsultarReentrega(unittest.TestCase):
    def test_sem_resultado_e_sem_checkpoint_e_trabalho_em_curso(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        resultado = consultar_reentrega(entrada)
        self.assertEqual(resultado.status, ReentregaStatus.TRABALHO_EM_CURSO)
        self.assertIsNone(resultado.resultado)
        self.assertIsNone(resultado.ultimo_checkpoint)

    def test_com_checkpoint_mas_sem_resultado_ainda_e_trabalho_em_curso(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = adicionar_checkpoint(entrada, {"passo": 1}, agora=AGORA)
        resultado = consultar_reentrega(entrada)
        self.assertEqual(resultado.status, ReentregaStatus.TRABALHO_EM_CURSO)
        self.assertEqual(resultado.ultimo_checkpoint.sequencia, 1)

    def test_com_resultado_registrado_e_resultado_observado(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = registrar_resultado(entrada, {"ok": True}, agora=AGORA)
        resultado = consultar_reentrega(entrada)
        self.assertEqual(resultado.status, ReentregaStatus.RESULTADO_OBSERVADO)
        self.assertEqual(resultado.resultado, {"ok": True})

    def test_resultado_observado_none_nao_e_confundido_com_trabalho_em_curso(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = registrar_resultado(entrada, None, agora=AGORA)
        resultado = consultar_reentrega(entrada)
        self.assertEqual(resultado.status, ReentregaStatus.RESULTADO_OBSERVADO)
        self.assertIsNone(resultado.resultado)


class TestAdicionarCheckpointReentrega(unittest.TestCase):
    """Achado da 1a rodada de revisão adversarial (P04 sub-entrega 2/N):
    reenvio do MESMO checkpoint (retry/heartbeat defensivo) deve ser um
    no-op, não consumir um slot de retenção nem disparar descarte FIFO de
    checkpoints antigos distintos."""

    def test_checkpoint_identico_ao_ultimo_e_no_op_idempotente(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = adicionar_checkpoint(entrada, {"passo": 1}, agora=AGORA)
        entrada2 = adicionar_checkpoint(entrada, {"passo": 1}, agora=AGORA + timedelta(minutes=1))
        self.assertIs(entrada2, entrada)
        self.assertEqual(len(entrada2.checkpoints), 1)

    def test_checkpoint_diferente_do_ultimo_acrescenta_normalmente(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = adicionar_checkpoint(entrada, {"passo": 1}, agora=AGORA)
        entrada = adicionar_checkpoint(entrada, {"passo": 2}, agora=AGORA)
        self.assertEqual(len(entrada.checkpoints), 2)

    def test_reenvio_duplicado_nao_derruba_checkpoints_antigos_do_fifo(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        for i in range(MAX_CHECKPOINTS_POR_OPERACAO):
            entrada = adicionar_checkpoint(entrada, {"passo": i}, agora=AGORA)
        checkpoints_antes = entrada.checkpoints
        # Reenvio do último checkpoint várias vezes -- sem o fix, cada
        # chamada empurraria o mais antigo para fora do FIFO.
        for _ in range(3):
            entrada = adicionar_checkpoint(
                entrada, {"passo": MAX_CHECKPOINTS_POR_OPERACAO - 1}, agora=AGORA
            )
        self.assertEqual(entrada.checkpoints, checkpoints_antes)

    def test_comparacao_e_so_com_o_ultimo_nao_com_o_historico_inteiro(self):
        # {"passo": 1} repete um checkpoint ANTERIOR (não o último) --
        # conta como progresso novo (ex.: voltou a um estado já visto), não
        # como reentrega, e é acrescentado normalmente.
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = adicionar_checkpoint(entrada, {"passo": 1}, agora=AGORA)
        entrada = adicionar_checkpoint(entrada, {"passo": 2}, agora=AGORA)
        entrada = adicionar_checkpoint(entrada, {"passo": 1}, agora=AGORA)
        self.assertEqual(len(entrada.checkpoints), 3)


class TestAdicionarCheckpoint(unittest.TestCase):
    def test_primeiro_checkpoint_tem_sequencia_1(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = adicionar_checkpoint(entrada, {"passo": 1}, agora=AGORA)
        self.assertEqual(len(entrada.checkpoints), 1)
        self.assertEqual(entrada.checkpoints[0].sequencia, 1)
        self.assertEqual(entrada.checkpoints[0].dados, {"passo": 1})

    def test_sequencia_cresce_a_cada_checkpoint(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = adicionar_checkpoint(entrada, {"passo": 1}, agora=AGORA)
        entrada = adicionar_checkpoint(entrada, {"passo": 2}, agora=AGORA)
        entrada = adicionar_checkpoint(entrada, {"passo": 3}, agora=AGORA)
        self.assertEqual([c.sequencia for c in entrada.checkpoints], [1, 2, 3])

    def test_nao_muta_a_entrada_original(self):
        original = criar_entrada("k1", {}, agora=AGORA)
        adicionar_checkpoint(original, {"passo": 1}, agora=AGORA)
        self.assertEqual(original.checkpoints, ())

    def test_excede_limite_de_retencao_descarta_mais_antigo_fifo(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        for i in range(MAX_CHECKPOINTS_POR_OPERACAO + 5):
            entrada = adicionar_checkpoint(entrada, {"passo": i}, agora=AGORA)
        self.assertEqual(len(entrada.checkpoints), MAX_CHECKPOINTS_POR_OPERACAO)
        # Os 5 primeiros (passo 0..4) devem ter sido descartados.
        self.assertEqual(entrada.checkpoints[0].dados, {"passo": 5})
        self.assertEqual(entrada.checkpoints[-1].dados, {"passo": MAX_CHECKPOINTS_POR_OPERACAO + 4})
        # A numeração de sequência continua crescente e sem reinício mesmo
        # após o descarte -- não vira 1..20 de novo.
        self.assertEqual(entrada.checkpoints[0].sequencia, 6)
        self.assertEqual(entrada.checkpoints[-1].sequencia, MAX_CHECKPOINTS_POR_OPERACAO + 5)

    def test_checkpoint_maior_que_limite_levanta_checkpoint_muito_grande(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        payload_grande = {"blob": "x" * (MAX_CHECKPOINT_BYTES + 1)}
        with self.assertRaises(CheckpointMuitoGrande) as ctx:
            adicionar_checkpoint(entrada, payload_grande, agora=AGORA)
        self.assertGreater(ctx.exception.tamanho_bytes, MAX_CHECKPOINT_BYTES)
        self.assertEqual(ctx.exception.limite_bytes, MAX_CHECKPOINT_BYTES)

    def test_checkpoint_exatamente_no_limite_e_aceito(self):
        # {"b":"...."} com separators compactos -- calcula o enchimento
        # exato para o payload serializado bater exatamente no limite.
        prefixo = '{"b":"'
        sufixo = '"}'
        tamanho_enchimento = MAX_CHECKPOINT_BYTES - len(prefixo) - len(sufixo)
        payload_no_limite = {"b": "x" * tamanho_enchimento}
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = adicionar_checkpoint(entrada, payload_no_limite, agora=AGORA)
        self.assertEqual(len(entrada.checkpoints), 1)

    def test_checkpoint_em_operacao_com_resultado_registrado_levanta_valueerror(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = registrar_resultado(entrada, {"ok": True}, agora=AGORA)
        with self.assertRaises(ValueError):
            adicionar_checkpoint(entrada, {"passo": 1}, agora=AGORA)

    def test_agora_naive_levanta_valueerror(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        with self.assertRaises(ValueError):
            adicionar_checkpoint(entrada, {"passo": 1}, agora=datetime(2026, 9, 25, 12, 0, 0))

    def test_orcamento_cumulativo_derruba_mais_antigos_alem_do_limite_de_contagem(self):
        # Achado do Codex (P2) na PR #328: MAX_CHECKPOINTS_POR_OPERACAO (20)
        # * MAX_CHECKPOINT_BYTES (64KiB) sozinho excede o limite de 1MiB de
        # um documento Firestore. Cada checkpoint aqui é único (não sofre
        # dedup pela reentrega) e quase no limite individual, então o
        # orçamento cumulativo tem que agir ANTES do limite de contagem.
        entrada = criar_entrada("k1", {}, agora=AGORA)
        tamanho_por_checkpoint = MAX_CHECKPOINT_BYTES - 40
        for i in range(MAX_CHECKPOINTS_POR_OPERACAO):
            entrada = adicionar_checkpoint(
                entrada, {"i": i, "blob": "x" * tamanho_por_checkpoint}, agora=AGORA
            )
        total_bytes = sum(
            len(str(c.dados).encode("utf-8")) for c in entrada.checkpoints
        )
        self.assertLessEqual(total_bytes, MAX_CHECKPOINTS_BYTES_TOTAL)
        self.assertLess(len(entrada.checkpoints), MAX_CHECKPOINTS_POR_OPERACAO)
        # Mantém sempre o(s) mais RECENTE(s) -- o último índice adicionado
        # tem que sobreviver.
        self.assertEqual(entrada.checkpoints[-1].dados["i"], MAX_CHECKPOINTS_POR_OPERACAO - 1)

    def test_orcamento_cumulativo_mantem_pelo_menos_um_checkpoint(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = adicionar_checkpoint(
            entrada, {"blob": "x" * (MAX_CHECKPOINT_BYTES - 20)}, agora=AGORA
        )
        self.assertEqual(len(entrada.checkpoints), 1)

    def test_mutar_dict_original_depois_de_adicionar_nao_afeta_o_checkpoint(self):
        # Achado do Codex (P2) na PR #328: o checkpoint guardava o dict do
        # chamador por referência; mutar o dict original depois mudava o
        # conteúdo do checkpoint "imutável" sem passar por nenhuma
        # validação.
        dados_originais = {"passo": 1, "detalhe": {"x": 1}}
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = adicionar_checkpoint(entrada, dados_originais, agora=AGORA)
        dados_originais["passo"] = 999
        dados_originais["detalhe"]["x"] = 999
        self.assertEqual(entrada.checkpoints[0].dados, {"passo": 1, "detalhe": {"x": 1}})


class TestRegistrarResultado(unittest.TestCase):
    def test_registra_resultado_e_marca_timestamp(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = registrar_resultado(entrada, {"ok": True}, agora=AGORA)
        self.assertEqual(entrada.resultado, {"ok": True})
        self.assertEqual(entrada.resultado_registrado_em, AGORA)

    def test_chamar_de_novo_com_mesmo_resultado_e_no_op_idempotente(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = registrar_resultado(entrada, {"ok": True}, agora=AGORA)
        entrada2 = registrar_resultado(entrada, {"ok": True}, agora=AGORA + timedelta(hours=1))
        self.assertIs(entrada2, entrada)
        # O timestamp original é preservado -- reentrega não reescreve.
        self.assertEqual(entrada2.resultado_registrado_em, AGORA)

    def test_chamar_de_novo_com_resultado_diferente_levanta_valueerror(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = registrar_resultado(entrada, {"ok": True}, agora=AGORA)
        with self.assertRaises(ValueError):
            registrar_resultado(entrada, {"ok": False}, agora=AGORA)

    def test_resultado_diferente_nao_altera_entrada_original(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = registrar_resultado(entrada, {"ok": True}, agora=AGORA)
        try:
            registrar_resultado(entrada, {"ok": False}, agora=AGORA)
        except ValueError:
            pass
        self.assertEqual(entrada.resultado, {"ok": True})

    def test_resultado_com_nan_reenviado_identico_e_no_op_idempotente(self):
        # Achado da 1a rodada de revisão adversarial: float("nan") != NaN em
        # Python (`==` sempre False para NaN), então comparar por `==` fazia
        # uma reentrega IDÊNTICA (mesmo NaN) ser tratada como conflito.
        # Comparação por serialização canônica resolve isso ("NaN" ==
        # "NaN" como string).
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = registrar_resultado(entrada, {"valor": float("nan")}, agora=AGORA)
        entrada2 = registrar_resultado(entrada, {"valor": float("nan")}, agora=AGORA)
        self.assertIs(entrada2, entrada)

    def test_resultado_bool_e_int_equivalente_sao_tratados_como_diferentes(self):
        # Achado da 1a rodada de revisão adversarial: `True == 1` é True em
        # Python, mas hash_canonico já trata bool e int como payloads
        # diferentes -- usar `==` aqui criaria duas regras de "mesmo valor"
        # incompatíveis no mesmo módulo.
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = registrar_resultado(entrada, True, agora=AGORA)
        with self.assertRaises(ValueError):
            registrar_resultado(entrada, 1, agora=AGORA)

    def test_agora_naive_levanta_valueerror_mesmo_no_caminho_de_no_op(self):
        # Achado da 1a rodada de revisão adversarial: a validação de
        # tz-awareness rodava DEPOIS da checagem de "já registrado", então
        # o caminho de no-op (mesmo resultado reenviado) mascarava um
        # `agora` naive que seria rejeitado numa chamada equivalente contra
        # uma entrada ainda não concluída.
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = registrar_resultado(entrada, {"ok": True}, agora=AGORA)
        with self.assertRaises(ValueError):
            registrar_resultado(entrada, {"ok": True}, agora=datetime(2026, 9, 25, 12, 0, 0))

    def test_resultado_nao_serializavel_e_rejeitado_ja_na_primeira_chamada(self):
        # Achado do Codex (P2) na PR #328: antes do fix, um resultado
        # não-serializável (ex.: datetime) era aceito silenciosamente na
        # PRIMEIRA chamada (dataclasses.replace não serializava nada) e só
        # quebrava com TypeError numa REENTREGA (quando a comparação via
        # serialização canônica rodava pela primeira vez) -- inconsistente
        # com o resto do módulo, que falha cedo. Agora falha já na
        # primeira chamada.
        entrada = criar_entrada("k1", {}, agora=AGORA)
        with self.assertRaises(TypeError):
            registrar_resultado(entrada, AGORA, agora=AGORA)

    def test_entrada_original_nao_e_alterada_quando_resultado_e_rejeitado(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        try:
            registrar_resultado(entrada, AGORA, agora=AGORA)
        except TypeError:
            pass
        self.assertIsNone(entrada.resultado_registrado_em)

    def test_mutar_dict_original_depois_de_registrar_nao_afeta_o_resultado(self):
        # Achado do Codex (P2) na PR #328: o resultado guardava o dict do
        # chamador por referência; mutar o dict original depois mudava o
        # "resultado observado" sem passar por nenhuma validação --
        # quebrava a garantia de nunca sobrescrever (item 10) na prática.
        dados_originais = {"ok": True, "detalhe": {"x": 1}}
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = registrar_resultado(entrada, dados_originais, agora=AGORA)
        dados_originais["ok"] = False
        dados_originais["detalhe"]["x"] = 999
        self.assertEqual(entrada.resultado, {"ok": True, "detalhe": {"x": 1}})

    def test_resultado_none_e_um_resultado_valido_registravel(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = registrar_resultado(entrada, None, agora=AGORA)
        self.assertIsNone(entrada.resultado)
        self.assertIsNotNone(entrada.resultado_registrado_em)

    def test_registrar_none_de_novo_e_no_op(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = registrar_resultado(entrada, None, agora=AGORA)
        entrada2 = registrar_resultado(entrada, None, agora=AGORA + timedelta(hours=1))
        self.assertIs(entrada2, entrada)

    def test_none_depois_de_resultado_nao_none_levanta_valueerror(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = registrar_resultado(entrada, {"ok": True}, agora=AGORA)
        with self.assertRaises(ValueError):
            registrar_resultado(entrada, None, agora=AGORA)

    def test_nao_muta_a_entrada_original(self):
        original = criar_entrada("k1", {}, agora=AGORA)
        registrar_resultado(original, {"ok": True}, agora=AGORA)
        self.assertIsNone(original.resultado_registrado_em)

    def test_preserva_checkpoints_existentes(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        entrada = adicionar_checkpoint(entrada, {"passo": 1}, agora=AGORA)
        entrada = registrar_resultado(entrada, {"ok": True}, agora=AGORA)
        self.assertEqual(len(entrada.checkpoints), 1)

    def test_agora_naive_levanta_valueerror(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        with self.assertRaises(ValueError):
            registrar_resultado(entrada, {"ok": True}, agora=datetime(2026, 9, 25, 12, 0, 0))


class TestCheckpointDataclass(unittest.TestCase):
    def test_sequencia_menor_que_1_levanta_valueerror(self):
        with self.assertRaises(ValueError):
            Checkpoint(sequencia=0, dados={}, criado_em=AGORA)

    def test_criado_em_naive_levanta_valueerror(self):
        with self.assertRaises(ValueError):
            Checkpoint(sequencia=1, dados={}, criado_em=datetime(2026, 9, 25, 12, 0, 0))

    def test_dados_nao_serializaveis_levanta_typeerror(self):
        with self.assertRaises(TypeError):
            Checkpoint(sequencia=1, dados={"x": object()}, criado_em=AGORA)


class TestLedgerEntryDataclass(unittest.TestCase):
    def test_criado_em_naive_levanta_valueerror(self):
        with self.assertRaises(ValueError):
            LedgerEntry(
                idempotency_key="k1",
                payload_hash="abc",
                criado_em=datetime(2026, 9, 25, 12, 0, 0),
            )

    def test_resultado_registrado_em_naive_levanta_valueerror(self):
        with self.assertRaises(ValueError):
            LedgerEntry(
                idempotency_key="k1",
                payload_hash="abc",
                criado_em=AGORA,
                resultado_registrado_em=datetime(2026, 9, 25, 12, 0, 0),
            )

    def test_e_imutavel(self):
        entrada = criar_entrada("k1", {}, agora=AGORA)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            entrada.idempotency_key = "outra"


if __name__ == "__main__":
    unittest.main()
