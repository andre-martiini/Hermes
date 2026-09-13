# Registro de execução — plano-hermes-autonomo-2026-09-06

Um bloco por pacote (P00–P18), no formato da seção 14.2 do plano. Cada pacote novo é acrescentado ao final; nenhum bloco anterior é reescrito depois de `validado`. Sem segredos nem conteúdo privado — apenas referências a artefatos e IDs.

**Blocos P00 a P02 sub-entrega 11/N foram movidos para
docs/autonomia/execucao-archive-p00-a-p02sub11.md em 2026-09-09 (P02
sub-entrega 15/N). Blocos P02 sub-entrega 12/N a 16/N foram movidos, em
2026-09-09 também, para um SEGUNDO arquivo de arquivo,
docs/autonomia/execucao-archive-p02-sub12-a-sub16.md — durante a correção
da sub-entrega P01 5/N, depois que uma escrita anterior derrubou
silenciosamente o bloco P02 sub-entrega 17/N na retranscrição manual de
um arquivo de 85701 bytes, e uma tentativa de reenviar tudo somado num
arquivo de arquivo só (159725 bytes) falhou por limite de saída (64000
tokens). O bloco P02 sub-entrega 17/N foi movido, também em 2026-09-09,
para um TERCEIRO arquivo de arquivo,
docs/autonomia/execucao-archive-p02-sub17.md — durante a sub-entrega P01
6/N, preventivamente. Os blocos P01 sub-entrega 3/N e 4/N foram movidos,
ainda em 2026-09-09, para um QUARTO arquivo de arquivo,
docs/autonomia/execucao-archive-p01-sub3-a-sub4.md — durante a sub-entrega
P01 7/N, também preventivamente. O bloco P01 sub-entrega 5/N foi movido,
ainda em 2026-09-09, para um QUINTO arquivo de arquivo,
docs/autonomia/execucao-archive-p01-sub5.md — durante a sub-entrega P01
8/N, preventivamente pelo mesmo motivo. Os blocos P01 sub-entrega 6/N a
9/N (fechamento do pacote) foram movidos, ainda em 2026-09-09, para um
SEXTO arquivo de arquivo, docs/autonomia/execucao-archive-p01-sub6-a-sub9.md
— durante a sub-entrega P02 19/N, preventivamente, ao registrar
retroativamente as sub-entregas P02 18/N e 19/N. Os blocos P02
sub-entrega 18/N a P03 sub-entrega 3/N foram movidos, em 2026-09-12, para
um SÉTIMO arquivo de arquivo,
docs/autonomia/execucao-archive-p02sub18-a-p03sub3.md — pela tarefa
agendada de avanço autônomo, ao registrar retroativamente a sub-entrega
P03 7/N, preventivamente (o arquivo ativo tinha passado de ~50KB sem
re-arquivamento desde o sexto arquivo). Ver o cabeçalho de cada arquivo
de arquivo para o relato completo. Os blocos P03 sub-entrega 4/N e 5/N foram
movidos, em 12/09/2026, para um OITAVO arquivo de arquivo,
docs/autonomia/execucao-archive-p03sub4-a-sub5.md — pela tarefa agendada de
avanço autônomo, ao acrescentar a entrada da sub-entrega P03 8/N,
preventivamente (o arquivo ativo passaria de ~50KB ao acrescentar essa
entrada sem re-arquivamento). Os blocos P03 sub-entrega 6/N e 7/N foram
movidos, em 13/09/2026, para um NONO arquivo de arquivo,
docs/autonomia/execucao-archive-p03sub6-a-sub7.md — pela tarefa agendada de
avanço autônomo, ao acrescentar a entrada da sub-entrega P03 10/N,
preventivamente (mesmo motivo).** Nenhum conteúdo foi perdido; é
uma relocação, não uma edição. Este arquivo continua sendo a fonte de
verdade para tudo a partir da sub-entrega P03 8/N em diante.

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 1cdbf7e74d0617cd0ea6ab61616897d7e97b5307
pacote: "P03 sub-entrega 8/N -- outputSchema/structuredContent (passo 3 do plano), fatia inicial: contrato de dados publicado em tools/list e refletido em tools/call, so para calculadora (candidato de menor risco -- pura, deterministica, sem rede nem Firestore)"
estado: validado
inicio: "2026-09-12T15:00:00Z"
fim: "2026-09-12T15:51:52Z"
arquivos_alterados:
  - functions/tools/registry.py (nova `_OUTPUT_SCHEMAS` -- lista FECHADA, mesmo padrao de `_CAMPOS_COM_TOLERANCIA_A_STRING_JSON`/`_CAMPOS_COM_ENUM_TOLERANTE_A_CASE` ja existentes neste arquivo -- e nova `output_schema(tool_name) -> dict | None`, hoje so com entrada para `calculadora`: `{expressao: str (obrigatorio), resultado: str, erro: str}`, `additionalProperties: false`)
  - functions/mcp_server.py (`_handle_tools_list` publica `outputSchema` no objeto Tool quando `registry.output_schema(name)` existe, campo opcional omitido -- nao null -- quando ausente, mesma convencao de `annotations`; `_handle_tools_call` inclui `structuredContent` no envelope de `tools/call` quando o executor devolveu um dict E a tool tem outputSchema publicado, reconstruido do `text` ja serializado com `json.dumps(..., default=str)` -- nunca do dict cru do executor -- ver decisoes)
  - functions/test_output_schema.py (novo -- 14 testes em 3 classes: TestOutputSchema com paridade contra as 105 tools reais do catalogo, TestHandleToolsListOutputSchema ponta a ponta em tools/list, TestIntegracaoHandleToolsCallStructuredContent ponta a ponta em tools/call incluindo o teste de nao-vacuidade do achado da revisao adversarial)
