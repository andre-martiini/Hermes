import { describe, expect, it } from 'vitest';
import type { EstrategiaMarco } from '../../types';
import { paraGravar, paraRascunho } from './itensEstrategia';
import { idLegado } from './perfilEstrategia';

const marco: EstrategiaMarco & { campo_futuro: string } = {
    id: 'm1', descricao: '91,7 kg', concluido: false, registros: [],
    dataAlvo: '2026-11-30', esperado: { peso: 91.7, cintura: 108 }, campo_futuro: 'não some',
};

describe('marcos da tela de estratégia: abrir e salvar não apaga o perfil', () => {
    it('ida e volta preservam dataAlvo, esperado e campo desconhecido', () => {
        const [gravado] = paraGravar('marco', paraRascunho('marco', [marco]));
        expect(gravado).toMatchObject({ dataAlvo: '2026-11-30', esperado: { peso: 91.7, cintura: 108 }, campo_futuro: 'não some' });
    });

    it('editar a descrição ou concluir no rascunho mantém o perfil', () => {
        const rascunho = paraRascunho('marco', [marco]).map(m => ({ ...m, descricao: 'revisto', concluido: true }));
        const [gravado] = paraGravar('marco', rascunho);
        expect(gravado).toMatchObject({ descricao: 'revisto', concluido: true, dataAlvo: '2026-11-30', esperado: { peso: 91.7, cintura: 108 } });
        expect(gravado.dataConclusao).toBeTruthy();
    });

    it('evidência vazia não é gravada; preenchida, sem espaços', () => {
        const [semEvidencia] = paraGravar('marco', paraRascunho('marco', [marco]));
        expect('evidencia' in semEvidencia).toBe(false);
        const [comEvidencia] = paraGravar('marco', [{ ...marco, evidencia: '  pesagem de 30/11 ' }]);
        expect(comEvidencia.evidencia).toBe('pesagem de 30/11');
    });

    it('marco legado em texto ganha o mesmo id que o MCP usa', () => {
        const [legado] = paraRascunho('marco', ['Chegar a 90 kg']);
        expect(legado.id).toBe(idLegado('marco', 0, 'Chegar a 90 kg'));
        expect(paraRascunho('marco', ['Chegar a 90 kg'])[0].id).toBe(legado.id);
    });
});
