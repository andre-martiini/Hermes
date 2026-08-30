// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';

// O componente assina `automations/hermes_robot` no mount. Sem estes mocks o
// render nao completa — o Firestore responde `permission-denied` e a tela fica
// vazia, que era um dos motivos de este arquivo nao passar.
vi.mock('../../firebase', () => ({ db: {} }));
vi.mock('firebase/firestore', () => ({
  doc: vi.fn(() => ({})),
  setDoc: vi.fn(async () => undefined),
  onSnapshot: vi.fn(() => () => undefined),
}));

import { onSnapshot } from 'firebase/firestore';
import { NFSeGenerator } from './NFSeGenerator';

Object.assign(navigator, { clipboard: { writeText: vi.fn() } });
global.fetch = vi.fn();

/**
 * Este arquivo existia e NUNCA rodava: o `npm test` enumerava os arquivos um a
 * um e ele nao estava na lista. Nesse tempo a interface do componente mudou
 * inteira — o titulo virou `NFSe_Data_Generator_V1`, os placeholders viraram
 * `0000,00` e `DDMMYYYY`, e o botao "gerar" sumiu porque o resultado passou a
 * ser calculado ao vivo.
 *
 * As AFIRMACOES do teste antigo, porem, continuavam certas: o gross-up
 * (`liquido / 0.89`), o INSS de 11% sobre o bruto e o codigo de servico 17.01
 * estao intactos no componente. Envelheceram os seletores, nao as regras — por
 * isso o teste foi reescrito contra a interface atual em vez de descartado.
 */
