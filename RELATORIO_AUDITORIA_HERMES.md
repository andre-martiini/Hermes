# Relatório de Auditoria: Sistema Hermes

Este relatório detalha a auditoria arquitetural e funcional do sistema de gestão Hermes, com ênfase em identificar oportunidades para automação avançada e integração preditiva com inteligência artificial, alinhando-se aos paradigmas modernos de engenharia e ecossistema TypeScript/React.

## Arquitetura Atual

A arquitetura atual do Hermes apresenta-se como um sistema híbrido e distribuído, que integra múltiplas tecnologias para atender às suas necessidades de gestão de tarefas, conhecimento, automação e integrações:

*   **Frontend (Cliente):** Aplicação Single-Page Application (SPA) desenvolvida em **React** com **TypeScript**. Utiliza Vite como bundler e tailwindcss para estilização. O gerenciamento de estado é predominantemente local nos componentes, com forte acoplamento ao Firebase para persistência em tempo real.
*   **Backend (Serverless):** O principal motor de sincronização (ex: integração com Google Tasks, e-mail) e lógica de negócios pesada reside no **Firebase Cloud Functions**, implementado primariamente em **Python** (`functions/main.py`, `functions/hermes_core_logic.py`). Existe também uma parte legada/secundária em Node.js (`functions_node/index.js`), usada para integrações específicas (ex: Puppeteer).
*   **Banco de Dados:** **Firestore (Firebase)** atua como a única fonte de verdade e mecanismo de comunicação em tempo real entre o cliente e os processos em background.
*   **Automação Local (RPA):** Um subsistema de automação local (`automations/server.py`) expõe uma API FastAPI para acionar scripts Python locais que interagem com sistemas do governo (PGD, SIGRH) utilizando Web Scraping / RPA via Selenium (ex: `execucao_pgd.py`, `emissor_nfse.py`).
*   **Copiloto/Bot:** Existe uma integração robusta via Telegram (`Hermes-Bot`), que orquestra a comunicação do usuário com o sistema, delegando tarefas para uma lógica centralizada (`hermes_core_logic.py`) que usa o Gemini LLM para interpretação de intenções.

## Gargalos Identificados

A auditoria revelou pontos de fricção e ineficiências técnicas na operação do sistema:

1.  **Acoplamento em RPA Local:** A dependência de scripts Selenium locais (`automations/`) para tarefas rotineiras (como emissão de NFS-e ou registro de PGD) cria um ponto único de falha. Exige um ambiente de execução (máquina do usuário ou VM dedicada) configurado, dificultando a migração 100% para a nuvem.
2.  **Sincronicidade Forçada no Front-End:** Certos fluxos dependem de ações manuais do usuário na interface React para disparar sincronizações ou invocar ferramentas, quando poderiam ser reativos baseados em eventos do Firestore.
3.  **Fragmentação do Backend:** A coexistência de lógicas de negócio em Cloud Functions (Python), Cloud Functions (Node.js) e servidor FastAPI local (Python) dificulta a manutenibilidade, o rastreamento de erros e a orquestração de fluxos complexos em caso de falhas transitórias.
4.  **Integração LLM Acoplada:** A interação com o modelo Gemini está codificada rigidamente nas Cloud Functions (ex: `hermes_core_logic.py`). A falta de uma interface padronizada, como o Model Context Protocol (MCP), limita a expansão para novos modelos, o uso de ferramentas complexas pelo LLM e o reaproveitamento de contextos em diferentes partes do sistema (Dashboard vs Telegram).
5.  **Processamento Lote Ineficiente:** Algumas sincronizações de grandes volumes de dados de ferramentas de terceiros dependem de timers (CRON) no Cloud Functions ou cliques do usuário, sem uma fila de mensagens (como Cloud Tasks) para garantir resiliência, retry backoff, e controle de concorrência.

## Propostas de Automação

Para transformar as rotinas estáticas em fluxos resilientes e escaláveis, propõe-se:

1.  **Migração RPA para Cloud via n8n:**
    *   Substituir os scripts locais que não necessitam estritamente de ambiente desktop pelo **n8n** hospedado em nuvem.
    *   Criar fluxos no n8n (Webhooks) que são chamados pelo Firebase, abstraindo a lógica de chamadas HTTP, parsing de PDFs (ex: faturas) e integração com APIs não-oficiais.
2.  **Web Scraping Headless Serverless:**
    *   Para as tarefas de scraping irredutíveis (como o PGD), portar o código do Selenium para bibliotecas como Playwright e encapsular em um contêiner no **Google Cloud Run**. Isso remove a dependência do servidor FastAPI (`automations/server.py`) e viabiliza execução sob demanda.
