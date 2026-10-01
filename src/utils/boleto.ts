/**
 * Linha digitável de boleto → código de barras, com conferência dos dígitos
 * verificadores e leitura de valor e vencimento.
 *
 * Dois formatos convivem: boleto bancário (47 dígitos) e conta de consumo ou
 * tributo, a "arrecadação" (48 dígitos, sempre começa com 8). Os dois viram o
 * mesmo código de barras de 44 dígitos, desenhado em Intercalado 2 de 5.
 */

export type TipoBoleto = 'bancario' | 'arrecadacao';

export interface AnaliseBoleto {
    tipo: TipoBoleto;
    valido: boolean;
    erro?: string;
    /** Os 44 dígitos do código de barras; só quando os verificadores conferem. */
    codigoBarras?: string;
    /** Em reais, quando o código traz valor. */
    valor?: number;
    /** YYYY-MM-DD; só boleto bancário com fator de vencimento. */
    vencimento?: string;
}

export const somenteDigitos = (texto: string | undefined | null): string => (texto || '').replace(/\D/g, '');

const modulo10 = (numero: string): number => {
    let soma = 0;
    let peso = 2;
    for (let i = numero.length - 1; i >= 0; i--) {
        let parcial = Number(numero[i]) * peso;
        if (parcial > 9) parcial = Math.floor(parcial / 10) + (parcial % 10);
        soma += parcial;
        peso = peso === 2 ? 1 : 2;
    }
    const resto = soma % 10;
    return resto === 0 ? 0 : 10 - resto;
};

const somaModulo11 = (numero: string): number => {
    let soma = 0;
    let peso = 2;
    for (let i = numero.length - 1; i >= 0; i--) {
        soma += Number(numero[i]) * peso;
        peso = peso === 9 ? 2 : peso + 1;
    }
    return soma;
};

/** DV geral do boleto bancário: 0, 10 e 11 viram 1. */
const modulo11Bancario = (numero: string): number => {
    const dv = 11 - (somaModulo11(numero) % 11);
    return dv === 0 || dv === 10 || dv === 11 ? 1 : dv;
};

/** Arrecadação: resto 0 ou 1 dá DV 0. */
const modulo11Arrecadacao = (numero: string): number => {
    const dv = 11 - (somaModulo11(numero) % 11);
    return dv >= 10 ? 0 : dv;
};

const DIA_MS = 86_400_000;
// Fator 1000 era 03/07/2000 (base 07/10/1997). Em 22/02/2025 o fator chegou a
// 9999 e recomeçou em 1000 (regra Febraban); o mesmo fator aponta para duas
// datas, e vale a mais próxima de hoje.
const BASE_ANTIGA = Date.UTC(1997, 9, 7);
const BASE_NOVA_FATOR_1000 = Date.UTC(2025, 1, 22);

const isoUtc = (ms: number) => new Date(ms).toISOString().slice(0, 10);

export const vencimentoDoFator = (fator: number, hoje: Date = new Date()): string | undefined => {
    if (!fator) return undefined;
    const candidatos = [BASE_ANTIGA + fator * DIA_MS];
    if (fator >= 1000) candidatos.push(BASE_NOVA_FATOR_1000 + (fator - 1000) * DIA_MS);
    const agora = hoje.getTime();
    candidatos.sort((a, b) => Math.abs(a - agora) - Math.abs(b - agora));
    return isoUtc(candidatos[0]);
};

const valorEmReais = (digitos: string): number | undefined => {
    const centavos = Number(digitos);
    return centavos > 0 ? centavos / 100 : undefined;
};

const ERRO_DV = 'Os dígitos verificadores não conferem; confira o número colado.';

const analisarBancarioPeloCodigo = (codigo: string, hoje: Date): AnaliseBoleto => {
    const dvGeral = modulo11Bancario(codigo.slice(0, 4) + codigo.slice(5));
    if (dvGeral !== Number(codigo[4])) return { tipo: 'bancario', valido: false, erro: ERRO_DV };
    return {
        tipo: 'bancario',
        valido: true,
        codigoBarras: codigo,
        valor: valorEmReais(codigo.slice(9, 19)),
        vencimento: vencimentoDoFator(Number(codigo.slice(5, 9)), hoje),
    };
};