decisoes:
  - id: p03-sub8-calculadora-primeira-tool-com-outputschema
    motivo: "outputSchema exige definir um CONTRATO DE DADOS por tool -- ao contrario de `annotations` (sub-entregas 6/N-7/N), que deriva de campos ja classificados no inventario para as 105 tools de uma vez, nao ha atalho generico aqui: serializar qualquer dict de retorno como 'o schema' seria publicar um contrato inventado, nunca verificado contra a forma real do resultado. `calculadora` escolhida como primeira por ser o candidato de menor risco do catalogo -- pura, deterministica, sem rede nem Firestore (inventario: necessidade_de_rede=False, verificador='deterministico, recomputavel pelo chamador'), sempre devolve um dict achatado com EXATAMENTE duas formas possiveis (sucesso: expressao+resultado; falha: expressao+erro), nunca as duas juntas, nunca um terceiro campo. Nao exigiu investigar comportamento assincrono, paginacao nem variacao de forma por argumento -- ao contrario da maioria das outras ~104 tools do catalogo, que ficam deliberadamente de fora por enquanto."
    autoridade: existente_ou_nova
  - id: p03-sub8-primeira-rodada-achou-crash-latente-no-mecanismo-geral
    motivo: "PRIMEIRA rodada de revisao adversarial (Agent tool, general-purpose, sem contexto da implementacao), achado real ANTES de qualquer coisa ir pro Argos: a implementacao original fazia `estruturado = result` (o dict cru do executor) em vez de derivar de `text` (que ja passa por `json.dumps(..., default=str)`). O envelope inteiro (incluindo `structuredContent`) e reserializado mais abaixo na pilha, em `_json_response`, via `json.dumps(payload, ensure_ascii=False)` -- SEM `default=str` e FORA de qualquer try/except que proteja o cliente de um erro cru. Para `calculadora` isso nunca falha hoje (o handler ja forca `str()` em tudo), mas o MECANISMO GERAL que esta sub-entrega introduz ficaria com um bug latente: a proxima tool a ganhar outputSchema cujo handler devolvesse um valor nao-JSON-nativo (datetime, Timestamp do Firestore, Decimal -- comuns neste catalogo) quebraria essa serializacao final com um TypeError nao tratado. Corrigido: `estruturado` passou a vir de `json.loads(text)`, nunca do `result` cru. Comprovado nao-vacuo empiricamente (mesmo padrao usado na PR #10 do Argos): revertendo o fix localmente, o novo teste `test_valor_nao_serializavel_no_dict_nao_quebra_structured_content` falha de verdade (`AssertionError: datetime.date(2026, 9, 12) != '2026-09-12'`); com o fix, passa."
    autoridade: existente_ou_nova
  - id: p03-sub8-segunda-rodada-sobre-o-fix-achou-escopo-largo-demais
    motivo: "SEGUNDA rodada de revisao adversarial, sobre o fix da primeira (mesmo padrao das sub-entregas 4/N-6/N e da PR #219/#10 do Argos): achou que a guarda `isinstance(result, dict)` sozinha fazia o round-trip `json.dumps`->`json.loads` rodar em TODA chamada de tool que devolve dict (a maioria das 105 do catalogo), nao so `calculadora` -- CPU gasta sem necessidade nas outras ~104, so pra descartar o resultado logo depois porque `registry.output_schema(name)` e None pra elas. Corrigido: guarda passou a `isinstance(result, dict) and registry.output_schema(name)`, e o check redundante mais abaixo (que checava `output_schema` de novo antes de anexar `structuredContent` ao envelope) foi simplificado para so `estruturado is not None`, ja que a segunda condicao ficou implicita na primeira."
    autoridade: existente_ou_nova
  - id: p03-sub8-terceira-rodada-sobre-o-segundo-fix-nao-achou-nada
    motivo: "TERCEIRA rodada de revisao adversarial, sobre o fix da segunda: percorreu explicitamente todos os caminhos possiveis de `_handle_tools_call` (sucesso com/sem schema, erro-dict com/sem schema, resultado string, excecao do executor, ToolNotAvailable) e confirmou cada um correto; confirmou que `registry.output_schema` deixou de ser chamado de forma redundante dentro da mesma funcao; confirmou que o teste que cobre 'tool sem outputSchema mas resultado e dict' (`test_tool_sem_output_schema_nunca_leva_structured_content_mesmo_com_dict`) de fato exercita o caminho corrigido, nao uma suposicao datada. Nao achou nada -- parada aqui, conforme a disciplina (escalar so enquanto uma rodada acha algo real; 'nao achou nada' e resultado valido, nao inventado pra parecer completo)."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "python3 -m venv + pip install -r requirements.txt (ambiente limpo, clonado via credenciais do sandbox -- primeira vez nesta sessao que a suite completa roda de fato, nao so os arquivos do escopo)"
    - "python3 -m unittest test_output_schema -v (arquivo isolado)"
    - "python3 -m unittest discover -s . -p 'test_*.py' -q (suite completa, antes e depois de cada rodada de correcao)"
  resultados:
    - "Baseline (antes de qualquer mudanca desta sub-entrega, clone limpo de origin/main): 1815/1815, 0 falhas, 0 erros -- confirma o numero ja registrado pela sub-entrega 7/N."
    - "Arquivo isolado test_output_schema.py: 14/14, 0 falhas, 0 erros."
    - "Suite completa apos a implementacao e as 3 rodadas de correcao: 1829/1829, 0 falhas, 0 erros, sem regressao (1815 baseline + 14 novos)."
