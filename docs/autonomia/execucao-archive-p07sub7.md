# Arquivo: P07 sub-entrega 7/N (movida de execucao.md em 2026-10-23, sem alteração de conteúdo)

```yaml
pacote: "P07 sub-entrega 7/N -- passo 5 (parte pura): functions/autonomy/correlacao_entregaveis.py. correlacionar(promessa, evidencias, ids_compromisso) liga um compromisso a evidências de entrega em WhatsApp, Gmail, tarefa ou documento: ID em comum = vínculo firme ('id', incerta=False); só objeto prometido (planilha, relatório...) no nome da evidência = vínculo 'semantico', sempre incerta=True; sem nenhum dos dois, nada. vinculo_firme(vinculos) só conta vínculo por ID. Nunca encerra compromisso sozinha. Só ValueError para entradas inválidas (tipos exatos, canal, ref imprimível sem espaço nas pontas, ids limitados, marcas combinantes). Sem I/O e sem wiring; fila antiga e A06 não alteradas."
estado: validado
inicio: "2026-10-22T19:45:00Z"
fim: "2026-10-22T20:20:00Z"
decisoes:
  - id: p07-sub7-semantico-sempre-incerto
    motivo: "Casar só por objeto prometido é heurística; precisão sobre revocação -- consumidor mantém o compromisso pendente."
  - id: p07-sub7-triagem
    motivo: "Nenhuma PR aberta no início do disparo de 17h BRT; nenhuma execução paralela da linha de autonomia."
testes:
  resultados:
    - "functions/ completo ANTES 4552 OK (conforme P07 sub 6); test_autonomy_correlacao_entregaveis 4 OK (novo); DEPOIS 4556 OK (226s, head final)."
revisao_adversarial:
  - "Rodada 1: docstring de vinculo_firme incoerente, vinculo_firme com entrada ruim levantava TypeError/AttributeError, canal subclasse de str com __eq__ hostil, ref com caractere não imprimível/espaços. Corrigido. Rodada 2: não achou nada. Codex + rodada 3: vinculo_firme revalida campos do Vinculo; __eq__ hostil e atributo removido viram ValueError; corrigido. Rodada 4: não achou nada. Observação: objetos genéricos como "arquivo" geram ruído semântico, sempre incerto."
pendencias:
  - "P07 passo 2 (extração estruturada, sombra); wiring em atencao_whatsapp somente com flag/sombra."
```

---