3.  **Arquitetura Reativa (Event-Driven):**
    *   Aproveitar extensivamente os triggers do Firestore (`onWrite`, `onCreate`) no Cloud Functions. A UI em React deve limitar-se a criar registros de "intenção" (ex: `fila_emissao_nfse`), deixando o backend assíncrono processar, interagir com serviços externos (n8n/Cloud Run) e atualizar o status do documento.
4.  **Pub/Sub e Cloud Tasks:**
    *   Implementar filas do Google Cloud Tasks para garantir execução de automações sensíveis (como disparos de e-mail e geração de relatórios) com controle de limite de taxa e políticas de repetição, resolvendo o gargalo de processamento em lote.

## Propostas de Inteligência Artificial (com MCP)

A modernização com IA visa transformar o Hermes de um sistema reativo para um assistente preditivo e autônomo:

1.  **Adoção do Model Context Protocol (MCP):**
    *   **Abstração de Ferramentas:** Implementar um servidor MCP intermediário em Node.js ou Python que encapsule as capacidades do Hermes (ler tarefas, atualizar projetos, buscar base de conhecimento, chamar automações).
    *   **Cliente Flexível:** O Hermes Copilot (atualmente no Telegram e na Web) se conectará ao servidor via protocolo MCP. O LLM (Gemini ou Qwen) usará as ferramentas MCP padronizadas, eliminando a codificação manual de "tool calls" nas Cloud Functions e habilitando o uso de múltiplos agentes.
2.  **Categorização e Triagem Preditiva:**
    *   Um agente rodando assincronamente intercepta novas tarefas criadas (via UI ou e-mail/WhatsApp). Utilizando as ferramentas via MCP e RAG (Retrieval-Augmented Generation) sobre o projeto/histórico, ele sugere ou atribui automaticamente Categorias (ex: [CLC], [GERAL]), Prioridades e Prazos baseados em padrões anteriores, alertando o usuário via notificação para revisão rápida no Dashboard.
3.  **Geração Autônoma de Relatórios e Diários de Bordo:**
    *   Através da integração MCP com a agenda (Google Calendar) e as Tarefas Concluídas, um agente IA formula o "Diário de Bordo" e relatórios de progresso no final de cada ciclo, atualizando os campos de "Notas" ou criando registros no módulo de Serviços sem intervenção direta.
4.  **Avaliação Contínua e "Self-Healing":**
    *   O agente LLM analisa periodicamente os logs de falha das automações RPA/n8n. Com base nos erros mapeados na "Base de Conhecimento", ele tenta classificar a causa raiz e, se permitido, modificar parâmetros do sistema (ex: limpar cache, tentar outra credencial), documentando a ação.

## Roadmap de Implementação

A aplicação das propostas será executada de forma iterativa, mitigando o risco de instabilidade:

*   **Fase 1: Preparação e Abstração (Mês 1)**
    *   **Ação:** Criar o barramento assíncrono básico. Substituir invocações diretas ao servidor FastAPI (RPA local) por um fluxo de "Filas" via Firestore, onde o servidor local escuta o banco em vez de receber chamadas HTTP diretas.
    *   **Impacto:** Permite escalar ou migrar o RPA no futuro sem alterar o código React, mantendo a compatibilidade estrita.
*   **Fase 2: Infraestrutura MCP e Integração LLM (Mês 2-3)**
    *   **Ação:** Desenvolver o "Hermes MCP Server" encapsulando 2 a 3 ferramentas principais (Ex: CRUD de Tarefas e Busca de RAG).
    *   **Ação:** Refatorar a Cloud Function `hermes_core_logic.py` para atuar como um "MCP Client", delegando a execução das funções ao padrão aberto, desacoplando o bot do Telegram da lógica interna.
*   **Fase 3: Automação Preditiva e Cloud Run (Mês 4)**
    *   **Ação:** Desativar gradualmente scripts do `automations/` movendo-os para contêineres independentes no Google Cloud Run acionados por Cloud Tasks, ou substituindo integrações diretas por fluxos via **n8n**.
    *   **Ação:** Ativar o agente de "Triagem Preditiva" rodando silenciosamente e sinalizando tarefas categorizadas para revisão do usuário (`necessita_revisao: true`).
*   **Fase 4: Consolidação Autônoma (Mês 5)**
    *   **Ação:** O usuário aprova a remoção das intervenções manuais. O bot passa a executar geração de relatórios e diários via MCP de forma autônoma (via Cron do Firestore), notificando apenas o resultado final na interface React.