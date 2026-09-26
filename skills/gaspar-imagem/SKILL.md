---
name: gaspar-imagem
description: Cria ou edita imagens pelo Gaspar (GPT Image 2.5 da OpenAI), escrevendo você mesmo um prompt completo e detalhado no método do guia oficial da OpenAI. Use SEMPRE que o André pedir uma imagem, ilustração, foto, capa, banner, ícone, logotipo, infográfico, arte para slide/post/documento, ou quiser mudar uma imagem existente (trocar fundo, usar um logo, refazer num estilo, variações) — mesmo que ele não diga "Gaspar" e mesmo havendo outro gerador de imagem conectado. Usa as tools gerar_imagem, editar_imagem e consultar_job do conector Gaspar.
---

# Imagens pelo Gaspar

O André descreve o que quer em poucas palavras; **você escreve o prompt de verdade**, completo, e o Gaspar gera. Nunca repasse o pedido cru ("um farol ao entardecer") para a tool: transforme-o num briefing visual. Para imagem, use sempre as tools do Gaspar — não outros geradores (Canva, artefato com SVG etc.), a não ser que ele peça.

## Fluxo

1. **Entenda o uso.** Para que é a imagem (slide, capa de documento, post, ícone, ilustração de relatório)? Isso decide proporção, estilo e se precisa de texto. Se o pedido já basta, não pergunte nada; se faltar algo essencial, faça **uma** pergunta e siga.
2. **Escreva o prompt** com a estrutura abaixo. Mostre-o ao André só se ele pedir ou se houver escolha estética em aberto — senão, gere direto.
3. **Chame a tool** com os parâmetros certos (tabela no fim). Ela devolve `job_id`: chame `consultar_job` até `done`, sem perguntar. Leva ~15–30 s (até ~2 min em `high`).
4. **Olhe a imagem** que vem anexada ao resultado e confira contra o pedido: texto soletrado certo, nada a mais, composição, cores. Se algo saiu errado, corrija com `editar_imagem` (passando a imagem gerada, pelo `drive_file_id`) antes de entregar — uma mudança por vez.
5. **Entregue**: diga em uma ou duas frases o que saiu e dê o `link_download` (arquivo original; é esse que se usa em slides, páginas e artefatos) e o `link_visualizacao` (Drive). Se ela pertence a uma ação do Gaspar, use `task_id` para anexar.

## Como escrever o prompt

Siga esta ordem, em blocos rotulados ou linhas separadas (não um parágrafo corrido). Seja concreto; cada linha deve mudar algo visível.

1. **Resultado e uso** — o que é a peça e para onde vai: "Ilustração de abertura para slide 16:9 de apresentação institucional".
2. **Cena e sujeito** — lugar, momento, o sujeito principal e o que ele está fazendo.
3. **Detalhes visíveis** — materiais e texturas, cores (2 a 4, com nome), luz (hora do dia, direção, dura/difusa), clima.
4. **Meio e estilo** — nomeie a técnica: "fotografia realista", "ilustração editorial flat", "aquarela", "render 3D", "gravura". Para foto, escreva **"fotorrealista"**. Referências de câmera servem para clima e enquadramento, não como especificação técnica.
5. **Composição** — enquadramento (plano aberto, close, vista de cima), ângulo (altura dos olhos, contra-plongée), onde fica cada coisa ("sujeito à direita, espaço vazio à esquerda para o título do slide").
6. **Pessoas** (se houver) — escala em relação ao ambiente, enquadramento do corpo ("corpo inteiro, pés visíveis"), para onde olham, o que as mãos fazem; para foto, textura real de pele.
7. **Texto na imagem** (se houver) — o texto exato **entre aspas**, com acentos, dizendo que aparece **uma vez só**; fonte (ex.: "sans-serif em negrito"), cor, tamanho relativo e posição. Palavra difícil ou nome próprio: soletre letra por letra. Termine com "nenhum outro texto".
8. **Restrições** — o que não pode aparecer: "sem marca-d'água, sem logotipos, sem texto extra, sem bordas". Diga explicitamente — o que não for proibido o modelo pode inventar.

Pode escrever em português. Evite adjetivos vazios ("lindo", "incrível", "alta qualidade") e instruções contraditórias.

