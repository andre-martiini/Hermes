import React from 'react';
import { AppSettings, Categoria, Tarefa } from '../../types';
import { functions } from '../../firebase';
import { httpsCallable } from 'firebase/functions';

export const DEFAULT_APP_SETTINGS: AppSettings = {

  notifications: {
    enablePush: true,
    habitsReminder: {
      enabled: true,
      time: "20:00"
    },
    weighInReminder: {
      enabled: true,
      frequency: 'weekly',
      time: "07:00",
      dayOfWeek: 1 // Segunda-feira
    },
    budgetRisk: {
      enabled: true
    },
    overdueTasks: {
      enabled: true
    },
    pgcAudit: {
      enabled: true,
      daysBeforeEnd: 5
    },
    custom: []
  }
};

export const getDaysInMonth = (year: number, month: number) => new Date(year, month + 1, 0).getDate();

export const isWorkDay = (date: Date) => {
  const day = date.getDay();
  return day !== 0 && day !== 6; // Seg-Sex
};

export const callScrapeSipac = async (taskId: string, processoSei: string) => {
  const data = { taskId, processoSei };
  if (import.meta.env.DEV) {
    try {
      const response = await fetch('/proxy-functions/scrapeSipac', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data })
      });
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Fetch error:', response.status, errorText);
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return response.json();
    } catch (error) {
      console.error('Erro na chamada via proxy:', error);
      throw error;
    }
  } else {
    const scrapeSipacFn = httpsCallable(functions, 'scrapeSipac');
    return scrapeSipacFn(data);
  }
};

export const getMonthWorkDays = (year: number, month: number) => {
  const days = [];
  const totalDays = getDaysInMonth(year, month);
  for (let d = 1; d <= totalDays; d++) {
    const date = new Date(year, month, d);
    if (isWorkDay(date)) days.push(new Date(date));
  }
  return days;
};

export const normalizeStatus = (status: string): string => {
  if (!status) return 'em andamento';
  return status
    .toLowerCase()
    .trim()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
};

export const isStandbyStatus = (status?: string | null) => {
  const normalized = normalizeStatus(status || '');
  return normalized === 'stand-by' || normalized === 'standby' || normalized === 'stand by' || normalized === 'cgby';
};
export const isCompletedStatus = (status?: string | null) => normalizeStatus(status || '') === 'concluido';

export const hasValidTaskDate = (date?: string | null) => {
  return Boolean(date && date !== '-' && date !== '0000-00-00');
};

export const applyStandbyDateRules = (
  updates: Partial<Tarefa> & Record<string, any>,
  previousTask?: Partial<Tarefa> | null
) => {
  const payload: Record<string, any> = { ...updates };
  const hasDateLimit = Object.prototype.hasOwnProperty.call(payload, 'data_limite');
  const hasDateStart = Object.prototype.hasOwnProperty.call(payload, 'data_inicio');

  if (hasDateLimit || hasDateStart) {
    const singleDate = (payload.data_limite ?? payload.data_inicio ?? '') as string;
    payload.data_limite = singleDate;
    payload.data_inicio = singleDate;
  }

  const dateWasAdded = (hasDateLimit || hasDateStart) && hasValidTaskDate(payload.data_limite || payload.data_inicio);
  if (dateWasAdded && isStandbyStatus(previousTask?.status)) {
    payload.status = 'em andamento';
  }

  const nextStatus = Object.prototype.hasOwnProperty.call(payload, 'status')
    ? String(payload.status)
    : previousTask?.status;

  if (isStandbyStatus(nextStatus)) {
    payload.data_limite = '';
    payload.data_inicio = '';
    payload.horario_inicio = null;
    payload.horario_fim = null;
    return payload;
  }

  return payload;
};

export const formatWhatsAppText = (text: string, isDarkMode: boolean = false) => {
  if (!text) return text;

  // Process block-level elements
  const lines = text.split('\n');
  const processedLines: React.JSX.Element[] = [];
  let currentList: React.JSX.Element[] = [];

  const flushList = () => {
    if (currentList.length > 0) {
      processedLines.push(<ul key={`list-${processedLines.length}`} className="list-disc ml-6 my-2 space-y-1">{currentList}</ul>);
      currentList = [];
    }
  };

  lines.forEach((line, index) => {
    // Lists
    if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
      currentList.push(<li key={index} className="pl-1">{formatInlineWhatsAppText(line.trim().substring(2), isDarkMode)}</li>);
    } else {
      flushList();

      // Blockquote
      if (line.trim().startsWith('>')) {
        processedLines.push(
          <blockquote key={index} className={`border-l-4 pl-4 py-1 my-2 italic rounded-r-lg ${isDarkMode ? 'border-white/20 text-white/50 bg-white/5' : 'border-slate-300 text-slate-500 bg-slate-50/50'}`}>
            {formatInlineWhatsAppText(line.trim().substring(1).trim(), isDarkMode)}
          </blockquote>
        );
      } else if (line.trim() === '') {
        processedLines.push(<div key={index} className="h-2"></div>);
      } else {
        processedLines.push(<div key={index}>{formatInlineWhatsAppText(line, isDarkMode)}</div>);
      }
    }
  });
  flushList();

  return <div className="space-y-0.5">{processedLines}</div>;
};

