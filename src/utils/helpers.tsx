import React from 'react';
import { AppSettings, Categoria } from '../../types';
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
  },
  pomodoro: {
    enabled: true,
    focusTime: 10,
    breakTime: 5,
    enableBeep: true
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

export const formatWhatsAppText = (text: string) => {
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
      currentList.push(<li key={index} className="pl-1">{formatInlineWhatsAppText(line.trim().substring(2))}</li>);
    } else {
      flushList();

      // Blockquote
      if (line.trim().startsWith('>')) {
        processedLines.push(
          <blockquote key={index} className="border-l-4 border-slate-300 pl-4 py-1 my-2 italic text-slate-500 bg-slate-50/50 rounded-r-lg">
            {formatInlineWhatsAppText(line.trim().substring(1).trim())}
          </blockquote>
        );
      } else if (line.trim() === '') {
        processedLines.push(<div key={index} className="h-2"></div>);
      } else {
        processedLines.push(<div key={index}>{formatInlineWhatsAppText(line)}</div>);
      }
    }
  });
  flushList();

  return <div className="space-y-0.5">{processedLines}</div>;
};

export const formatInlineWhatsAppText = (text: string) => {
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
  applyRegex(/```([\s\S]+?)```/g, (inner) => <pre className="bg-slate-100/80 p-3 rounded-lg font-mono text-[11px] my-2 overflow-x-auto border border-slate-200 text-slate-800">{inner}</pre>);

  // Inline Code `text`
  applyRegex(/`([^`]+?)`/g, (inner) => <code className="bg-slate-100 px-1.5 py-0.5 rounded font-mono text-[11px] text-pink-600 border border-slate-200">{inner}</code>);

  // Bold *text*
  applyRegex(/\*([^\*]+?)\*/g, (inner) => <strong className="font-black text-slate-900">{inner}</strong>);

  // Italic _text_
  applyRegex(/_([^_]+?)_/g, (inner) => <em className="italic">{inner}</em>);

  // Strikethrough ~text~
  applyRegex(/~([^~]+?)~/g, (inner) => <del className="line-through opacity-60">{inner}</del>);

  return <>{parts.map((part, i) => <React.Fragment key={i}>{part}</React.Fragment>)}</>;
};

export const detectAreaFromTitle = (titulo: string): Categoria => {
  const tituloLower = titulo.toLowerCase();

  // Palavras-chave para CLC
  const clcKeywords = ['licitação', 'licitacao', 'pregão', 'pregao', 'contrato', 'dispensa', 'inexigibilidade', 'compra', 'aquisição', 'aquisicao', 'processo'];

  // Palavras-chave para Assistência Estudantil
  const assistenciaKeywords = ['assistência', 'assistencia', 'estudantil', 'aluno', 'bolsa', 'auxílio', 'auxilio', 'permanência', 'permanencia'];

  // Verifica CLC primeiro
  if (clcKeywords.some(keyword => tituloLower.includes(keyword))) {
    return 'CLC';
  }

  // Verifica Assistência Estudantil
  if (assistenciaKeywords.some(keyword => tituloLower.includes(keyword))) {
    return 'ASSISTÊNCIA';
  }

  // Se não encontrar palavras-chave específicas, retorna GERAL
  return 'GERAL';
};
