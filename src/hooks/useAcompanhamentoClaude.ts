import { useEffect, useState } from 'react';
import { doc, onSnapshot } from 'firebase/firestore';
import { db } from '@/firebase';

// O leitor local da skill `reuniao` (scripts/acompanhar_reuniao.py) grava
// `acompanhamento_claude/{sessao}` a cada 30 s enquanto o Claude lê a reunião.
// Sem sinal há mais de 75 s, o Claude parou de ler (Monitor expirou, app
// fechado), mesmo que o documento ainda diga ativo.
const VALIDADE_MS = 75_000;

export const claudeEstaAcompanhando = (
  dados: { ativo?: boolean; visto_em?: { toMillis?: () => number } | string | null } | null | undefined,
  agoraMs: number,
): boolean => {
  if (!dados?.ativo || !dados.visto_em) return false;
  const vistoMs = typeof dados.visto_em === 'string'
    ? Date.parse(dados.visto_em)
    : dados.visto_em.toMillis?.() ?? NaN;
  return Number.isFinite(vistoMs) && agoraMs - vistoMs <= VALIDADE_MS;
};

export function useAcompanhamentoClaude(sessaoId: string | null): boolean {
  const [dados, setDados] = useState<Parameters<typeof claudeEstaAcompanhando>[0]>(null);
  const [agora, setAgora] = useState(() => Date.now());

  useEffect(() => {
    setDados(null);
    if (!sessaoId) return;
    const unsub = onSnapshot(
      doc(db, 'acompanhamento_claude', sessaoId),
      snap => setDados(snap.exists() ? (snap.data() as any) : null),
      () => setDados(null),
    );
    const relogio = window.setInterval(() => setAgora(Date.now()), 15_000);
    return () => { unsub(); window.clearInterval(relogio); };
  }, [sessaoId]);

  return claudeEstaAcompanhando(dados, agora);
}