evidencias:
  - "Tres rodadas de revisao adversarial independente (Agent tool, general-purpose, cada uma sem contexto da implementacao ou das rodadas anteriores): a primeira achou o bug latente de serializacao no mecanismo geral (ver decisoes); a segunda, sobre o fix da primeira, achou que o escopo do round-trip json.dumps/json.loads era mais largo que o pretendido; a terceira, sobre o fix da segunda, nao achou nada."
  - "Teste de nao-vacuidade: o teste que prova a correcao do achado da 1a rodada foi executado tambem SEM o fix (revertido localmente por 1 linha), confirmando que falha de verdade nesse caso e so passa com a correcao aplicada -- nao e um teste vazio."
  - "Teste de paridade (TestOutputSchema::test_paridade_apenas_calculadora_tem_output_schema_hoje) cobre TODAS as tools reais do catalogo (registry.list_tool_names()), nao so calculadora escolhida a dedo -- confirma que a lista fechada nao vazou para nenhuma outra tool."
  - "Todos os 3 arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificacao de hash local (git hash-object) contra o sha retornado pelo Argos -- os 3 batendo de primeira, sem drift de whitespace nem corrupcao. Verificacao adicional, mais forte que o hash isolado do proprio Argos: git fetch do branch remoto (refspec explicito) + git show origin/<branch>:<path> | git hash-object --stdin comparado ao arquivo local, para os 3 arquivos -- identico."
  - "Sanity check do PR: changed_files=3, additions=355, deletions=1 no retorno de argos_criar_pr_repositorio -- bate exatamente com git diff --stat main origin/<branch> rodado localmente antes de abrir o PR, sem arquivo extra nem reconstrucao acidental."
  - "PR #251 aberta (https://github.com/andre-martiini/Hermes/pull/251), com o relato completo das 3 rodadas no corpo -- AINDA NAO MESCLADA, aguardando revisao e merge manual do Andre."
  - "CONFIRMACAO POSTERIOR (12/09/2026, tarefa agendada de avanco autonomo, ao iniciar a sub-entrega 9/N): PR #251 mesclada pelo Andre -- confirmado por `git clone` publico do repositorio + `git log --oneline -5 origin/main`, merge commit `ea134f3d` presente na historia de `main` (mensagem: \"P03 sub-entrega 8/N: outputSchema/structuredContent para calculadora (#251)\"), e por `git branch -r` nao mostrar mais o branch de origem da PR (apagado automaticamente no merge). Estado desta entrada atualizado de `pronto_para_revisao` para `validado` nesta mesma sessao, sem reescrever nenhum outro campo do bloco."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por confirmacao posterior (ver evidencias): PR #251 mesclada; esta entrada passou de pronto_para_revisao para validado."
  - "ABERTA, nova (achado da 1a rodada de revisao adversarial, aceito como limitacao deliberada por enquanto): `structuredContent` so chega no caminho de EXECUCAO DIRETA de `_handle_tools_call` -- nao chega nos caminhos que usam `_text_result` (confirmacao pendente/negada, job assincrono, `confirmar_acao`). `calculadora` nunca passa por eles hoje (nao esta em `_CONFIRMACAO_OBRIGATORIA` nem em `_ASYNC_TOOLS`), mas `_exige_confirmacao` tambem consulta `system/mcp_access.confirm_tools` em runtime (Firestore) -- se um dia alguem configurar `calculadora` la, as chamadas sairiam sem `structuredContent` mesmo com outputSchema continuando anunciado em tools/list. Fechar isso direito exigiria levar `structuredContent` para dentro de `_text_result`, usada por fluxos bem mais amplos que so calculadora -- fora do escopo desta fatia pequena."
  - "ABERTA, deliberadamente: outputSchema para as demais ~103 tools do catalogo continua fora de escopo (buscar_contato coberta pela sub-entrega 9/N, ver bloco seguinte) -- cada uma exige investigar a forma real do handler antes de publicar um contrato, mesma disciplina das outras excecoes fechadas deste modulo."
  - "ABERTA, deliberadamente (herdada da sub-entrega 7/N): idempotentHint continua fora de escopo -- precisa de investigacao dedicada por HANDLER, nenhum campo do inventario atual registra isso."
  - "ABERTA: a fatia `envelope` do passo 3 do plano (alem de outputSchema/structuredContent/annotations, ja cobertos em parte) nao foi investigada nesta sub-entrega."
  - "Pendencias ja registradas em blocos anteriores e nao tocadas por esta sub-entrega continuam abertas: religar inventario tipado (P03 sub-entrega 1/N) a decisao de politica real; ambiguidades de classificacao (gerar_relatorio, salvar_memoria_global); card do Telegram de rascunho degradado nao reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore nao configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupcao silenciosa em escritas grandes via Argos; passo 2 do P02 (OAuth claims/scopes) como hardening futuro nao-bloqueante; inconsistencia de criterio nao-bloqueante em 5 das 7 tools sem dominio_rede classificado (sub-entrega 7/N)."
