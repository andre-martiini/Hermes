# Arquivo: P07 sub-entrega 13/N (movida de execucao.md em 2026-10-25, sem alteração de conteúdo)

```yaml
pacote: "P07 sub-entrega 13/N -- captura de media.filename: services/whatsapp-capture/nome_arquivo.js (nomeArquivoMidia) e captureMedia (index.js) passam a gravar media.filename (nome do documento do whatsapp-web.js; aparado, sem controles C0/C1, marcas bidi e invisíveis, substituto solto -> U+FFFD, máx. 255 pontos de código; vazio/ausente = campo omitido). Permite à sombra de cumprimento (sub 11) conferir o objeto prometido contra o nome do anexo e medir o A06 real. Só novas capturas e o reparo de mídia; sem mudança Python, sem flag nova (campo aditivo)."
estado: validado
inicio: "2026-10-24T17:00:00Z"
fim: "2026-10-24T17:40:00Z"
decisoes:
  - id: p07-sub13-triagem
    motivo: "Nenhuma PR aberta no início do disparo das 14h BRT; nenhuma execução paralela da linha de autonomia."
  - id: p07-sub13-arquivo-execucao
    motivo: "execucao.md arquivado (bloco P07 sub 10 -> execucao-archive-p07sub10.md)."
  - id: p07-sub13-limitacoes
    motivo: "Aceitas: mensagens de documento já gravadas com storage_path não ganham filename (reparo só olha as sem storage_path; backfill do histórico não coberto); truncamento por ponto de código pode cortar combinante (>255 chars, cosmético)."
testes:
  resultados:
    - "functions/ completo ANTES 4636 OK (main atual; Python intocado); DEPOIS 4636 OK. services/whatsapp-capture: nome_arquivo_test 5 OK (novo)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): sem defeito de escrita no Firestore, perda de mensagem ou regressão no reparo; apontou higiene (substituto solto, marcas bidi/invisíveis fora de C0) -> corrigido com 1 teste novo. Rodada 2 não feita (correção de uma regex pura, coberta por teste)."
pendencias:
  - "P07: ligar as 3 sombras (extração, cumprimento, follow-up) só com aval do André e medir precisão com dados reais antes de qualquer fechamento automático; revisão final do pacote para pacote_concluido: P07."
```
