import { Tarefa } from '../../types';
import { parseDiaryRichNote } from './diaryEntries';
import { normalizeStatus } from './helpers';

export const generateMarkdown = (
  moduleName: string,
  description: string,
  dictionary: Record<string, string>,
  dataSections: { title: string, data: any[], columns?: string[] }[]
): string => {
  const timestamp = new Date().toLocaleString('pt-BR');
  let md = `# Exportacao do Modulo: ${moduleName}\n`;
  md += `**Data da Exportacao:** ${timestamp}\n\n`;

  md += `## 1. Introducao\n`;
  md += `${description}\n\n`;

  md += `## 2. Dicionario de Dados\n`;
  md += `| Campo | Significado |\n`;
  md += `|---|---|\n`;
  Object.entries(dictionary).forEach(([key, desc]) => {
    md += `| **${key}** | ${desc} |\n`;
  });
  md += `\n`;

  md += `## 3. Dados Atuais\n`;

  dataSections.forEach((section, idx) => {
    md += `### 3.${idx + 1}. ${section.title}\n`;
    if (!section.data || section.data.length === 0) {
      md += `*Nenhum registro encontrado.*\n\n`;
      return;
    }

    const keys = section.columns || Object.keys(section.data[0]);
    md += `| ${keys.join(' | ')} |\n`;
    md += `| ${keys.map(() => '---').join(' | ')} |\n`;

    section.data.forEach(row => {
      md += `| ${keys.map(k => {
        const val = row[k];
        if (val === null || val === undefined) return '-';
        if (typeof val === 'object') return JSON.stringify(val);
        return String(val).replace(/\|/g, '\\|');
      }).join(' | ')} |\n`;
    });
    md += `\n`;
  });

  return md;
};

export const downloadMarkdown = (filename: string, content: string) => {
  const blob = new Blob([content], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${filename}_${new Date().toISOString().split('T')[0]}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

const formatTaskStatus = (task: Tarefa) => {
  const status = normalizeStatus(task.status);
  if (status === 'stand-by') return 'Stand-by';
  if (status === 'concluido') return 'Concluido';
  return 'Em andamento';
};

const formatTaskDate = (value?: string | null) => {
  if (!value || value === '-' || value === '0000-00-00') return 'Sem prazo definido';
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  return new Date(`${value}T00:00:00`).toLocaleDateString('pt-BR');
};

const formatDiaryEntry = (note: string) => {
  const parsed = parseDiaryRichNote(note || '');
  if (!parsed) return { tipo: 'texto', titulo: '', conteudo: note || '' };
  if (parsed.type === 'FILE') return { tipo: 'arquivo', titulo: parsed.name || 'Arquivo', conteudo: parsed.value || '' };
  if (parsed.type === 'LINK') return { tipo: 'link', titulo: parsed.name || 'Link', conteudo: parsed.value || '' };
  return { tipo: 'contato', titulo: parsed.name || 'Contato', conteudo: parsed.value || '' };
};

export const generateActionsMarkdown = (tasks: Tarefa[]): string => {
  const timestamp = new Date().toLocaleString('pt-BR');
  let md = '# Exportacao do Modulo: Acoes\n';
  md += `**Data da Exportacao:** ${timestamp}\n\n`;
  md += '## 1. Visao Geral\n';
  md += 'Exportacao detalhada das acoes cadastradas no Hermes, incluindo metadados, diario de bordo e anexos vinculados.\n\n';
  md += '## 2. Resumo\n';
  md += `- Total de acoes: ${tasks.length}\n`;
  md += `- Em andamento: ${tasks.filter(task => normalizeStatus(task.status) === 'em andamento').length}\n`;
  md += `- Em stand-by: ${tasks.filter(task => normalizeStatus(task.status) === 'stand-by').length}\n`;
  md += `- Concluidas: ${tasks.filter(task => normalizeStatus(task.status) === 'concluido').length}\n\n`;
  md += '## 3. Acoes Exportadas\n\n';

  if (tasks.length === 0) {
    md += '*Nenhuma acao encontrada.*\n';
    return md;
  }

  tasks.forEach((task, index) => {
    md += `### 3.${index + 1}. ${task.titulo || `Acao ${task.id}`}\n`;
    md += `- ID: ${task.id}\n`;
    md += `- Status: ${formatTaskStatus(task)}\n`;
    md += `- Prazo: ${formatTaskDate(task.data_limite || task.data_inicio)}\n`;
    md += `- Projeto: ${task.projeto || 'Nao informado'}\n`;
    md += `- Categoria: ${task.categoria || 'Nao classificada'}\n`;
    md += `- Prioridade: ${task.prioridade || 'Nao informada'}\n`;
    md += `- Criada em: ${task.data_criacao ? new Date(task.data_criacao).toLocaleString('pt-BR') : 'Nao informado'}\n`;
    md += `- Atualizada em: ${task.data_atualizacao ? new Date(task.data_atualizacao).toLocaleString('pt-BR') : 'Nao informado'}\n`;
    md += `- Concluida em: ${task.data_conclusao ? new Date(task.data_conclusao).toLocaleString('pt-BR') : 'Nao concluida'}\n`;
    if (task.horario_inicio || task.horario_fim) md += `- Janela de horario: ${task.horario_inicio || '--:--'} ate ${task.horario_fim || '--:--'}\n`;
    if (task.descricao) md += `- Descricao: ${task.descricao}\n`;
    if (task.notas) md += `- Notas: ${task.notas}\n`;
    if (task.processo_sei) md += `- Processo SEI: ${task.processo_sei}\n`;
    if (task.chat_gemini_url) md += `- Link do chat: ${task.chat_gemini_url}\n`;
    if (typeof task.tempo_total_segundos === 'number') md += `- Tempo total registrado (segundos): ${task.tempo_total_segundos}\n`;
    md += '\n';

    md += '#### Diario de Bordo\n';
    const entries = [...(task.acompanhamento || [])].sort((a, b) => new Date(a.data).getTime() - new Date(b.data).getTime());
    if (entries.length === 0) {
      md += '- Sem registros no diario de bordo.\n\n';
    } else {
      entries.forEach((entry, entryIndex) => {
        const formatted = formatDiaryEntry(entry.nota || '');
        md += `${entryIndex + 1}. **${entry.data ? new Date(entry.data).toLocaleString('pt-BR') : 'Data nao informada'}**`;
        if (formatted.tipo !== 'texto') md += ` [${formatted.tipo}]`;
        md += '\n';
        if (formatted.titulo) md += `   - Titulo: ${formatted.titulo}\n`;
        md += `   - Conteudo: ${formatted.conteudo || '(vazio)'}\n`;
      });
      md += '\n';
    }

    md += '#### Arquivos, Links e Metadados\n';
    const items = task.pool_dados || [];
    if (items.length === 0) {
      md += '- Nenhum item vinculado.\n\n';
    } else {
      items.forEach((item, itemIndex) => {
        md += `${itemIndex + 1}. **${item.nome || 'Sem nome'}**\n`;
        md += `   - Tipo: ${item.tipo}\n`;
        md += `   - Referencia: ${item.valor || 'Nao informada'}\n`;
        md += `   - ID interno: ${item.id}\n`;
        md += `   - Data de criacao: ${item.data_criacao ? new Date(item.data_criacao).toLocaleString('pt-BR') : 'Nao informada'}\n`;
        if (item.drive_file_id) md += `   - ID do arquivo no Drive: ${item.drive_file_id}\n`;
      });
      md += '\n';
    }
  });

  return md;
};