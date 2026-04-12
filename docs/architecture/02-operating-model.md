# Hermes Operating Model

## 1. Objetivo

Definir o modelo canônico mínimo para permitir ingestão, memória, roteamento, governança e execução sem ambiguidade estrutural.

## 2. Fonte de Verdade

O Hermes deve tratar os dados em quatro níveis:

1. `source artifact`
2. `derived artifact`
3. `operational record`
4. `knowledge object`

### 2.1 Source Artifact

Representa o material original recebido.

Exemplos:

- áudio bruto;
- PDF original;
- mensagem de WhatsApp;
- arquivo de repositório;
- URL capturada.

### 2.2 Derived Artifact

Representa uma transformação do original.

Exemplos:

- transcrição;
- markdown extraído;
- JSON estruturado;
- chunk;
- resumo;
- diff;
- minuta.

### 2.3 Operational Record

Representa um evento de trabalho do Hermes.

Exemplos:

- entrada registrada;
- ferramenta executada;
- aprovação pedida;
- aprovação concedida;
- patch proposto;
- minuta revisada.

### 2.4 Knowledge Object

Representa conhecimento estabilizado e reutilizável.

Exemplos:

- norma;
- POP;
- decisão;
- entidade de domínio;
- contexto técnico consolidado;
- procedimento validado.

## 3. Entidades Canônicas

### 3.1 IntakeRecord

Pacote mínimo visto pelo Hermes ao receber qualquer insumo.

Campos mínimos:

- `id`
- `received_at`
- `channel`
- `domain_hint`
- `confidentiality`
- `source_artifact_ids`
- `request_text`
- `requested_by`
- `processing_status`

### 3.2 Artifact

Representa original ou derivado.

Campos mínimos:

- `id`
- `artifact_type`
- `origin_type`
- `mime_type`
- `title`
- `storage_ref`
- `checksum`
- `created_at`
- `source_artifact_id`
- `derivation_kind`
- `version`
- `provenance`

### 3.3 KnowledgeNode

Representa objeto de conhecimento reutilizável.

Campos mínimos:

- `id`
- `node_type`
- `canonical_title`
- `domain`
- `status`
- `confidence`
- `valid_from`
- `valid_until`
- `source_refs`
- `version_of`
- `current_version`

### 3.4 KnowledgeEdge

Representa relação explícita entre nós.

Tipos iniciais:

- `depends_on`
- `supersedes`
- `derived_from`
- `approved_by`
- `used_in`
- `related_to`
- `applies_to`
- `produces`

Campos mínimos:

- `id`
- `from_id`
- `to_id`
- `edge_type`
- `confidence`
- `evidence_refs`
- `created_at`

### 3.5 Procedure

Representa POP executável e versionado.

Campos mínimos:

- `id`
- `name`
- `domain`
- `trigger_conditions`
- `preconditions`
- `states`
- `transitions`
- `required_artifacts`
- `approval_policy`
- `version`
- `status`

### 3.6 ToolDefinition

Representa ferramenta homologada.

Campos mínimos:

- `id`
- `canonical_name`
- `executor_type`
- `input_schema_ref`
- `output_schema_ref`
- `permissions`
- `impact_level`
- `timeout_ms`
- `error_policy`
- `audit_level`
- `enabled`

### 3.7 DecisionRecord

Representa decisão tomada pelo Hermes em uma demanda.

Campos mínimos:

- `id`
- `intake_id`
- `decision_type`
- `route`
- `clarity_score`
- `context_score`
- `impact_score`
- `approval_required`
- `reasoning_summary`
- `context_refs`
- `created_at`

### 3.8 ExecutionRecord

Representa uma execução concreta.

Campos mínimos:

- `id`
- `decision_id`
- `executor`
- `tool_id`
- `procedure_id`
- `status`
- `started_at`
- `finished_at`
- `input_ref`
- `output_ref`
- `error_ref`

## 4. Eventos Canônicos

O Hermes deve operar orientado a eventos explícitos.

Eventos mínimos:

1. `intake_received`
2. `artifact_registered`
3. `artifact_derived`
4. `knowledge_promoted`
5. `context_retrieved`
6. `decision_made`
7. `approval_requested`
8. `approval_resolved`
9. `execution_started`
10. `execution_completed`
11. `execution_failed`
12. `feedback_applied`

## 5. Proveniência

Toda informação reaproveitável deve manter a cadeia:

- de onde veio;
- por qual transformação passou;
- por qual ferramenta ou agente foi produzida;
- quem aprovou ou corrigiu;
- qual versão está vigente.

Sem isso, o objeto não deve ser promovido para memória estável.

## 6. Versionamento

### 6.1 Regra geral

Objetos reutilizáveis não são sobrescritos silenciosamente. Eles:

- criam nova versão;
- mantêm vínculo com a versão anterior;
- registram motivo da substituição;
- preservam histórico de vigência.

### 6.2 Aplicação

- documentos derivados podem ser sobrescritos tecnicamente, desde que a trilha de derivação seja preservada;
- knowledge nodes, procedures e policy objects devem ser versionados semanticamente.

## 7. Ordem de Evolução da Memória

### 7.1 Etapa inicial

Memória documental versionada, com:

- artifacts;
- intake records;
- decision records;
- execution records;
- knowledge nodes simples.

### 7.2 Etapa posterior

Camada de relações explícitas e consulta relacional/grafo com:

- edges;
- vigência temporal;
- inferência limitada;
- exploração contextual mais rica.

## 8. Decisão de Fonte Primária

No curto prazo, a memória primária do Hermes deve ser:

- documental;
- versionada;
- com proveniência forte.

O grafo entra como camada de enriquecimento e recuperação avançada, não como requisito de início para toda a plataforma.