proximo_pacote: "P03 -- ver bloco da sub-entrega 9/N (PR #254, aguardando merge do Andre) para o proximo passo apos ela."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: a32df3874bf3880fe82b5f9a36b7feb6694fa651
pacote: "P03 sub-entrega 9/N -- outputSchema/structuredContent (passo 3 do plano), segunda fatia: contrato de dados publicado em tools/list e refletido em tools/call para buscar_contato, apos calculadora (sub-entrega 8/N, PR #251, confirmada mesclada nesta mesma execucao -- ver bloco anterior)"
estado: validado
inicio: "2026-09-12T19:05:00Z"
fim: "2026-09-12T19:27:15Z"
arquivos_alterados:
  - "functions/tools/registry.py (nova entrada `_OUTPUT_SCHEMAS['buscar_contato']` -- contrato para as duas formas que `_buscar_contato` produz: termo vazio, `{erro: str, candidatos: []}`, ou sucesso, `{candidatos: [...]}`; item de `candidatos` com 8 campos, `additionalProperties: false` -- pessoa_id/nome/email/telefone/whatsapp_chat_id/tags/score tipados normalmente, `modelo_interacao` deliberadamente solto em `type: [object, null]` sem `properties` aninhado)"
  - "functions/test_output_schema.py (5 testes novos: paridade do contrato puro contra as 106 tools reais do catalogo, publicacao em tools/list, e tres testes de integracao ponta a ponta via `_handle_tools_call` -- sucesso, termo vazio, paridade campo a campo contra o schema publicado)"
decisoes:
  - id: p03-sub9-buscar-contato-segunda-tool-candidata-de-baixo-risco
    motivo: "Entre os poucos handlers do catalogo que devolvem DICT CRU (nao string serializada) -- pre-condicao atual do mecanismo de structuredContent -- `buscar_contato` foi escolhida por ser pura leitura, sem rede, sem escrita, com apenas dois `return` possiveis no corpo da funcao (nao amostragem: leitura completa de `tools/hermes_tools.py::_buscar_contato`). Candidatas descartadas nesta rodada: `consultar_historico_acoes` e `buscar_arquivos_acervo` (item de resultado vem de funcoes de busca em outros modulos -- busca_grafo.py/busca_acervo.py -- exigiria investigar a forma delas tambem, fatia maior); `consultar_investimentos` (LEITURA_E_ESCRITA, depende de servico externo, dados financeiros -- risco maior). `consultar_saude`/`obter_acao`, sugeridas como candidatas pela sub-entrega 8/N, foram descartadas apos investigacao: `_consultar_saude` serializa o resultado para STRING via `json.dumps` antes de devolver (nao teria structuredContent mesmo com outputSchema publicado -- contrato anunciado nunca cumprido, pior que omissao) e `obter_acao` tem forma bem mais complexa (plano_acao aninhado, anexos, campos de data com formatos variaveis) que exigiria investigacao proporcional a uma sub-entrega propria."
    autoridade: existente_ou_nova
  - id: p03-sub9-modelo-interacao-contrato-solto-e-required
    motivo: "`modelo_interacao` vem de `data.get('modelo_interacao')` sem default -- confirmado em `main.py::parse_resposta_modelo_pessoa` (unico lugar que escreve o campo) que o valor e sempre `None` ou um dict de 4 chaves (registro/tempo_resposta_tipico/acoes_recentes/atualizado_em), mas o CONTEUDO desse dict e gerado por LLM, sem a mesma garantia estrutural do resto do item -- por isso o contrato aqui fica em `type: [object, null]`, sem `properties`/`additionalProperties` aninhado, mesmo espirito ja usado para os hints nao investigados de `mcp_annotations`. Esta em `required` (nao opcional) porque a CHAVE esta sempre presente no dict construido por `_buscar_contato`, mesmo quando o valor e `None` -- mesmo tratamento dado as outras 7 chaves sempre presentes do item."
    autoridade: existente_ou_nova
  - id: p03-sub9-primeira-rodada-achou-comentario-overclaiming
    motivo: "PRIMEIRA rodada de revisao adversarial (Agent tool, general-purpose, sem contexto da implementacao), achado real antes de qualquer coisa ir pro Argos: o comentario original de `_OUTPUT_SCHEMAS['buscar_contato']` afirmava que pessoa_id/nome/email/telefone/whatsapp_chat_id sao 'sempre string' so por causa do default `''` em `data.get(campo, '')` -- raciocinio errado, porque `dict.get(chave, default)` so devolve o default quando a CHAVE ESTA AUSENTE, nao quando esta presente com outro tipo. Como ha ~10 pontos de escrita diferentes na colecao `perfil_pessoas` (main.py, telegram_extended.py, contact_merge_utils.py e outros, nenhum auditado nesta sub-entrega), um documento legado com, por exemplo, `telefone` gravado como numero atravessaria sem cast e o `structuredContent` produzido divergiria silenciosamente do `outputSchema` publicado para aquele candidato especifico -- nao trava o Hermes (nada valida o envelope contra o schema antes de responder), mas e uma garantia mais fraca do que o comentario original alegava. Corrigido: comentario reescrito para nao overclaim, com o cenario concreto documentado e `pessoa_id` (sempre `doc.id`, garantido pelo SDK do Firestore) e `score` (sempre `float`, construido no proprio handler) explicitamente diferenciados desse risco -- registrado como pendencia nao-bloqueante, sem adicionar validacao runtime nova (mudaria comportamento de producao da tool, fora do escopo de uma fatia de contrato)."
    autoridade: existente_ou_nova
  - id: p03-sub9-segunda-rodada-sobre-o-fix-nao-achou-nada-de-novo
    motivo: "SEGUNDA rodada de revisao adversarial, sobre a correcao da primeira (mesmo padrao das sub-entregas 2/N, 4/N, 5/N, 6/N e da PR #219/#10 do Argos): confirmou que o comentario corrigido distingue corretamente pessoa_id/score do risco do restante dos campos, confirmou que adicionar `modelo_interacao` a `required` e correto (chave sempre presente no dict construido pelo handler) e nao entra em conflito com `type: [object, null]` (obrigatoriedade de chave e nulabilidade de valor sao ortogonais em JSON Schema), e conferiu que os testes atualizados batem com o schema sem deixar nenhuma asserção contraditória ou desatualizada. Nao achou nada de novo -- parada aqui, conforme a disciplina (escalar so enquanto uma rodada acha algo real; observou um nit de estilo nao-bloqueante: uma asserção redundante em um teste, sem efeito pratico)."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "python3 -m venv + pip install -r requirements.txt (ambiente limpo, clonado publicamente via git clone do repositorio)"
    - "python3 -m unittest test_output_schema -v (arquivo isolado)"
    - "python3 -m unittest discover -s . -p 'test_*.py' -q (suite completa, antes e depois da correcao)"
  resultados:
    - "Baseline (antes de qualquer mudanca desta sub-entrega, clone de origin/main incluindo a PR #251 ja mesclada): 1829/1829, 0 falhas, 0 erros -- confirma o numero ja registrado pela sub-entrega 8/N."
    - "Arquivo isolado test_output_schema.py apos a implementacao e a correcao: 19/19, 0 falhas, 0 erros."
    - "Suite completa apos a implementacao e a correcao: 1834/1834, 0 falhas, 0 erros, sem regressao (1829 baseline + 5 novos)."
