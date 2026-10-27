/** Subtítulos dos links discretos (Resumo financeiro, Saúde e telemetria) — tudo calculado na leitura. */

export const subtituloFinanceiro = (contasVencendo: number | null | undefined): string => {
    if (contasVencendo === null || contasVencendo === undefined) return 'Contas, cartão e investimentos';
    if (contasVencendo <= 0) return 'Sem pendências nas contas';
    return `${contasVencendo} ${contasVencendo === 1 ? 'conta vencendo' : 'contas vencendo'}`;
};

export interface SaudeDoDia {
    pesagemRegistrada: boolean;
    checkinManha: boolean;
    checkinNoite: boolean;
    /** Maior dor registrada ontem (0 a 10), ou `null` sem registro. */
    dorOntem: number | null;
}

/** "Pesagem e 2 check-ins de hoje pendentes · dor ontem 0". */
export const subtituloSaude = (s: SaudeDoDia): string => {
    const pendentes: string[] = [];
    if (!s.pesagemRegistrada) pendentes.push('pesagem');
    const checkins = Number(!s.checkinManha) + Number(!s.checkinNoite);
    if (checkins > 0) pendentes.push(`${checkins} ${checkins === 1 ? 'check-in' : 'check-ins'}`);
    const unidades = Number(!s.pesagemRegistrada) + checkins;
    const lista = pendentes.join(' e ');
    const hoje = pendentes.length === 0
        ? 'Tudo registrado hoje'
        : `${lista.charAt(0).toUpperCase()}${lista.slice(1)} de hoje ${unidades === 1 ? 'pendente' : 'pendentes'}`;
    return s.dorOntem === null ? hoje : `${hoje} · dor ontem ${s.dorOntem}`;
};
