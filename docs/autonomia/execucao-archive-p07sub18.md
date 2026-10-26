```yaml
pacote: "P07 sub-entrega 18/N -- wiring em sombra do passo 3 (vários compromissos por chat): extracao_compromissos_sombra passa a chamar autonomy.compromissos_chat.abrir (que não tinha chamador em produção) para cada promessa firme (não incerta) extraída da mensagem, gravando no resumo da sombra só n_compromissos e chaves_compromissos (chat__mensagem__indice) e, se algum item for descartado, compromissos_chat_erro (contagem). Mesma flag da sombra de extração (system/settings.atencao.extracao_estruturada.enabled, padrão DESLIGADO); nunca texto."
estado: validado
inicio: "2026-10-26T11:00:00Z"
fim: "2026-10-26T11:50:00Z"
decisoes:
  - id: p07-sub18-triagem
    motivo: "Nenhuma PR aberta e nenhuma execução paralela da linha de autonomia no disparo das 8h BRT. A revisão final do P07 achou o passo 3 (compromissos_chat) sem chamador em produção; pacote_concluido: P07 segue pendente."
  - id: p07-sub18-substituicao
    motivo: "A extração não tem sinal de substituição explícita; compromissos_chat.substituir continua sem chamador e fica fora da sombra. Limitação declarada: não se inventa relação por semelhança de texto (o contrato proíbe)."
  - id: p07-sub18-item-invalido
    motivo: "Item inválido (ex.: caractere não imprimível no objeto) é descartado isoladamente e contado; objeto normalizado por espaços. Achado da rodada 1 (um item ruim zerava todos)."
  - id: p07-sub18-arquivo
    motivo: "execucao.md perto de 50KB: bloco 'P07 correção da revisão final' arquivado em execucao-archive-p07correcao.md."
testes:
  resultados:
    - "functions/ completo ANTES 4660 OK (diário, sub 17); DEPOIS 4664 OK (+4 em test_extracao_compromissos_sombra)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): 1 achado real (objeto com quebra de linha/não imprimível zerava todas as promessas da mensagem) -> correção por item + normalização. Rodada 2 sobre a correção: não achou nada."
pendencias:
  - "P07: substituir (relação explícita) segue sem chamador por falta de sinal na extração -- decidir se vale um sinal de modelo ou se o passo 3 fica atendido só por independência; ativação das sombras só com aval do André; depois, nova revisão final do pacote (pacote_concluido: P07)."
```


