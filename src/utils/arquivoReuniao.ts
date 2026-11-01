// Texto e nome do arquivo .txt da reunião — o mesmo para o botão "Salvar no
// Drive", o download e o salvamento automático ao parar a gravação.

export interface FalaDoArquivo {
  speaker: string;
  text: string;
  timestamp: Date;
}

export interface MensagemDoArquivo {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

export const montarTextoReuniao = (
  inicio: Date,
  fim: Date,
  falas: readonly FalaDoArquivo[],
  linhaConsentimento: string,
  mensagens: readonly MensagemDoArquivo[] = [],
  titulo?: string | null,
): string => {
  const linhasFala = falas.length > 0
    ? falas.map(t => `[${t.timestamp.toLocaleTimeString('pt-BR')}] ${t.speaker}: ${t.text}`)
    : ['(Sem falas transcritas)'];
  const secaoChat = mensagens.length > 0
    ? ['', '=== CHAT ASSISTENTE ===', ...mensagens.map(m => `[${m.timestamp.toLocaleTimeString('pt-BR')}] ${m.role === 'user' ? 'Você' : 'Assistente'}: ${m.content}`)]
    : [];
  return [
    'TRANSCRIÇÃO DE REUNIÃO',
    ...(titulo ? [titulo] : []),
    '',
    `Início: ${inicio.toLocaleString('pt-BR')}`,
    `Fim: ${fim.toLocaleString('pt-BR')}`,
    linhaConsentimento,
    '',
    '=== TRANSCRIÇÃO ===',
    ...linhasFala,
    ...secaoChat,
    '',
  ].join('\n');
};

const dois = (n: number) => String(n).padStart(2, '0');

/** "Reuniao_2026-11-01_14-00.txt", ou com o título: "Reuniao_2026-11-01_14-00 - Alinhamento PROAD.txt". */
export const nomeArquivoReuniao = (inicio: Date, titulo?: string | null): string => {
  const base = `Reuniao_${inicio.getFullYear()}-${dois(inicio.getMonth() + 1)}-${dois(inicio.getDate())}_${dois(inicio.getHours())}-${dois(inicio.getMinutes())}`;
  const limpo = (titulo || '').replace(/[\\/:*?"<>|\r\n\t]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 80);
  return limpo ? `${base} - ${limpo}.txt` : `${base}.txt`;
};