evidencias:
  - "Duas rodadas de revisao adversarial independente (Agent tool, general-purpose, cada uma sem contexto da implementacao ou da rodada anterior): a primeira achou o comentario overclaiming sobre garantia de tipo dos campos vindos de Firestore (ver decisoes); a segunda, sobre a correcao, nao achou nada de novo."
  - "Teste de paridade (TestOutputSchema::test_paridade_calculadora_e_buscar_contato_tem_output_schema_hoje) cobre TODAS as tools reais do catalogo (registry.list_tool_names(), 106 hoje), nao so as duas escolhidas a dedo -- confirma que a lista fechada nao vazou para nenhuma outra tool."
  - "Os 2 arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificacao de hash local (git hash-object) contra o sha retornado pelo Argos -- os 2 batendo de primeira. Verificacao adicional, mais forte que o hash isolado do proprio Argos: git fetch do branch remoto + git show FETCH_HEAD:<path> | git hash-object --stdin comparado ao arquivo local, para os 2 arquivos -- identico."
  - "Sanity check do PR: changed_files=2, additions=219, deletions=21 no retorno de argos_criar_pr_repositorio -- bate exatamente com git diff --stat rodado localmente contra o commit-base da branch antes de abrir o PR."
  - "PR #254 aberta (https://github.com/andre-martiini/Hermes/pull/254), com o relato completo das 2 rodadas no corpo -- AINDA NAO MESCLADA, aguardando revisao e merge manual do Andre."
  - "CONFIRMACAO POSTERIOR (13/09/2026, tarefa agendada de avanco autonomo, ao iniciar a sub-entrega 10/N -- o conector Argos ficou indisponivel para o disparo anterior do dia, que so pode confirmar isto por leitura publica via git, ver bloco seguinte): PR #254 mesclada pelo Andre, e PR #255 (diario desta propria sub-entrega, que a registrou como pronto_para_revisao) tambem -- confirmado por git clone publico do repositorio + git log --oneline origin/main, merge commits cc1b3e0 (#254) e 77c95bf (#255) presentes na historia de main, ambos em 12/09/2026 17h02 BRT. Estado desta entrada atualizado de pronto_para_revisao para validado nesta mesma sessao, sem reescrever nenhum outro campo do bloco -- mesmo padrao ja usado na sub-entrega 8/N."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por confirmacao posterior (ver evidencias): PR #254 e PR #255 mescladas; esta entrada passou de pronto_para_revisao para validado."
  - "ABERTA, herdada da sub-entrega 8/N: `structuredContent` so chega no caminho de EXECUCAO DIRETA de `_handle_tools_call`, nao nos caminhos que usam `_text_result`. `buscar_contato` nao esta em `_CONFIRMACAO_OBRIGATORIA` nem em `_ASYNC_TOOLS` hoje, mas o mesmo risco de configuracao futura via Firestore (`system/mcp_access.confirm_tools`) documentado para calculadora se aplica aqui tambem."
  - "ABERTA, nova, NAO-bloqueante (achado da 1a rodada de revisao adversarial desta sub-entrega): pessoa_id/nome/email/telefone/whatsapp_chat_id/tags do item de `buscar_contato` sao tipados como string/array assumindo que ~10 pontos de escrita diferentes em `perfil_pessoas` (main.py, telegram_extended.py, contact_merge_utils.py e outros) sempre gravam o tipo pretendido -- nenhum desses pontos foi auditado nesta sub-entrega. Um documento legado com tipo errado produziria `structuredContent` divergente do `outputSchema` publicado para aquele candidato especifico, sem quebrar o Hermes (nada valida o envelope contra o schema antes de responder). Corrigir isso com certeza exigiria auditar todos os pontos de escrita ou adicionar validacao/coercao no proprio `_buscar_contato` -- fora do escopo desta fatia de contrato; candidato a sub-entrega futura se algum cliente MCP real reportar divergencia."
  - "ABERTA, deliberadamente: outputSchema para as demais ~102 tools do catalogo (buscar_contato e calculadora ja cobertas) continua fora de escopo -- cada uma exige investigar a forma real do handler antes de publicar um contrato."
  - "ABERTA, deliberadamente (herdada da sub-entrega 7/N): idempotentHint continua fora de escopo -- precisa de investigacao dedicada por HANDLER, nenhum campo do inventario atual registra isso."
  - "ABERTA: a fatia `envelope` do passo 3 do plano (alem de outputSchema/structuredContent/annotations, ja cobertos em parte) nao foi investigada nesta sub-entrega."
  - "Pendencias ja registradas em blocos anteriores e nao tocadas por esta sub-entrega continuam abertas: religar inventario tipado (P03 sub-entrega 1/N) a decisao de politica real; ambiguidades de classificacao (gerar_relatorio, salvar_memoria_global); card do Telegram de rascunho degradado nao reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore nao configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupcao silenciosa em escritas grandes via Argos; passo 2 do P02 (OAuth claims/scopes) como hardening futuro nao-bloqueante; inconsistencia de criterio nao-bloqueante em 5 das 7 tools sem dominio_rede classificado (sub-entrega 7/N)."
