# Hermes: Vision And Boundaries

## 1. Contexto

O Hermes atual já combina:

- gestão de tarefas e projetos;
- integração com Firebase e Google;
- captura de insumos como arquivos, áudio, WhatsApp e documentos;
- bases RAG personalizadas e vetorização;
- fluxos experimentais de operações autônomas.

Essa base é útil, mas ainda não constitui uma plataforma de agentes madura. O objetivo agora é evoluir o Hermes sem transformar o sistema em um monólito mais complexo e menos governável.

## 2. Missão do Hermes

O Hermes deve atuar como um orquestrador confiável para:

- receber insumos multimodais;
- estruturar e preservar contexto com proveniência;
- recuperar contexto útil por domínio e tarefa;
- propor planos, artefatos e ações;
- executar apenas o que estiver homologado e autorizado;
- aprender com histórico validado e correções humanas.

## 3. Princípios Arquiteturais

### 3.1 Orquestração acima de execução

O Hermes não deve concentrar toda a lógica em um único runtime ou arquivo. Sua função principal é:

- entender a demanda;
- compor contexto;
- selecionar caminho de decisão;
- delegar para executor, ferramenta ou agente adequado;
- registrar rastros da operação.

### 3.2 Memória com proveniência

Memória não é wiki linear. Toda informação reutilizável deve carregar:

- fonte;
- momento de captura;
- versão;
- vínculo com domínio;
- confiança;
- relação com eventos e artefatos derivados.

### 3.3 Autonomia graduada

Autonomia é função de:

- clareza da demanda;
- suficiência do contexto recuperado;
- impacto potencial;
- escopo de permissão.

### 3.4 Ferramentas homologadas

Nenhuma ação externa deve nascer de “descoberta improvisada” em tempo de execução. Toda ferramenta deve existir em catálogo local com:

- contrato de entrada;
- contrato de saída;
- escopo de permissão;
- política de erro;
- política de auditoria.

### 3.5 Separação entre cérebro e musculatura

O Hermes não deve confundir:

- memória;
- política;
- roteamento;
- execução;
- automação.

Essas responsabilidades são complementares, mas distintas.

## 4. Domínios Iniciais

Os domínios iniciais do Hermes devem ser limitados aos contextos já mais próximos da realidade do repositório:

1. `operacoes_administrativas`
2. `sistemas_e_codigo`
3. `captura_e_conhecimento`

Esses domínios são suficientes para validar ingestão, memória, governança e execução controlada sem abrir escopo excessivo.

## 5. Capacidades Nativas x Integradas

### 5.1 Devem permanecer nativas no Hermes

- roteamento de demanda;
- composição de contexto;
- política de risco e aprovação;
- catálogo de ferramentas homologadas;
- memória canônica e metadados;
- auditoria de decisão e execução;
- geração de pacotes de trabalho para agentes externos.

### 5.2 Podem ser delegadas para serviços e automações

- transcrição;
- parsing documental;
- extração estruturada;
- listeners e gatilhos;
- automações determinísticas;
- execução especializada em ambiente dedicado.

## 6. Camadas-alvo

### Camada A: Intake

Recebe insumos e produz um `IntakeRecord` canônico.

### Camada B: Preparation

Normaliza, extrai, deriva e preserva original e derivados.

### Camada C: Memory

Armazena documentos, eventos, entidades, relações, artefatos e trilhas.

### Camada D: Orchestration

Classifica demanda, recupera contexto, calcula risco e escolhe rota.

### Camada E: Execution

Aciona ferramenta homologada, fluxo automatizado ou agente especializado.

### Camada F: Governance

Registra decisões, fontes, permissões, auditoria e feedback humano.

## 7. Boundaries Arquiteturais

### 7.1 O que o Hermes é

- um sistema de coordenação cognitiva e operacional;
- um runtime de decisão com memória e política;
- um ponto único de governança sobre agentes e ferramentas.

### 7.2 O que o Hermes não é

- apenas um chat com contexto;
- apenas um RAG;
- apenas um catálogo de automações;
- apenas um sistema de tarefas;
- apenas um wrapper de n8n;
- apenas um executor de código.

## 8. Anti-Objetivos

Para evitar regressões arquiteturais, o Hermes não deve:

- expandir a lógica central em arquivos gigantes com múltiplas responsabilidades;
- criar novos fluxos sem contrato de entrada e saída;
- acoplar política de risco à UI;
- usar memória sem proveniência;
- executar ações externas fora do catálogo homologado;
- importar integralmente arquiteturas de repositórios auxiliares sem curadoria.

## 9. Decisão Estrutural

O Hermes adotará como base:

- `claude-mem` como referência para observabilidade, progressive disclosure, corpus e contexto persistente;
- `LightRAG` como referência para evolução do RAG relacional e grafo;
- `My-Brain-Is-Full-Crew` como referência para despacho por papéis;
- `rtk` como referência para governança de runtime e disciplina operacional;
- `n8n` como executor/automação homologada, não como núcleo cognitivo.

Essa combinação é de padrões, não de importação literal de runtime.
