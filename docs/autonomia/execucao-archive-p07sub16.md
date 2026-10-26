# Arquivo: P07 sub-entrega 16/N (movida de execucao.md em 2026-10-26, sem alteração de conteúdo)

```yaml
pacote: "P07 sub-entrega 16/N -- wiring em sombra do passo 4 (prazo expresso x estimativa de acompanhamento): followup_compromissos_sombra.registrar passa a chamar autonomy.prazo_followup.planejar_acompanhamento (que não tinha chamador em produção) e grava no resumo acompanhamento_origem/verificar_em/amostra e acompanhamento_delta_horas contra o vence_em fixo do fluxo antigo. Histórico de horas de resposta do dono derivado das últimas 200 mensagens do chat (horas_de_resposta). Mesma flag da sombra de follow-up (padrão DESLIGADO); só números e datas, nunca texto; falha vira acompanhamento_erro sem derrubar a sombra."
estado: validado
inicio: "2026-10-25T16:45:00Z"
fim: "2026-10-25T17:30:00Z"
decisoes:
  - id: p07-sub16-triagem
    motivo: "Nenhuma PR aberta no início do disparo das 14h BRT; nenhuma execução paralela da linha de autonomia. Revisão final do P07 achou o passo 4 (prazo_followup) sem chamador: a revisão final anterior (revogada) não cobria isso; pacote_concluido: P07 segue pendente."
  - id: p07-sub16-sem-prazo-expresso
    motivo: "A sombra planeja com prazo=None (estimativa); o prazo expresso da extração estruturada ainda não é lido aqui. Limitação declarada."
  - id: p07-sub16-bot-no-historico
    motivo: "Respostas do bot saem como from_me e o registro que as identifica expira em 6h, então não dá para filtrá-las no histórico (e filtrar geraria até 200 leituras por promessa). Latências < 2 min são tratadas como automáticas; respostas do bot mais lentas contaminam a amostra para baixo (piso de 1 h limita)."
  - id: p07-sub16-arquivo
    motivo: "execucao.md em 49523 bytes: bloco P07 sub 13 arquivado em execucao-archive-p07sub13.md."
testes:
  resultados:
    - "functions/ completo ANTES 4652 OK (diário); DEPOIS 4657 OK (+5 em test_followup_compromissos_sombra)."
revisao_adversarial:
  - "Rodada 1: 1 achado real (respostas do bot contavam como do dono) -> correção. Rodada 2 sobre a correção: 2 achados reais (filtro só vale 6h; leituras sequenciais por mensagem) -> filtro trocado por piso de latência, sem leituras. Rodada 3: não achou nada."
pendencias:
  - "P07: ler prazo expresso da extração na sombra de acompanhamento; ativação das sombras só com aval do André; depois, nova revisão final do pacote (pacote_concluido: P07)."
```