### Exemplo

Pedido: "uma imagem de um farol ao entardecer pro slide de abertura".

```
Uso: imagem de fundo para o slide de abertura de uma apresentação (16:9), com espaço livre para título.
Cena: farol branco com faixa preta sobre costão de rochas escuras no litoral do Espírito Santo, ao entardecer; mar com ondas quebrando nas pedras; ilha pequena ao fundo.
Luz e cor: sol baixo à direita, luz dourada lateral; céu em laranja, pêssego e lilás; sombras longas em azul-arroxeado.
Estilo: ilustração editorial com textura de guache, pinceladas visíveis, acabamento limpo.
Composição: plano aberto, altura dos olhos; farol no terço direito; metade esquerda com céu e mar calmos, sem elementos, para receber o título.
Restrições: sem texto, sem pessoas, sem barcos, sem marca-d'água.
```

### Tipos de peça

- **Foto realista**: "fotorrealista", textura real (pele, desgaste, poeira), luz natural nomeada, enquadramento de fotógrafo; "espontâneo, não posado" quando fizer sentido.
- **Infográfico / diagrama / slide com conteúdo**: escreva como um briefing didático — título exato, público, o que deve ensinar, formato (fluxo, linha do tempo, comparação), cada rótulo exato entre aspas, ícones no mesmo estilo, setas claras, fundo branco, bastante respiro. Qualidade `high`.
- **Logotipo / ícone**: personalidade da marca e onde será usado; formas geométricas simples, poucos traços, legível pequeno, centralizado com margem; `fundo: transparente` + png, e peça "sujeito isolado em fundo totalmente transparente, sem fundo sólido, sem xadrez, sem sombra".
- **Peça de divulgação**: briefing criativo — público, tom, conceito, composição, a frase exata entre aspas; evite cara de banco de imagens.

## Edição (`editar_imagem`)

- Diga **o que muda** e **o que fica**: "Mude apenas X. Mantenha todo o resto igual: rostos, proporções, roupas, enquadramento, luz, cores, texto."
- Várias referências: identifique cada uma pela ordem e papel — "Imagem 1: foto da equipe (sujeito). Imagem 2: logotipo (aplicar no canto superior direito, pequeno)". Diga como combinar e peça luz, escala, perspectiva e sombras coerentes.
- **Uma mudança por rodada** e repita a lista do que deve ficar a cada nova edição — senão os detalhes derivam.
- Personagem consistente em várias imagens: gere a primeira, depois use-a como referência com "não redesenhe o personagem" e repita a descrição dele.
- Máscara: só se o André tiver um PNG com a área a mudar transparente; sem ela, a instrução de "mude apenas X" costuma bastar no `sunburst`.
- Nunca envie foto ou documento com dados de terceiros (servidores, alunos) sem pedido explícito dele.

## Parâmetros

| Parâmetro | Como escolher |
| --- | --- |
| `proporcao` | `16:9` slide/banner/capa horizontal · `9:16` celular/story · `1:1` post/ícone/avatar · `4:3` e `3:4` documento e cartaz |
| `modelo` | `flare` (padrão, rápido) para quase tudo. `sunburst` quando a exigência é alta: edição precisa, rosto a preservar, muito texto, composição difícil. `editar_imagem` já usa `sunburst` |
| `qualidade` | `medium` padrão. `low` para rascunho ou para testar ideias. `high` para texto pequeno, infográfico, retrato de perto. `xhigh`/`max` só se `high` não resolver — mais alto nem sempre fica melhor |
| `quantidade` | 2–4 quando ele quiser escolher entre opções; senão 1 |
| `fundo` | `transparente` para logo, ícone, recorte (com `formato` png ou webp) |
| `task_id` | quando a imagem é de uma ação do Gaspar — fica anexada e no diário |

Custo de referência: ~US$ 0,01 por imagem em `medium` 16:9, menos de 1 centavo em `low`; `high` custa várias vezes mais. Há teto diário (US$ 2 por padrão); se a tool recusar por teto, ofereça qualidade menor ou menos imagens.

Fonte do método: guias de prompting de imagem da OpenAI (developers.openai.com/api/docs/guides/image-prompting e o cookbook "GPT Image Generation Models Prompting Guide").
