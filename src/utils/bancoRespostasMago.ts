// src/utils/bancoRespostasMago.ts
// Banco de respostas do MAGO — apresentação à SETEC/MEC (01/09) e FDI (02/09).
//
// Provisório de propósito: enquanto a camada de PREPARAÇÃO não existir, o banco
// é escrito à mão a partir do documento de apoio. Foi assim que ele provou
// valor antes de existir sistema, e é assim que dá para testar o casador hoje.
// Quando a preparação existir, isto vira dado e sai do código.
//
// Fonte: "MAGO — Banco de respostas para SETEC/MEC", documento no Drive.

import type { CartaoResposta } from './cartoesReuniao';

export const BANCO_MAGO: CartaoResposta[] = [
  {
    id: 'suap',
    pergunta: 'Como isso se relaciona com o SUAP?',
    gatilhos: ['suap', 'dentro do suap', 'integrar com o suap', 'ja tem no suap'],
    resposta: [
      'São camadas diferentes. O SUAP é transacional, é onde o processo acontece.',
      'O MAGO é diagnóstico e monitoramento de maturidade, ancorado num questionário externo que muda a cada ciclo por decisão do TCU.',
      'E nada impede o MAGO consumir evidências que já vivem no SUAP. Integração, não substituição.',
    ],
    naoDizer: 'Nada que soe a disputa por território. Quem trata como concorrência perde a sala.',
  },
  {
    id: 'politica-de-rede',
    pergunta: 'Isso é política de rede ou projeto de um campus?',
    gatilhos: ['politica de rede', 'projeto de um campus', 'iniciativa isolada', 'so do ifes'],
    resposta: [
      'Hoje é iniciativa institucional do Ifes, com o IF Roraima em teste e o CONIF discutindo adoção compartilhada.',
      'É exatamente por isso que estou aqui: virar política da Rede não é decisão minha, é de vocês.',
    ],
    naoDizer: 'Não diga que já é da Rede. Não é, e alguém na sala sabe disso.',
  },
  {
    id: 'custo',
    pergunta: 'Quanto custa?',
    gatilhos: ['quanto custa', 'qual o custo', 'qual o valor', 'custo por instituicao', 'quanto sai'],
    resposta: [
      'A Rede não está comprando hospedagem. Está custeando uma equipe que sustenta e evolui o sistema.',
      '70,8% é equipe, cinco pessoas. 14,3% infraestrutura. 13% a taxa da Fundação.',
      'Nuvem e IA de verdade são 5,7% do total.',
    ],
    numeros: [
      'R$ 210.220,00 por ano, toda a Rede',
      'R$ 5.127,32 por instituição/ano',
      'R$ 427,28 por mês',
    ],
  },
  {
    id: 'quem-paga',
    pergunta: 'E quem paga?',
    gatilhos: ['quem paga', 'forma de pagamento', 'como pagar', 'rateio', 'de onde vem o recurso'],
    resposta: [
      'Custeio central pelo MEC/SETEC — sem rateio e sem risco de adesão parcial.',
      'TED entre órgãos federais, Decreto 10.426/2020.',
      'Fundação de apoio, Lei 8.958/1994 — é o que a planilha já pressupõe.',
      'CONIF como centralizador: uma relação em vez de 41.',
      'É custeio, não investimento: serviço continuado em nuvem não incorpora ao patrimônio.',
    ],
    naoDizer:
      'Não afirme rubrica orçamentária específica sem confirmar com a área. Confundir custeio com investimento trava processo por meses.',
  },
  {
    id: 'queda-posicao',
    pergunta: 'Se o Ifes tem a ferramenta, por que caiu de 6º para 13º?',
    gatilhos: ['caiu de', 'por que caiu', 'perdeu posicao', 'decimo terceiro', 'piorou'],
    resposta: [
      'Em 2024 o levantamento foi reestruturado: incorporou sustentabilidade social e ambiental, primeiro indicador público federal de ESG. Não dá comparação direta.',
      'Nas dimensões em que o MAGO atuava, o Ifes é 2º entre 38.',
      'A queda está nas duas dimensões novas, que a ferramenta ainda não cobria.',
    ],
    numeros: [
      'Governança pública 79,5% (média 54,8%)',
      'Gestão de pessoas 78,3% (média 41,1%)',
      'Social 22,2% · Ambiental 25,4%',
    ],
    naoDizer:
      'Não atribua posições e médias ao TCU — são cálculo dos autores. E 78,3% é o iGestPessoas; o iGovPessoas é 64,6%.',
  },
  {
    id: 'ia-decide',
    pergunta: 'A IA decide? Manda coisa para o TCU?',
    gatilhos: ['a ia decide', 'inteligencia artificial decide', 'manda para o tcu', 'envia para o tcu', 'a ia responde sozinha'],
    resposta: [
      'Não. Ela relaciona documentos, redige justificativa e sugere plano — tudo como proposta.',
      'Não decide, não envia nada ao TCU, não emite veredito e não busca links sozinha.',
      'O texto nunca muda sem aceite explícito, parágrafo por parágrafo.',
    ],
    naoDizer: 'Se puder, demonstre em vez de explicar. O diff com Aceitar e Desfazer encerra em dez segundos.',
  },
  {
    id: 'lgpd',
    pergunta: 'E os dados? LGPD?',
    gatilhos: ['lgpd', 'protecao de dados', 'seguranca dos dados', 'onde ficam os dados'],
    resposta: [
      'Nuvem multi-organização com isolamento por organização, conformidade com a LGPD e log de auditoria de toda alteração.',
      'Diagnóstico público só se a instituição ligar.',
      'Há um especialista em segurança da informação custeado no projeto, 20h semanais.',
      'E os dados do levantamento do TCU são públicos por definição.',
    ],
  },
  {
    id: 'quem-usa',
    pergunta: 'Quem já usa?',
    gatilhos: ['quem ja usa', 'quem usa hoje', 'outras instituicoes usam', 'tem caso de uso'],
    resposta: [
      'IF Roraima, em caráter de teste. CONIF discutindo adoção compartilhada.',
      '1º lugar no Prêmio de Boas Práticas do MEC, categoria Fortalecimento da Gestão de Riscos e Controles Internos.',
    ],
    naoDizer:
      'ENAP e Reditec são SUBMISSÕES, não prêmios. Sobre o TCU: a equipe técnica reconheceu o alinhamento metodológico. Não houve validação formal.',
  },
  {
    id: 'inpi',
    pergunta: 'De quem é o software?',
    gatilhos: ['de quem e o software', 'titularidade', 'propriedade intelectual', 'inpi', 'licenca do software', 'quem e o dono'],
    resposta: [
      'Registro no INPI: BR512024001217-6.',
      'A modelagem jurídica da cessão está sendo tratada com a Procuradoria.',
    ],
    naoDizer: 'Não improvise titularidade. É a informação que ainda falta confirmar.',
  },
  {
    id: 'escala',
    pergunta: 'Aguenta 41 instituições?',
    gatilhos: ['aguenta', 'escala', 'quarenta e uma instituicoes', 'suporta o volume', 'performance'],
    resposta: [
      'Arquitetura serverless em React e Firebase, multi-organização, com isolamento por instituição.',
      'Sem instalação local em nenhuma delas. O custo marginal por instituição adicional é baixo.',
      'A infraestrutura inteira é mil reais por mês. E o modelo já roda com mais de uma organização hoje.',
    ],
  },
  {
    id: 'prazo-implantacao',
    pergunta: 'Quanto tempo para um instituto entrar?',
    gatilhos: ['quanto tempo para entrar', 'prazo de implantacao', 'quanto tempo demora', 'como e a adesao'],
    resposta: [
      'Cerca de 90 dias, em seis etapas.',
      'Primeira semana: adesão, perfis e importação da linha de base do ciclo TCU 2024.',
      'Semanas 2 e 3 os articuladores, semana 4 capacitação, meses 2 e 3 o primeiro ciclo.',
      'A instituição não começa do zero: as respostas de 2024 entram importadas. O trabalho é de revisão, não de digitação.',
    ],
  },
  {
    id: 'dependencia-pessoal',
    pergunta: 'E se você sair do Ifes?',
    gatilhos: ['se voce sair', 'dependencia de uma pessoa', 'e se voce nao estiver', 'continuidade'],
    resposta: [
      'A planilha custeia cinco pessoas, não uma: coordenador técnico, operador de infraestrutura, especialista em segurança e dois bolsistas.',
      'A expansão prevê comitê gestor com relatórios de execução.',
      'É pergunta legítima, e a estrutura de sustentação é justamente o que se decide agora.',
    ],
    naoDizer: 'Responda sem defensividade.',
  },
  {
    id: 'mudanca-questionario',
    pergunta: 'E se o TCU mudar o questionário de novo?',
    gatilhos: ['mudar o questionario', 'se o tcu mudar', 'proximo ciclo muda', 'versionamento'],
    resposta: [
      'Já mudou, e o sistema atravessou.',
      'O catálogo é versionado: cada ciclo entra como versão nova, preservando o histórico.',
      'A reestruturação de 2024 foi absorvida por esse mecanismo.',
    ],
  },
  {
    id: 'ganho-mec',
    pergunta: 'O que o MEC ganha com isso?',
    gatilhos: ['o que o mec ganha', 'qual o beneficio para a setec', 'o que muda para o ministerio'],
    resposta: [
      'Hoje a SETEC vê a maturidade da Rede uma vez por ciclo, pelo resultado do TCU, depois que já passou.',
      'Com a Rede na mesma ferramenta, passa a ver em que ponto cada instituição está, em que está travada e o que está fazendo — de forma contínua e comparável.',
      'O portal da Rede Federal já mostra as 41 instituições por qualquer um dos 14 indicadores. Isso já existe e é público.',
      'O que muda é o dado deixar de ser fotografia anual e virar acompanhamento.',
    ],
  },
];
