import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { NFSeGenerator } from './NFSeGenerator';

// Mock clipboard API
Object.assign(navigator, {
  clipboard: {
    writeText: vi.fn(),
  },
});

global.fetch = vi.fn();

describe('NFSeGenerator Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders the component and calculates initial state correctly', () => {
    render(<NFSeGenerator onClose={() => {}} />);
    expect(screen.getByText('Gerador de Dados NFS-e')).toBeTruthy();
    
    // Check initial prompt state
    expect(screen.getByText('Preencha os dados ao lado para gerar o espelho da nota')).toBeTruthy();
  });

  it('accepts user input and generates valid output data with accurate math calculations', async () => {
    render(<NFSeGenerator onClose={() => {}} />);
    
    const inputValorLiquido = screen.getByPlaceholderText('Ex: 5000,00');
    const inputMesRef = screen.getByPlaceholderText('Ex: Janeiro/2026');

    // Valor Líquido = 5000
    fireEvent.change(inputValorLiquido, { target: { value: '5000' } });
    fireEvent.change(inputMesRef, { target: { value: 'Dezembro/2026' } });
    
    // Click Generate
    const btnGenerate = screen.getByText('Gerador Dados', { exact: false });
    fireEvent.click(btnGenerate);
    
    // Result elements
    await waitFor(() => {
      expect(screen.getByText('R$ 5.617,98')).toBeTruthy(); // Gross Up (Valor Bruto)
      expect(screen.getByText('R$ 617,98')).toBeTruthy();    // INSS Retido
      expect(screen.getByText('17.01')).toBeTruthy();          // Tax code
      expect(screen.getByText(/Desenvolvimento de soluções tecnológicas e consultoria/i)).toBeTruthy();
    });
  });

  it('fetches CNPJ data successfully and populates UI', async () => {
    const mockApiResponse = {
      cnpj: '12345678000195',
      razao_social: 'EMPRESA TESTE LTDA',
      municipio: 'SÃO PAULO',
      uf: 'SP',
    };
    
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockApiResponse,
    });
    
    render(<NFSeGenerator onClose={() => {}} />);
    const inputCnpj = screen.getByPlaceholderText('00.000.000/0000-00');
    fireEvent.change(inputCnpj, { target: { value: '12.345.678/0001-95' } });
    
    const fetchButton = (inputCnpj.nextElementSibling as HTMLButtonElement);
    expect(fetchButton.disabled).toBe(false);
    
    fireEvent.click(fetchButton);

    await waitFor(() => {
       expect(screen.getByText('EMPRESA TESTE LTDA')).toBeTruthy();
       expect(screen.getByText('SÃO PAULO - SP')).toBeTruthy();
    });
  });

  it('handles copy to clipboard correctly', async () => {
    render(<NFSeGenerator onClose={() => {}} />);
    
    fireEvent.change(screen.getByPlaceholderText('Ex: 5000,00'), { target: { value: '1000' } });
    fireEvent.change(screen.getByPlaceholderText('Ex: Janeiro/2026'), { target: { value: 'Jan/2026' } });
    fireEvent.change(screen.getByPlaceholderText('00.000.000/0000-00'), { target: { value: '12.345.678/0001-95' } });
    
    fireEvent.click(screen.getByText('Gerar Dados para NFS-e'));
    
    await waitFor(() => {
      expect(screen.getByText('17.01')).toBeTruthy();
    });

    const codigoElement = screen.getByText('17.01');
    const copyBtn = codigoElement.nextElementSibling as HTMLButtonElement;
    
    fireEvent.click(copyBtn);
    
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('17.01');
  });
});
