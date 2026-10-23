# Arquivo: P07 sub-entrega 8/N (movida de execucao.md em 2026-10-23, sem alteração de conteúdo)

```yaml
pacote: "P07 sub-entrega 8/N -- passo 2 (parte pura, sombra): functions/autonomy/extracao_estruturada.py. validar_extracao(mensagem, saida, hoje) valida a saída já decodificada de um modelo de extração ({compromissos:[{classe,objeto,evidencia}]}, máx. 5) contra a mensagem: evidência literal (normalizada) e com >=2 caracteres visíveis (NFC, sem preenchedores invisíveis), classe conhecida, duplicatas fundidas. O modelo nunca afrouxa a seleção barata: base cancelamento/vaga/pergunta prevalece com incerta=True; mesma classe herda base.incerta; promessa sobre base incerta vira intencao_vaga; qualquer outra divergência é incerta. comparar_sombra(base, extraidos) mede concordância (promessa firme modelo x base) para métricas em sombra. Só ValueError. Sem I/O, sem chamada de modelo e sem wiring; fila antiga e A06 não alteradas."
estado: validado
inicio: "2026-10-23T11:00:00Z"
fim: "2026-10-23T12:30:00Z"
decisoes:
  - id: p07-sub8-triagem
    motivo: "Nenhuma PR aberta no início do disparo; branches claude/* restantes são antigas/mescladas, nenhuma execução paralela."
  - id: p07-sub8-arquivo-execucao
    motivo: "execucao.md arquivado (bloco P07 sub 4 -> execucao-archive-p07sub4.md)."
  - id: p07-sub8-limitacoes
    motivo: "Aceitas por ser módulo puro em sombra, sem wiring: modelo que fabrica item consistente com a ressalva; ressalvas que o classificador barato não reconhece; entregável fora do vocabulário de cumprimento._OBJETOS; sobrecautela (itens independentes ficam incertos quando a dúvida não é identificável). Reabrir ao ligar o wiring."
  - id: p07-sub8-marcas-combinantes
    motivo: "Objeto/evidência só com marcas combinantes são recusados (conservador); aceito."
testes:
  resultados:
    - "functions/ completo ANTES 4556 OK (P07 sub 7); com a versão intermediária 4565 OK (284s); test_autonomy_extracao_estruturada 26 OK (novo); DEPOIS 4582 OK (280s, head final)."
revisao_adversarial:
  - "Rodada 1: evidência/objeto só invisível, comparar_sombra com entradas inválidas e iterador. Rodada 2: preenchedores Hangul, cautela só em promessa, base não validada. Rodada 3: incerteza da base descartada, preenchedor U+3164. Rodada 4: contagem de jamos Hangul (NFC). Rodada 5: incerteza herdada só em classes de cautela. Rodada 6: divergência da base perdia dúvida. Todos corrigidos. Rodada 7 (fuzz diferencial de 30 mil mensagens contra oráculo): não achou nada. Depois da PR, Codex P2 (base global contaminava cláusulas independentes) -> base por sentença; rodadas 8-17 sobre esse isolamento acharam, cada uma, ressalvas vizinhas órfãs, item espúrio de evidência curta, dedup dependente de ordem, anáfora, flexões/plural -ões, e-mail com hífen e abreviações (doc/mail), todas corrigidas (isolamento só com ressalva explicada por outro item de entregável conhecido, sem dúvida residual). Rodada 17 achou só abreviação doc (corrigida); não houve rodada final limpa após essa correção."
pendencias:
  - "P07: wiring em atencao_whatsapp somente com flag/sombra (chamar o modelo de extração, gravar comparar_sombra); suíte F02 com limiar de precisão da seção 11; revisão final do pacote para pacote_concluido: P07."
```