proximo_pacote: "P03 -- aguardando merge da PR #254 (outputSchema/structuredContent para buscar_contato). Depois de mesclada: mais uma fatia pequena de outputSchema para outra tool de baixo risco (candidatos a investigar: tools de leitura simples cujo handler devolva dict cru, nao string serializada -- e a maioria serializa, entao a proxima escolha exige o mesmo levantamento feito aqui), ou a investigacao dedicada de idempotentHint por handler, ou perguntar ao Andre se ele prefere avancar direto para P04 (pedidos duraveis/lease/ledger) dado que o passo 2 do P03 ja esta totalmente fechado e o passo 3 tem duas fatias reais entregues -- a cargo da execucao autonoma agendada, salvo nova prioridade do Andre."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 77c95bf7915573b785752ef012f2cf5458fbd4ad
pacote: "P03 sub-entrega 10/N -- outputSchema/structuredContent (passo 3 do plano), terceira fatia: contrato de dados publicado em tools/list e refletido em tools/call para consultar_lista_compras, apos calculadora (sub-entrega 8/N) e buscar_contato (sub-entrega 9/N)"
estado: pronto_para_revisao
inicio: "2026-09-13T11:20:00Z"
fim: "2026-09-13T12:31:19Z"
arquivos_alterados:
  - "functions/tools/registry.py (nova entrada `_OUTPUT_SCHEMAS['consultar_lista_compras']` -- contrato para as 7 chaves sempre presentes no nivel superior (total/planejados/comprados/filtro/encontrados/retornados/itens) mais `truncado` opcional; item com os 7 campos sempre presentes de `_item_publico` mais `ordem` opcional; `filtro` enum fechado com os 5 valores que `lista_compras._FILTROS` resolve)"
  - "functions/test_output_schema.py (5 testes novos: schema com campos obrigatorios/opcionais corretos, publicacao em tools/list, sucesso com structuredContent igual ao content, filtro invalido -- caminho real de erro, string 'ERRO|...' -- nunca leva structuredContent, e paridade campo a campo contra o schema publicado)"
