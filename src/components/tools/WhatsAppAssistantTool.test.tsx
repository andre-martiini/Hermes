// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WhatsAppAssistantTool } from './WhatsAppAssistantTool';

const { askWhatsAppAssistantMock } = vi.hoisted(() => ({
  askWhatsAppAssistantMock: vi.fn(),
}));

vi.mock('../../utils/whatsappAssistant', () => ({
  askWhatsAppAssistant: askWhatsAppAssistantMock,
}));

vi.mock('../ui/UIComponents', () => ({
  AutoExpandingTextarea: (props: any) => <textarea {...props} />,
}));

const createDeferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

describe('WhatsAppAssistantTool', () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    localStorage.clear();
    askWhatsAppAssistantMock.mockReset();
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      writable: true,
      value: vi.fn(),
    });
  });

  it('mostra o indicador de digitacao e renderiza markdown/contexto apos a resposta', async () => {
    const deferred = createDeferred<any>();
    askWhatsAppAssistantMock.mockReturnValueOnce(deferred.promise);
    const showToast = vi.fn();

    render(<WhatsAppAssistantTool onBack={vi.fn()} showToast={showToast} />);

    fireEvent.change(
      screen.getAllByPlaceholderText(/encontre o grupo da obra/i)[0],
      { target: { value: 'Procure o grupo da obra' } },
    );
    fireEvent.click(screen.getByRole('button', { name: /enviar/i }));

    expect(screen.getByRole('status', { name: /hermes esta respondendo/i })).toBeInTheDocument();

    deferred.resolve({
      markdown: '## Resumo\n- Pendencia principal\n- Proximo passo',
      attachments: [],
      context: {
        selectedChatId: 'chat-obra',
        selectedChatName: 'Obra Campus',
        memorySummary: 'Grupo em foco: Obra Campus. Tema recente: pendencia, obra.',
        lastSearchKeywords: ['pendencia', 'obra'],
        resultCount: 2,
      },
    });

    await waitFor(() => expect(screen.getAllByText('Obra Campus').length).toBeGreaterThan(0));
    expect(screen.getByText('Resumo')).toBeInTheDocument();
    expect(screen.getByText('Pendencia principal')).toBeInTheDocument();
    expect(screen.getByText(/Foco recente: pendencia, obra/i)).toBeInTheDocument();
    expect(showToast).not.toHaveBeenCalled();
  });

  it('permite fixar um chat candidato localmente pela interface', async () => {
    askWhatsAppAssistantMock.mockResolvedValueOnce({
      markdown: 'Encontrei mais de um chat parecido.',
      attachments: [],
      context: {
        candidateChats: [
          { chatId: 'chat-obra', chatName: 'Obra Campus', isGroup: true, score: 0.71 },
          { chatId: 'chat-centro', chatName: 'Obra Centro', isGroup: true, score: 0.66 },
        ],
        pendingDisambiguation: true,
        memorySummary: 'Selecao de chat ainda pendente.',
      },
    });
    const showToast = vi.fn();

    render(<WhatsAppAssistantTool onBack={vi.fn()} showToast={showToast} />);

    fireEvent.change(
      screen.getAllByPlaceholderText(/encontre o grupo da obra/i)[0],
      { target: { value: 'Abra o grupo da obra' } },
    );
    fireEvent.click(screen.getByRole('button', { name: /enviar/i }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Obra Campus' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Obra Campus' }));

    await waitFor(() => expect(screen.queryByText('confirmacao pendente')).not.toBeInTheDocument());
    expect(screen.getAllByText('Obra Campus').length).toBeGreaterThan(0);
    expect(showToast).toHaveBeenCalledWith('Contexto fixado em Obra Campus.', 'info');
  });
});