describe('NFSeGenerator', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(() => { cleanup(); });

  const abrir = () => render(<NFSeGenerator onClose={() => {}} />);
  const campoLiquido = () => screen.getByPlaceholderText('0000,00');

  it('renderiza sem depender do Firestore', () => {
    abrir();
    expect(screen.getByText('NFSe_Data_Generator_V1')).toBeTruthy();
  });

  it('faz o gross-up e o INSS a partir do valor liquido', () => {
    // 5000 / 0.89 = 5617,98 (bruto); 11% disso = 617,98 (INSS retido).
    // Sao os numeros do teste original: a regra nao mudou, so a tela.
    abrir();
    fireEvent.change(campoLiquido(), { target: { value: '5000' } });
    expect(screen.getByText('R$ 5.617,98')).toBeTruthy();
    expect(screen.getByText('R$ 617,98')).toBeTruthy();
  });

  it('expoe o codigo de servico 17.01', () => {
    abrir();
    fireEvent.change(campoLiquido(), { target: { value: '5000' } });
    expect(screen.getByText('17.01')).toBeTruthy();
  });

  it('o painel de saida so aparece depois de haver um valor liquido', () => {
    // Regressao concreta: `showResults` era um estado que nunca era ligado, e o
    // painel inteiro ficava inalcancavel. Este teste fixa as duas metades — o
    // estado vazio antes, o resultado depois.
    abrir();
    expect(screen.getByText('WAITING_FOR_DATA_STREAM')).toBeTruthy();
    fireEvent.change(campoLiquido(), { target: { value: '5000' } });
    expect(screen.queryByText('WAITING_FOR_DATA_STREAM')).toBeNull();
    expect(screen.getByText('17.01')).toBeTruthy();
  });

  it('copia o codigo de servico para a area de transferencia', () => {
    abrir();
    fireEvent.change(campoLiquido(), { target: { value: '5000' } });
    const codigo = screen.getByText('17.01');
    fireEvent.click(codigo.nextElementSibling as HTMLButtonElement);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('17.01');
  });

  it('nao libera a emissao antes de o tomador estar identificado', () => {
    // `runRobot` grava um pedido que faz um robo emitir NOTA FISCAL de verdade.
    // Com o painel destravado so pelo valor liquido, o botao ficava clicavel
    // antes da busca do CNPJ, e o pedido saia com `cnpj_tomador: ''` e a
    // descricao contendo o literal `[RAZAO SOCIAL]`.
    abrir();
    fireEvent.change(campoLiquido(), { target: { value: '5000' } });
    const emitir = screen.getByText(/EXECUTE_ROBOTIC_EMISSION/i).closest('button')!;
    expect(emitir.disabled).toBe(true);
  });

  it('libera a emissao depois de o CNPJ ser buscado', async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        cnpj: '12345678000195',
        razao_social: 'EMPRESA TESTE LTDA',
        municipio: 'SAO PAULO',
        uf: 'SP',
      }),
    });
    abrir();
    fireEvent.change(campoLiquido(), { target: { value: '5000' } });
    const campoCnpj = screen.getByPlaceholderText('00.000.000/0000-00');
    fireEvent.change(campoCnpj, { target: { value: '12.345.678/0001-95' } });
    fireEvent.click(campoCnpj.nextElementSibling as HTMLButtonElement);
    await waitFor(() => {
      const emitir = screen.getByText(/EXECUTE_ROBOTIC_EMISSION/i).closest('button')!;
      expect(emitir.disabled).toBe(false);
    });
  });

  const buscarCnpj = async (valor = '12.345.678/0001-95', razao = 'EMPRESA TESTE LTDA') => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        cnpj: valor.replace(/\D/g, ''),
        razao_social: razao,
        municipio: 'SAO PAULO',
        uf: 'SP',
      }),
    });
    const campo = screen.getByPlaceholderText('00.000.000/0000-00');
    fireEvent.change(campo, { target: { value: valor } });
    fireEvent.click(campo.nextElementSibling as HTMLButtonElement);
    // `getAllByText`: a razao social aparece no cartao do tomador E dentro da
    // descricao gerada.
    await waitFor(() => expect(screen.getAllByText(new RegExp(razao, 'i')).length).toBeGreaterThan(0));
    return campo;
  };

  it('editar o CNPJ depois da busca invalida o tomador', async () => {
    // Buscar A e trocar o campo para B mantinha `clientData` em A: a emissao
    // continuava liberada e a nota sairia para A com o formulario mostrando B.
    abrir();
    fireEvent.change(campoLiquido(), { target: { value: '5000' } });
    const campo = await buscarCnpj();
    expect(screen.getByText(/EXECUTE_ROBOTIC_EMISSION/i).closest('button')!.disabled).toBe(false);

    fireEvent.change(campo, { target: { value: '98.765.432/0001-10' } });
    expect(screen.getByText(/EXECUTE_ROBOTIC_EMISSION/i).closest('button')!.disabled).toBe(true);
    expect(screen.getByText(/COPY_STREAM/i).closest('button')!.disabled).toBe(true);
  });

  it('nao deixa copiar a descricao com o placeholder da razao social', async () => {
    // Travar so o robo nao basta: esta descricao colada a mao no portal produz
    // a mesma nota errada.
    abrir();
    fireEvent.change(campoLiquido(), { target: { value: '5000' } });
    expect(screen.getByText(/COPY_STREAM/i).closest('button')!.disabled).toBe(true);
    await buscarCnpj();
    expect(screen.getByText(/COPY_STREAM/i).closest('button')!.disabled).toBe(false);
  });

  it('status desconhecido libera de novo, para o botao nao travar apos o sucesso', async () => {
    // O contraponto do `it.each` acima: o bridge sinaliza o fim com um status
    // que este arquivo nao enumera, e tratar desconhecido como ocupado deixaria
    // o botao morto depois de uma emissao bem sucedida.
    //
    // O CNPJ PRECISA ser buscado nos dois casos: sem isso o botao ficaria
    // desabilitado por falta de tomador, e a assercao passaria pelo motivo
    // errado — foi o que aconteceu na primeira versao deste teste, que a
    // mutacao nao derrubava.
    (onSnapshot as any).mockImplementationOnce((_ref: any, cb: any) => {
      cb({ data: () => ({ status: 'done' }) });
      return () => undefined;
    });
    abrir();
    fireEvent.change(campoLiquido(), { target: { value: '5000' } });
    await buscarCnpj();
    expect(screen.getByText(/EXECUTE_ROBOTIC_EMISSION/i).closest('button')!.disabled).toBe(false);
  });

  it.each(['requested', 'processing', 'login_confirmed'])(
    'emissao travada enquanto o robo esta em %s',
    async (status) => {
      // Uma lista so de "robo ocupado". As duas versoes anteriores enumeravam
      // esses estados em dois lugares e divergiam — faltava `processing` num e
      // `login_confirmed` no outro, e nos dois casos o botao voltava habilitado
      // no meio de uma emissao em curso.
      (onSnapshot as any).mockImplementationOnce((_ref: any, cb: any) => {
        cb({ data: () => ({ status }) });
        return () => undefined;
      });
      abrir();
      fireEvent.change(campoLiquido(), { target: { value: '5000' } });
      await buscarCnpj();
      expect(screen.getByText(/EXECUTE_ROBOTIC_EMISSION|SIGNAL_DISPATCHED|ROBOT_ENGAGED/i)
        .closest('button')!.disabled).toBe(true);
    },
  );

  it('busca o CNPJ e mostra a razao social', async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        cnpj: '12345678000195',
        razao_social: 'EMPRESA TESTE LTDA',
        municipio: 'SAO PAULO',
        uf: 'SP',
      }),
    });
    abrir();
    const campoCnpj = screen.getByPlaceholderText('00.000.000/0000-00');
    fireEvent.change(campoCnpj, { target: { value: '12.345.678/0001-95' } });
    fireEvent.click(campoCnpj.nextElementSibling as HTMLButtonElement);
    await waitFor(() => {
      expect(screen.getByText(/EMPRESA TESTE LTDA/i)).toBeTruthy();
    });
  });
});