const analisarArrecadacaoPeloCodigo = (codigo: string): AnaliseBoleto => {
    const identificador = codigo[2];
    const modulo = identificador === '6' || identificador === '7' ? modulo10
        : identificador === '8' || identificador === '9' ? modulo11Arrecadacao : null;
    if (!modulo) {
        return { tipo: 'arrecadacao', valido: false, erro: 'O terceiro dígito de uma conta de consumo deve ser 6, 7, 8 ou 9; confira o número colado.' };
    }
    if (modulo(codigo.slice(0, 3) + codigo.slice(4)) !== Number(codigo[3])) {
        return { tipo: 'arrecadacao', valido: false, erro: ERRO_DV };
    }
    // 6 e 8: valor efetivo em reais. 7 e 9: valor de referência (índice), não dinheiro.
    const temValor = identificador === '6' || identificador === '8';
    return {
        tipo: 'arrecadacao',
        valido: true,
        codigoBarras: codigo,
        valor: temValor ? valorEmReais(codigo.slice(4, 15)) : undefined,
    };
};

/**
 * Analisa o que foi colado no campo: linha digitável (47 ou 48 dígitos) ou o
 * próprio código de barras (44). Pontos, espaços e traços são ignorados.
 * Devolve null quando não há dígito nenhum.
 */
export const analisarBoleto = (texto: string | undefined | null, hoje: Date = new Date()): AnaliseBoleto | null => {
    const d = somenteDigitos(texto);
    if (!d) return null;

    if (d.length === 44) {
        return d[0] === '8' ? analisarArrecadacaoPeloCodigo(d) : analisarBancarioPeloCodigo(d, hoje);
    }

    if (d.length === 47 && d[0] !== '8') {
        const campos: Array<[string, string]> = [
            [d.slice(0, 9), d[9]],
            [d.slice(10, 20), d[20]],
            [d.slice(21, 31), d[31]],
        ];
        if (campos.some(([numero, dv]) => modulo10(numero) !== Number(dv))) {
            return { tipo: 'bancario', valido: false, erro: ERRO_DV };
        }
        const codigo = d.slice(0, 4) + d[32] + d.slice(33, 47) + d.slice(4, 9) + d.slice(10, 20) + d.slice(21, 31);
        return analisarBancarioPeloCodigo(codigo, hoje);
    }

    if (d.length === 48 && d[0] === '8') {
        const blocos = [0, 12, 24, 36].map((i) => d.slice(i, i + 11));
        const dvs = [11, 23, 35, 47].map((i) => Number(d[i]));
        const codigo = blocos.join('');
        const identificador = codigo[2];
        const modulo = identificador === '6' || identificador === '7' ? modulo10
            : identificador === '8' || identificador === '9' ? modulo11Arrecadacao : null;
        if (modulo && blocos.some((bloco, i) => modulo(bloco) !== dvs[i])) {
            return { tipo: 'arrecadacao', valido: false, erro: ERRO_DV };
        }
        return analisarArrecadacaoPeloCodigo(codigo);
    }

    const tipo: TipoBoleto = d[0] === '8' ? 'arrecadacao' : 'bancario';
    return {
        tipo,
        valido: false,
        erro: `A linha digitável tem 47 dígitos (boleto bancário) ou 48 (conta de consumo ou tributo); este número tem ${d.length}.`,
    };
};

const PADROES_ITF = ['nnwwn', 'wnnnw', 'nwnnw', 'wwnnn', 'nnwnw', 'wnwnn', 'nwwnn', 'nnnww', 'wnnwn', 'nwnwn'];
export const LARGA_ITF = 3;

/**
 * Larguras alternadas (barra, espaço, barra...) do Intercalado 2 de 5, em
 * módulos: 1 é fina, LARGA_ITF é larga. Inclui início e fim, não a margem.
 * O primeiro dígito de cada par vai nas barras e o segundo nos espaços.
 */
export const larguraItf = (digitos: string): number[] => {
    if (!/^\d+$/.test(digitos) || digitos.length % 2 !== 0) {
        throw new Error('O Intercalado 2 de 5 precisa de um número par de dígitos.');
    }
    const largura = (c: string) => (c === 'w' ? LARGA_ITF : 1);
    const saida = [1, 1, 1, 1];
    for (let i = 0; i < digitos.length; i += 2) {
        const barras = PADROES_ITF[Number(digitos[i])];
        const espacos = PADROES_ITF[Number(digitos[i + 1])];
        for (let k = 0; k < 5; k++) saida.push(largura(barras[k]), largura(espacos[k]));
    }
    saida.push(LARGA_ITF, 1, 1);
    return saida;
};

export const descreverBoleto = (analise: AnaliseBoleto): string => {
    const partes = [analise.tipo === 'bancario' ? 'Boleto bancário' : 'Conta de consumo ou tributo'];
    if (analise.valor !== undefined) {
        partes.push(analise.valor.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }));
    }
    if (analise.vencimento) {
        const [ano, mes, dia] = analise.vencimento.split('-');
        partes.push(`vence ${dia}/${mes}/${ano}`);
    }
    return partes.join(' · ');
};