decisoes:
  - id: p03-sub10-consultar-lista-compras-candidata-outputschema
    motivo: "Candidata escolhida apos levantar no inventario todas as tools LEITURA, sem rede, sem dado sensivel (necessidade_de_rede=False, dados_sensiveis=False): consultar_lista_compras, obter_portal_compras_publico, consultar_elevacoes_sugeridas, consultar_promocoes_autonomia_sugeridas, obter_projeto_bolsas_publico, consultar_pedidos_agente, consultar_execucoes_agente, consultar_politica, simular_politica, preparar_politica, entre outras. `consultar_politica` foi investigada e descartada primeiro: `_consultar_politica` (tools/hermes_tools.py) faz `json.dumps(...)` e devolve STRING, nao dict -- mesmo motivo pelo qual `consultar_saude` foi descartada na sub-entrega 9/N (contrato anunciado nunca teria structuredContent cumprido). `consultar_lista_compras` (backed por tools/lista_compras.py::consultar/_item_publico) foi escolhida por devolver dict cru com forma fixa e por `_item_publico` forcar `str()`/`bool()` em cada campo do item antes de devolver -- garantia de tipo mais forte que a de buscar_contato (que passa campos direto do documento do Firestore sem coercao) na PROPRIA funcao, ainda que nao a mais forte do catalogo (calculadora forca tipo em TODO campo sem excecao; consultar_lista_compras tem uma excecao, o campo opcional `ordem`, sem coercao em _item_publico). As demais candidatas do levantamento nao foram investigadas em profundidade nesta sub-entrega -- ficam como candidatas para a proxima fatia."
    autoridade: existente_ou_nova
  - id: p03-sub10-seis-rodadas-de-revisao-adversarial-sobre-um-comentario
    motivo: "A implementacao executavel (o JSON Schema em si, tipos/required/enum/additionalProperties) nunca mudou apos a 1a rodada -- todas as 5 correcoes subsequentes foram no COMENTARIO explicativo acima de `_OUTPUT_SCHEMAS['consultar_lista_compras']`, sobre quais caminhos de codigo alem de tools/lista_compras.py tambem tocam a colecao Firestore shopping_items (relevante porque `ordem`, unico campo do item sem coercao de tipo em `_item_publico`, depende disso). Rodada 1 (Agent tool, general-purpose, sem contexto): achou que o comentario original chamava tools/lista_compras.py de 'unico ponto de escrita/leitura' da colecao -- falso, tools/telegram_extended.py tambem le/escreve direto (obter_portal_compras_publico/mutar_portal_compras_publico). Corrigido. Rodada 2, sobre a correcao: confirmou a correcao 1 verdadeira, mas achou um overclaiming DIFERENTE -- um comentario em test_output_schema.py dizia que consultar_lista_compras tinha 'a garantia de tipo mais forte das tres' tools, quando calculadora e mais forte (zero excecoes vs. uma). Corrigido para comparacao pairwise precisa. Rodada 3: achou que a correcao 1 citou ERRADO qual duplicacao tools/inventory.py documenta -- atribuiu a duplicacao security_portals.py/tools/telegram_extended.py a uma nota do inventario que na verdade fala de outra coisa (mutar_portal_compras_publico vs. mutar_lista_compras). Corrigido. Rodada 4: achou que a propria contagem 'tres caminhos reais' (ja reescrita duas vezes) ainda estava incompleta -- o FRONTEND web (ShoppingListTool.tsx/index.tsx) tambem escreve na colecao via SDK do Firebase, direto do navegador. Nenhuma tentativa de enumeracao exaustiva resistiu a rodada seguinte achando mais um caminho -- decisao: parar de tentar enumerar todos os caminhos no comentario, reescrever para declarar honestamente que uma auditoria completa esta fora de escopo, que `ordem` foi checado como sempre inteiro so nos caminhos efetivamente inspecionados, e que isso e risco aceito e nao-bloqueante (mesmo tratamento ja dado ao risco equivalente de buscar_contato/perfil_pessoas na sub-entrega 9/N). Rodada 5, sobre essa reescrita: confirmou que a nova redacao nao overclaima mais contagem de caminhos, mas achou uma inconsistencia textual pequena (o historico dizia 'as tres primeiras rodadas', quando na real ja eram quatro rodadas com achado ate ali) -- aproveitada para remover o historico narrativo detalhado do comentario de codigo (nao e o lugar certo para uma narrativa de revisao; fica so a conclusao atual, com referencia a esta PR/entrada de diario para o historico). Rodada 6: nao achou nada -- criterio de parada atingido (escalar so enquanto uma rodada acha algo real)."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "python3 -m venv + pip install -r requirements.txt (ambiente limpo, clonado publicamente via git clone do repositorio)"
    - "python3 -m unittest test_output_schema -v (arquivo isolado)"
    - "python3 -m unittest discover -s . -p 'test_*.py' -q (suite completa, antes -- via git stash -- e depois de cada rodada de correcao)"
  resultados:
    - "Baseline (origin/main antes desta sub-entrega, confirmado via git stash para isolar do working tree local): 1834/1834, 0 falhas, 0 erros -- confirma o numero ja registrado pela sub-entrega 9/N."
    - "Arquivo isolado test_output_schema.py apos a implementacao: 24/24, 0 falhas, 0 erros."
    - "Suite completa apos a implementacao e as 5 rodadas de correcao textual: 1839/1839, 0 falhas, 0 erros, sem regressao (1834 baseline + 5 novos)."