export const formatInlineWhatsAppText = (text: string, isDarkMode: boolean = false) => {
  let parts: (string | React.JSX.Element)[] = [text];

  const applyRegex = (regex: RegExp, formatter: (match: string) => React.JSX.Element) => {
    const newParts: (string | React.JSX.Element)[] = [];
    parts.forEach(part => {
      if (typeof part !== 'string') {
        newParts.push(part);
        return;
      }

      let lastIndex = 0;
      let match;
      while ((match = regex.exec(part)) !== null) {
        if (match.index > lastIndex) {
          newParts.push(part.substring(lastIndex, match.index));
        }
        newParts.push(formatter(match[1]));
        lastIndex = regex.lastIndex;
      }
      if (lastIndex < part.length) {
        newParts.push(part.substring(lastIndex));
      }
    });
    parts = newParts;
  };

  // Monospace ```text``` (do this first to avoid other formatting inside)
  applyRegex(/```([\s\S]+?)```/g, (inner) => <pre className={`p-3 rounded-lg font-mono text-[11px] my-2 overflow-x-auto border ${isDarkMode ? 'bg-black/30 border-white/10 text-white/80' : 'bg-slate-100/80 border-slate-200 text-slate-800'}`}>{inner}</pre>);

  // Inline Code `text`
  applyRegex(/`([^`]+?)`/g, (inner) => <code className={`px-1.5 py-0.5 rounded font-mono text-[11px] border ${isDarkMode ? 'bg-black/30 border-white/10 text-pink-400' : 'bg-slate-100 border-slate-200 text-pink-600'}`}>{inner}</code>);

  // Bold *text*
  applyRegex(/\*([^\*]+?)\*/g, (inner) => <strong className={`font-black ${isDarkMode ? 'text-white' : 'text-slate-900'}`}>{inner}</strong>);

  // Italic _text_
  applyRegex(/_([^_]+?)_/g, (inner) => <em className="italic">{inner}</em>);

  // Strikethrough ~text~
  applyRegex(/~([^~]+?)~/g, (inner) => <del className="line-through opacity-60">{inner}</del>);

  return <>{parts.map((part, i) => <React.Fragment key={i}>{part}</React.Fragment>)}</>;
};

export const detectAreaFromTitle = (titulo: string): Categoria => {
  const tituloLower = titulo.toLowerCase();

  const clcKeywords = ['licitação', 'licitacao', 'pregão', 'pregao', 'contrato', 'dispensa', 'inexigibilidade', 'compra', 'aquisição', 'aquisicao', 'processo'];
  const assistenciaKeywords = ['assistência', 'assistencia', 'estudantil', 'aluno', 'bolsa', 'auxílio', 'auxilio', 'permanência', 'permanencia'];
  const saudeKeywords = ['saúde', 'saude', 'médico', 'medico', 'exame', 'consulta', 'medicamento', 'hospital', 'biometria', 'peso', 'treino'];
  const financeiroKeywords = ['pagamento', 'boleto', 'conta', 'dinheiro', 'valor', 'reais', 'financeiro', 'banco', 'transferência', 'pix', 'gasto', 'orçamento'];
  const sistemaKeywords = ['sistema', 'bug', 'feature', 'desenvolvimento', 'dev', 'api', 'banco de dados', 'deploy', 'servidor'];

  if (clcKeywords.some(keyword => tituloLower.includes(keyword))) return 'CLC';
  if (assistenciaKeywords.some(keyword => tituloLower.includes(keyword))) return 'ASSISTÊNCIA';
  if (saudeKeywords.some(keyword => tituloLower.includes(keyword))) return 'SAÚDE';
  if (financeiroKeywords.some(keyword => tituloLower.includes(keyword))) return 'FINANCEIRO';
  if (sistemaKeywords.some(keyword => tituloLower.includes(keyword))) return 'SISTEMA';

  return 'GERAL';
};
