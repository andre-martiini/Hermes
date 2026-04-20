# Integration Notes

## Onde o Hermes toca PDF hoje

- `functions/main.py:2343` em `vectorizeKnowledgeItemCallable`: extrai PDF com `pdfplumber` antes de gravar `texto_bruto` e vetor.
- `functions/main.py:2786` em `processExtraContextFile`: extrai PDF com `pdfplumber` para contexto extra.
- `functions/main.py:6159` em `askCopilotoHermes`: já existe uma trilha de ingestão documental para anexos do copiloto com `driveFileId`, hoje centrada em Gemini File API.
- `functions/knowledge_graph.py`: o Diário de Bordo e outras referências acabam convergindo para `indice_artefatos`, então o motor local deve produzir texto limpo o bastante para esse índice.

## Ajustes no plano original

### 1. Canal de entrada

Descartar a hipótese de WhatsApp. O skill deve servir para:

- upload no copiloto Hermes;
- anexos ou referências absorvidas pelo Diário de Bordo;
- ingestão comum de arquivos em `conhecimento`.

### 2. Instalação

Não depender de “download de binário de assets” como premissa principal.

Motivos:

- o repositório upstream documenta a CLI e as bindings, mas a estratégia mais estável para o Hermes local é instalar o pacote `@firecrawl/pdf-inspector` pinado em versão;
- isso evita acoplamento a nomes de artefatos de CI;
- em Windows o pacote npm validado localmente funciona com a CLI `pdf-inspector`.

### 3. Wrapper

Preferir um wrapper Python que invoque o script `bin/pdf-inspector.mjs` via `node`.

Motivos:

- evita dependência de `.cmd` no Windows;
- evita shell quoting frágil;
- mantém o consumo assíncrono e seguro com `create_subprocess_exec`.

### 4. Decisão de roteamento

Usar estas regras:

- `hasEncodingIssues=true` -> `force_full_ocr`
- `pdfType in {Scanned, ImageBased}` -> `fallback_to_gemini`
- `pagesNeedingOcr != []` -> `hybrid_merge`
- caso contrário -> `use_local_markdown`

## O que ainda não foi ligado automaticamente

- O skill prepara o runtime local e o wrapper.
- A conexão direta com `functions/main.py` foi deixada desacoplada de propósito, porque esses fluxos hoje misturam execução local e cloud e precisam de escolha explícita de ponto de integração antes de embutir dependência nova.

