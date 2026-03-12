import { describe, expect, it } from 'vitest';
import type { WhatsAppAssistantResponse } from '@/utils/whatsappAssistant';
import {
  createAssistantSession,
  createInitialAssistantState,
  getSessionPreview,
  prepareSessionsForStorage,
  toConversationHistory,
  whatsappAssistantReducer,
} from './whatsappAssistantState';

const buildResponse = (overrides: Partial<WhatsAppAssistantResponse> = {}): WhatsAppAssistantResponse => ({
  markdown: 'Resposta',
  attachments: [],
  context: {},
  ...overrides,
});

describe('whatsappAssistantReducer', () => {
  it('preserva memoria anterior quando a nova resposta atualiza apenas parte do contexto', () => {
    const firstState = createInitialAssistantState();
    const submitted = whatsappAssistantReducer(firstState, {
      type: 'submitPrompt',
      sessionId: firstState.activeSessionId,
      text: 'Procure o grupo da obra',
      now: '2026-03-12T09:00:00.000Z',
      messageId: 'user-1',
    });

    const withFirstResponse = whatsappAssistantReducer(submitted, {
      type: 'resolvePrompt',
      sessionId: submitted.activeSessionId,
      now: '2026-03-12T09:00:04.000Z',
      messageId: 'assistant-1',
      response: buildResponse({
        markdown: 'Grupo Obra Campus selecionado.',
        context: {
          selectedChatId: 'chat-obra',
          selectedChatName: 'Obra Campus',
          lastSearchKeywords: ['pendencia', 'obra'],
          memorySummary: 'Grupo em foco: Obra Campus. Tema: pendencia, obra.',
          resultCount: 12,
        },
      }),
    });

    const merged = whatsappAssistantReducer(withFirstResponse, {
      type: 'resolvePrompt',
      sessionId: withFirstResponse.activeSessionId,
      now: '2026-03-12T09:01:00.000Z',
      messageId: 'assistant-2',
      response: buildResponse({
        markdown: 'Hoje houve uma entrega e duas pendencias.',
        context: {
          searchScopeLabel: 'hoje',
          resultCount: 3,
        },
      }),
    });

    const activeSession = merged.sessions[0];
    expect(activeSession.context.selectedChatId).toBe('chat-obra');
    expect(activeSession.context.selectedChatName).toBe('Obra Campus');
    expect(activeSession.context.lastSearchKeywords).toEqual(['pendencia', 'obra']);
    expect(activeSession.context.searchScopeLabel).toBe('hoje');
    expect(activeSession.context.resultCount).toBe(3);
  });

  it('mantem o draft por sessao e promove a sessao ativa apos nova atividade', () => {
    const firstSession = createAssistantSession('2026-03-12T08:00:00.000Z');
    const secondSession = createAssistantSession('2026-03-12T08:10:00.000Z');
    const initialState = {
      sessions: [firstSession, secondSession],
      activeSessionId: secondSession.id,
    };

    const withDraft = whatsappAssistantReducer(initialState, {
      type: 'updateDraft',
      sessionId: secondSession.id,
      value: 'rascunho',
    });

    const submitted = whatsappAssistantReducer(withDraft, {
      type: 'submitPrompt',
      sessionId: secondSession.id,
      text: 'Resumo do grupo',
      now: '2026-03-12T08:11:00.000Z',
      messageId: 'user-2',
    });

    expect(submitted.sessions[0].id).toBe(secondSession.id);
    expect(submitted.sessions[0].draft).toBe('');
    expect(submitted.sessions[1].draft).toBe('');
  });

  it('prepara o armazenamento com limite de sessoes e mensagens', () => {
    const oversizedSession = createAssistantSession('2026-03-12T07:00:00.000Z');
    oversizedSession.messages = Array.from({ length: 96 }, (_, index) => ({
      id: `msg-${index}`,
      role: index % 2 === 0 ? 'assistant' : 'user',
      text: `Mensagem ${index}`,
      timestamp: `2026-03-12T07:${String(index).padStart(2, '0')}:00.000Z`,
    }));
    oversizedSession.status = 'loading';
    oversizedSession.draft = 'x'.repeat(5000);

    const stored = prepareSessionsForStorage(
      Array.from({ length: 14 }, (_, index) => ({
        ...oversizedSession,
        id: `chat-${index}`,
      })),
    );

    expect(stored).toHaveLength(12);
    expect(stored[0].messages).toHaveLength(80);
    expect(stored[0].status).toBe('idle');
    expect(stored[0].draft).toHaveLength(4000);
  });

  it('gera historico enxuto e preview legivel da sessao', () => {
    const session = createAssistantSession('2026-03-12T06:00:00.000Z');
    session.messages.push(
      {
        id: 'user-3',
        role: 'user',
        text: 'Primeira pergunta',
        timestamp: '2026-03-12T06:10:00.000Z',
      },
      {
        id: 'assistant-3',
        role: 'assistant',
        text: 'Resposta longa com bastante contexto e detalhes sobre a obra e os anexos disponíveis.',
        timestamp: '2026-03-12T06:10:05.000Z',
      },
    );

    const history = toConversationHistory(session.messages);
    expect(history.at(-1)?.text).toContain('Resposta longa');
    expect(getSessionPreview(session)).toContain('Resposta longa');
  });
});