evidencias:
  - "Seis rodadas de revisao adversarial independente (Agent tool, general-purpose, cada uma sem contexto da implementacao ou das rodadas anteriores) -- ver decisoes para o relato completo e honesto de cada achado. Nenhuma rodada encontrou problema na logica executavel do schema (tipos/required/enum/additionalProperties) nem nos testes -- todos os achados foram sobre precisao factual do texto explicativo (overclaiming de quantos caminhos de codigo tocam a colecao shopping_items, e uma citacao errada de qual nota do inventario documenta qual duplicacao)."
  - "Teste de paridade (TestOutputSchema::test_paridade_tres_tools_tem_output_schema_hoje) cobre TODAS as tools reais do catalogo (registry.list_tool_names(), 106 hoje), nao so as tres escolhidas a dedo."
  - "Os 2 arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificacao de hash local (git hash-object) contra o sha retornado pelo Argos -- os 2 batendo de primeira, sem drift de whitespace nem corrupcao."
  - "Sanity check do PR: changed_files=2, additions=248, deletions=19 no retorno de argos_criar_pr_repositorio -- bate exatamente com git diff --stat rodado localmente contra o commit-base (77c95bf) antes de abrir o PR."
  - "PR #256 aberta (https://github.com/andre-martiini/Hermes/pull/256), com o relato completo das 6 rodadas no corpo -- AINDA NAO MESCLADA, aguardando revisao e merge manual do Andre. Esta propria entrada de diario e o 9o arquivo de arquivo (execucao-archive-p03sub6-a-sub7.md) vao numa segunda commit desta mesma branch/PR, apos o codigo+testes."
  - "CONTEXTO OPERACIONAL: o disparo agendado anterior de hoje (13/09/2026, manha) nao conseguiu avancar porque o conector Argos MCP estava indisponivel para aquela sessao (enabledInChat=false) -- ficou registrado so como atualizacao do Blueprint da Autonomia via leitura publica (git clone/git log, sem escrita), sem nenhuma sub-entrega nova. O usuario reativou o Argos e pediu para tentar novamente; esta sessao confirmou o acesso restaurado (ListConnectors -> enabledInChat=true) e seguiu com este trabalho."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "ABERTA: PR #256 aguardando merge do Andre -- esta entrada esta em pronto_para_revisao, nao validado; uma execucao futura desta tarefa agendada deve conferir se foi mesclada (git clone publico + git log/git branch -r) e atualizar estado/evidencias aqui, sem reescrever um bloco ja validado."
  - "PROCESSO, novo (achado indireto das rodadas 4-5 de revisao adversarial desta sub-entrega): um comentario de codigo que tenta enumerar EXAUSTIVAMENTE todos os caminhos que tocam um recurso compartilhado (ex.: uma colecao Firestore) e uma armadilha -- cada tentativa de fechar a lista foi refutada pela rodada seguinte achando mais um caminho (2 reescritas, 3 caminhos descobertos ao longo do processo: tools/telegram_extended.py, security_portals.py, frontend web). A partir desta sub-entrega, quando um comentario precisar registrar que um recurso tem OUTROS escritores alem do investigado, a redacao correta e declarar isso como fato conhecido e nao-exaustivo (dar 1-2 exemplos concretos, dizer explicitamente que uma auditoria completa esta fora de escopo) em vez de tentar contar/nomear todos -- mesmo espirito ja usado para pendencias tipo 'ha ~10 pontos de escrita, nenhum auditado' (buscar_contato, sub-entrega 9/N), que nunca tentou ser uma lista fechada e por isso nunca precisou ser corrigida por contagem incompleta."
  - "PROCESSO, novo: uma narrativa detalhada rodada-a-rodada de revisao adversarial NAO deve morar dentro de um comentario de codigo permanente -- e material de PR body/diario, nao de fonte. Tentar manter as duas coisas sincronizadas (o comentario tentando resumir seu proprio historico de correcao) e o que gerou a inconsistencia '3 vs 4 rodadas' que a rodada 5 encontrou. O comentario final em tools/registry.py ficou só com a CONCLUSAO atual mais uma referencia a esta PR/entrada para o historico -- nao com o historico embutido."
  - "ABERTA, nova, NAO-bloqueante (aceita conscientemente, ver decisoes): o campo `ordem` de cada item de consultar_lista_compras nao tem coercao de tipo em `_item_publico`, e a colecao shopping_items tem pelo menos 3 outros escritores conhecidos (tools/telegram_extended.py, security_portals.py, frontend web) alem de tools/lista_compras.py -- nenhum dos inspecionados grava `ordem` hoje, mas isso nao e uma auditoria completa da colecao. Mesma categoria e mesmo tratamento do risco de tipo de buscar_contato/perfil_pessoas (sub-entrega 9/N)."
  - "ABERTA, deliberadamente: outputSchema para as demais ~103 tools do catalogo continua fora de escopo -- candidatas ja levantadas nesta sub-entrega e ainda nao investigadas em profundidade: obter_portal_compras_publico, consultar_elevacoes_sugeridas, consultar_promocoes_autonomia_sugeridas, obter_projeto_bolsas_publico, consultar_pedidos_agente, consultar_execucoes_agente, simular_politica, preparar_politica. `consultar_politica` INVESTIGADA E DESCARTADA (handler serializa para string via json.dumps antes de devolver -- mesmo motivo de consultar_saude na sub-entrega 9/N)."
  - "ABERTA, deliberadamente (herdada da sub-entrega 7/N): idempotentHint continua fora de escopo -- precisa de investigacao dedicada por HANDLER, nenhum campo do inventario atual registra isso."
  - "ABERTA: a fatia `envelope` do passo 3 do plano (alem de outputSchema/structuredContent/annotations, ja cobertos em parte) nao foi investigada nesta sub-entrega."
  - "Pendencias ja registradas em blocos anteriores e nao tocadas por esta sub-entrega continuam abertas: religar inventario tipado (P03 sub-entrega 1/N) a decisao de politica real; ambiguidades de classificacao (gerar_relatorio, salvar_memoria_global); card do Telegram de rascunho degradado nao reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore nao configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupcao silenciosa em escritas grandes via Argos; passo 2 do P02 (OAuth claims/scopes) como hardening futuro nao-bloqueante; inconsistencia de criterio nao-bloqueante em 5 das 7 tools sem dominio_rede classificado (sub-entrega 7/N); estrutura de _item_publico de mutar_portal_compras_publico/security_portals.py duplicada com mutar_lista_compras (achado ja documentado em tools/inventory.py antes desta sub-entrega, nao criado por ela)."
proximo_pacote: "P03 -- aguardando merge da PR #256 (outputSchema/structuredContent para consultar_lista_compras). Depois de mesclada: mais uma fatia pequena de outputSchema para uma das candidatas ja levantadas (obter_portal_compras_publico, consultar_elevacoes_sugeridas, consultar_promocoes_autonomia_sugeridas, obter_projeto_bolsas_publico, consultar_pedidos_agente, consultar_execucoes_agente -- cada uma exige o mesmo levantamento de forma real do handler feito aqui), ou a investigacao dedicada de idempotentHint por handler, ou perguntar ao Andre se prefere avancar direto para P04 (pedidos duraveis/lease/ledger) dado que o passo 2 do P03 ja esta totalmente fechado e o passo 3 tem tres fatias reais entregues -- a cargo da execucao autonoma agendada, salvo nova prioridade do Andre."
```
