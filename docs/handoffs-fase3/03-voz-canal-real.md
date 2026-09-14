# PR 3 da Fase 3 — Voz como canal fino real (filtragem por `voiceEnabled`)

## Correção de uma suposição do `00-visao-geral.md` — leia antes de implementar

O `00-visao-geral.md` (linhas 45-61 e 82-87) afirma que, além do filtro por
`voiceEnabled`, este PR deveria "confirmar que a fila de atenção e a decisão
de aprovação do outbox já são alcançáveis por voz (não estão na lista de
exclusão)". Fui conferir no código antes de escrever este handoff e a
segunda metade dessa frase **não é verdade hoje**:

- `obter_fila_atencao` / `resolver_item_atencao` (`tools/hermes_tools.py:1932-1949`,
  `atencao.py`) operam só sobre a coleção `atencao` (`atencao.py:31`) —
  itens de ações, conversas e rotinas que algo escreveu lá dentro. Nenhum
  código grava um item de `whatsapp_outbox` nessa coleção. Ou seja, a fila
  de atenção em si **é** alcançável por voz (não está em `_VOICE_EXCLUDED`),
  mas ela não contém rascunhos de WhatsApp — não tem o que "confirmar" aí
  porque não há ligação entre as duas coleções.
- Não existe nenhuma tool MCP para aprovar ou descartar um rascunho do
  outbox. O único tool exposto é `listar_rascunhos_pendentes` (leitura). A
  decisão real (`aprovar_rascunho` / `descartar_rascunho`,
  `outbox_aprovacao.py`) só é acionada pelo callback do botão inline do
  Telegram (`outbox:{id}:yes|no`) — não passa pelo dispatcher MCP
  (`tools/mcp_dispatch.py`) e não tem schema em `functions/schemas/`.

Não é um bug: ninguém pediu decisão de outbox por voz até agora, e listar
já funciona. Mas não dá para "confirmar" algo que não existe — então este
PR não inclui isso. Ver "Fora de escopo" no fim.

## O que muda em `hermes-voice-client/orchestrator.py`

`mcp_client.list_tools()` já devolve cada tool com
`_meta.voiceEnabled` calculado pelo servidor
(`functions/mcp_server.py:584`, via `registry.is_voice_enabled`,
`functions/tools/registry.py:250-251`). `_build_gemini_tools` (linhas 70-83)
ignora esse campo hoje e monta uma `FunctionDeclaration` para **toda** tool
que o servidor lista — inclusive as ~11 em `_VOICE_EXCLUDED`
(`registry.py:202-217`: formulário, imagem, relatório, as quatro variantes
de lote, leitura de documento inteiro, e os dois registros de investimento).

Adicionar o filtro dentro da própria função, para manter testável em
isolamento sem precisar de um servidor MCP real:

```python
def _build_gemini_tools(mcp_tools: list[dict]) -> list[types.Tool]:
    declarations = []
    for tool in mcp_tools:
        if not tool.get("_meta", {}).get("voiceEnabled", False):
            continue
        input_schema = tool.get("inputSchema") or {"type": "object", "properties": {}}
        declarations.append(
            types.FunctionDeclaration(
                name=tool["name"],
                description=tool.get("description", ""),
                parameters=_json_schema_to_gemini(input_schema),
            )
        )
    if not declarations:
        return []
    return [types.Tool(function_declarations=declarations)]
```

Não mexer em `_ensure_chat` além disso — ela já passa `mcp_tools` (a lista
crua com `_meta`) para `_build_gemini_tools`, então o filtro por dentro é
suficiente e não muda a assinatura de nada que chama a função.

## Novo teste (`hermes-voice-client/test_orchestrator.py`, arquivo novo)

Não existe nenhum teste em `hermes-voice-client/` hoje (nem `pytest` nas
`requirements.txt`). Seguir o padrão `unittest` do resto do repo
(`python -m unittest`), não introduzir `pytest` só para isto. Testar
`_build_gemini_tools` isoladamente com fixtures fake — não precisa de rede
nem do Gemini de verdade:

- Uma lista com uma tool `_meta.voiceEnabled=True` e outra `False` →
  `declarations` do `Tool` retornado contém só o nome da primeira.
- Lista onde nenhuma tool tem `voiceEnabled=True` → retorna `[]` (mantém o
  comportamento atual de lista vazia).
- Tool sem a chave `_meta` (defensivo, caso um servidor MCP mais antigo
  não mande o campo) → tratada como `voiceEnabled=False`, não quebra com
  `KeyError`.

## Atualizar `hermes-voice-client/README.md`

A seção "Limitações conhecidas desta fase" (linhas 75-78) ainda diz que só
4 tools funcionam (`consultar_historico_acoes`, `buscar_arquivos_acervo`,
`buscar_contato`, `calculadora`) — desatualizado desde que
`tools/hermes_tools.py` passou a ter os handlers reais. Depois do filtro
implementado, gerar a lista real rodando localmente (com o servidor MCP no
ar):

```bash
python -c "from tools import registry; print(sorted(n for n in registry.list_mcp_enabled_tools() if registry.is_voice_enabled(n)))"
```

e substituir a lista hardcoded do README pelo resultado real (ou por uma
frase que aponte para `_VOICE_EXCLUDED` em vez de listar tool por tool, para
não desatualizar de novo na próxima tool nova). Também documentar ali, em
uma linha, que decisão de rascunho do outbox por voz não existe ainda (só
listar) — para não repetir a suposição errada do `00-visao-geral.md`.

## Validação manual do canal real

Suíte automatizada cobre só a função pura de filtro. Rodar o cliente local
de verdade uma vez (`uvicorn main:app --port 8765`, com o servidor MCP
deployado e o UID liberado em `system/mcp_access.allowed_uids`) e conferir:

1. Uma pergunta que aciona `obter_fila_atencao` ou `calculadora` funciona
   normalmente.
2. Pedir algo que só existe numa tool excluída (ex.: "gera um relatório
   completo do mês") — o modelo não deve tentar chamar `gerar_relatorio`
   porque ela nem está na lista de declarations; ele deve responder que não
   consegue fazer isso por voz (ou sugerir usar outro canal).

## Fora de escopo deste PR

- `hermes-voice-bridge/` (Twilio + Gemini Live, `main.py:556-560`): canal e
  modelo diferentes, usa tools locais (`task_tools.py`) mescladas com
  `mcp_declarations` sem o mecanismo `tools/list` do MCP — não tem o campo
  `_meta.voiceEnabled` para filtrar. Se um dia for migrado para o mesmo
  padrão do cliente local, é PR à parte.
- Tool MCP para aprovar/descartar rascunho do outbox por voz
  (`decidir_rascunho_whatsapp` ou similar): gap real identificado acima,
  mas expor o envio de uma mensagem real por voz é o mesmo tipo de decisão
  de risco que já tirou os dois `registrar_*investimento` da lista de voz
  (transcrição errada grava/dispara algo que não tem como estornar sozinho)
  — meritório de decisão própria do André, não bundlar aqui.
- VAD contínuo, barge-in, cancelamento de eco: já documentado no README como
  fase futura, sem relação com este PR.
- Qualidade da voz Piper em pt-BR: validação por escuta, ortogonal a este PR.
