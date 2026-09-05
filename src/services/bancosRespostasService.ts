// src/services/bancosRespostasService.ts
// Acesso ao Firestore dos bancos de resposta. As regras de conteúdo ficam em
// src/utils/bancosRespostas.ts — aqui é só ida e volta ao banco.

import { db } from '@/firebase';
import {
  addDoc,
  collection,
  deleteDoc,
  doc,
  getDocs,
  orderBy,
  query,
  updateDoc,
} from 'firebase/firestore';
import { limparCartao, type BancoRespostas } from '../utils/bancosRespostas';
import type { CartaoResposta } from '../utils/cartoesReuniao';

const COLECAO = 'bancos_respostas';

export const listarBancos = async (): Promise<BancoRespostas[]> => {
  const snapshot = await getDocs(query(collection(db, COLECAO), orderBy('atualizadoEm', 'desc')));
  return snapshot.docs.map((d) => {
    const dados = d.data();
    return {
      id: d.id,
      nome: (dados.nome as string) || 'Banco sem nome',
      descricao: (dados.descricao as string) || undefined,
      cartoes: ((dados.cartoes as CartaoResposta[]) ?? []).map(limparCartao),
      criadoEm: (dados.criadoEm as string) || '',
      atualizadoEm: (dados.atualizadoEm as string) || '',
      eventoCalendarId: (dados.eventoCalendarId as string) || (dados.evento_calendar_id as string) || undefined,
    };
  });
};

export const criarBanco = async (
  nome: string,
  cartoes: readonly CartaoResposta[],
  descricao?: string,
  eventoCalendarId?: string,
): Promise<string> => {
  const agora = new Date().toISOString();
  const ref = await addDoc(collection(db, COLECAO), {
    nome: nome.trim() || 'Banco sem nome',
    ...(descricao?.trim() ? { descricao: descricao.trim() } : {}),
    ...(eventoCalendarId?.trim() ? { eventoCalendarId: eventoCalendarId.trim() } : {}),
    cartoes: cartoes.map(limparCartao),
    criadoEm: agora,
    atualizadoEm: agora,
  });
  return ref.id;
};

export const atualizarBanco = async (
  id: string,
  nome: string,
  cartoes: readonly CartaoResposta[],
  descricao?: string,
  eventoCalendarId?: string,
): Promise<void> => {
  await updateDoc(doc(db, COLECAO, id), {
    nome: nome.trim() || 'Banco sem nome',
    descricao: descricao?.trim() ?? '',
    eventoCalendarId: eventoCalendarId?.trim() || null,
    cartoes: cartoes.map(limparCartao),
    atualizadoEm: new Date().toISOString(),
  });
};

export const removerBanco = async (id: string): Promise<void> => {
  await deleteDoc(doc(db, COLECAO, id));
};
