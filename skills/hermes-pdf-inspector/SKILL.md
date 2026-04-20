---
name: hermes-pdf-inspector
description: Integrar o pdf-inspector aos fluxos locais de PDF do Hermes com roteamento entre Markdown estrutural e OCR seletivo. Use quando Codex precisar preparar ou ajustar ingestao de PDFs no copiloto Hermes, no Diario de Bordo ou na ingestao comum, especialmente para preservar tabelas financeiras, detectar encoding quebrado e reduzir dependencia de OCR integral.
---

# Hermes PDF Inspector

Usar esta skill para transformar `pdf-inspector` em um motor local de extração de precisão para o Hermes.

Preferir esta skill quando o objetivo for:

- extrair Markdown de PDFs textuais com melhor preservação de tabelas e colunas;
- decidir quando usar OCR somente em páginas necessárias;
- evitar texto corrompido por fontes `Identity-H` ou encoding quebrado;
- preparar integração local antes de mexer nos fluxos maiores do `functions/main.py`.

## Fluxo

1. Instalar o runtime local com `python skills/hermes-pdf-inspector/scripts/install_pdf_inspector.py`.
2. Usar `automations/pdf_precision_engine.py` como wrapper padrão.
3. Chamar `process_pdf_with_precision(...)` passando um caminho local de PDF.
4. Respeitar a ação retornada:
   - `use_local_markdown`: usar apenas o Markdown local.
   - `hybrid_merge`: usar Markdown local e mandar só `ocr_required_pages` para OCR visual.
   - `force_full_ocr`: descartar o texto local por problema de encoding.
   - `fallback_to_gemini`: usar pipeline atual quando o motor local falhar.

## Regras de Integração

- Não assumir WhatsApp. Os pontos de entrada corretos são copiloto, Diário de Bordo e ingestão comum.
- Não usar `asyncio.create_subprocess_shell` para montar comando com string. Usar `create_subprocess_exec`.
- Tratar `pagesNeedingOcr` como páginas `0-indexed`.
- Só fazer merge híbrido quando houver páginas pendentes de OCR. PDF textual puro deve virar `use_local_markdown`.
- Se `hasEncodingIssues` vier verdadeiro, descartar o texto local inteiro.
- Manter fallback para o pipeline atual do Hermes enquanto a integração não estiver fechada.

## Pontos do Repositório

- Ler [integration-notes.md](references/integration-notes.md) antes de tocar nos fluxos reais.
- Usar `setup_bot.bat` para preparar o runtime local do motor.

