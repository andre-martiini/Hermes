# Governance, Risk And Tooling

## 1. Objetivo

Definir a política inicial de autonomia, validação, ferramentas homologadas e responsabilidades de execução.

## 2. Policy Engine

Toda demanda deve ser avaliada por um motor de política com três eixos:

- `clarity_score`
- `context_score`
- `impact_score`

Esses eixos não substituem regras duras. Eles são combinados com regras obrigatórias de bloqueio.

## 3. Modos de Ação

### 3.1 Ação automática

Permitida para:

- ingestão;
- transcrição;
- extração;
- conversão;
- classificação;
- indexação;
- síntese interna sem efeito externo.

### 3.2 Confirmação curta

Necessária para:

- geração de artefato interno importante;
- roteamento com ambiguidade moderada;
- execução com contexto bom, porém incompleto;
- propostas operacionais sem efeito externo imediato.

### 3.3 Aprovação obrigatória

Necessária para:

- envios oficiais;
- comunicação institucional;
- abertura de PR;
- alterações persistentes em sistemas externos;
- exclusões;
- execução de alto impacto;
- execução com baixa confiança;
- ações em domínio sensível.

## 4. Regras Duras de Bloqueio

Independentemente do score, o Hermes deve bloquear execução automática quando houver:

- operação destrutiva;
- escrita externa sem homologação;
- mudança de código fora de ambiente controlado;
- ausência de fonte mínima;
- ausência de trilha de auditoria;
- conflito entre contexto recuperado e política vigente.

## 5. Tool Registry

Toda ferramenta homologada deve possuir registro local com:

- `canonical_name`
- `purpose`
- `executor_type`
- `input_schema`
- `output_schema`
- `permissions`
- `impact_level`
- `timeout_ms`
- `observability_requirements`
- `error_policy`
- `approval_mode`

## 6. Tipos de Executor

### 6.1 Native

Executado no próprio Hermes.

Uso indicado:

- validações leves;
- transforms pequenos;
- roteamento;
- montagem de pacotes;
- operações de baixo risco.

### 6.2 Automation

Executado por fluxo externo homologado, como n8n.

Uso indicado:

- ETL;
- parsing;
- listeners;
- conversão estruturada;
- integrações determinísticas.

### 6.3 Specialist Agent

Executado por agente especializado.

Uso indicado:

- análise técnica;
- síntese mais complexa;
- propostas estruturadas;
- geração de patch;
- adaptação contextual de procedimento.

## 7. Papel do n8n

O n8n deve operar como camada de automação homologada, não como centro de decisão.

### 7.1 O que faz sentido no n8n

- pdf para markdown lógico;
- áudio para texto estruturado;
- documento/url/imagem para JSON;
- listeners de repositório;
- gatilhos de atualização incremental;
- pipelines de captura.

### 7.2 O que não deve migrar para o n8n

- decisão de risco;
- política de aprovação;
- composição cognitiva de contexto;
- seleção final de executor;
- promoção de conhecimento sem validação arquitetural.

## 8. Catálogo Inicial de Ferramentas

### T-001 `audio_transcribe_structured`

- executor: `automation`
- impacto: `low`
- aprovação: `automatic`

### T-002 `pdf_to_markdown_logical`

- executor: `automation`
- impacto: `low`
- aprovação: `automatic`

### T-003 `content_to_schema_json`

- executor: `automation`
- impacto: `medium`
- aprovação: `automatic`

### T-004 `url_to_clean_markdown`

- executor: `automation`
- impacto: `low`
- aprovação: `automatic`

### T-005 `repository_change_listener`

- executor: `automation`
- impacto: `medium`
- aprovação: `automatic`

### T-006 `code_issue_packet_builder`

- executor: `native`
- impacto: `medium`
- aprovação: `short_confirmation`

### T-007 `specialist_code_patch_proposal`

- executor: `specialist_agent`
- impacto: `high`
- aprovação: `mandatory`

### T-008 `procedure_minuta_generator`

- executor: `specialist_agent`
- impacto: `high`
- aprovação: `mandatory`

## 9. Auditoria

Toda ação relevante deve gerar:

- referência da demanda;
- contexto usado;
- ferramentas acionadas;
- parâmetros principais;
- artefatos produzidos;
- resultado;
- erro, se houver;
- decisão de aprovação associada.

## 10. Feedback e Aprendizado

Feedback humano não deve sobrescrever o histórico bruto. Ele deve gerar:

- `feedback_applied`;
- nova versão de procedimento, minuta ou knowledge node;
- aumento ou redução de confiança;
- eventual atualização de policy ou POP.

## 11. Regra de Implantação

Nenhuma nova integração deve entrar no Hermes sem:

1. definição de executor;
2. schema de entrada;
3. schema de saída;
4. política de erro;
5. política de aprovação;
6. política de auditoria.
