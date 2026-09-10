"""Testes do inventário tipado de ferramentas MCP (tools/inventory.py).

P03 passo 1 do plano de autonomia (docs/plano-hermes-autonomo-2026-09-06.md):
"criar inventário tipado por ferramenta: domínios, leitura/escrita,
reversibilidade, necessidade de rede, dados sensíveis, política e
verificador". Este teste não valida se CADA classificação está correta
(isso não é automatizável sem reler o código de cada tool) -- valida a
propriedade estrutural que o passo 1 pressupõe: paridade 1:1 com o
catálogo real, e nenhum campo obrigatório vazio/inconsistente.
"""

from __future__ import annotations

import unittest

from autonomy.contracts import ClasseEfeito
from tools import inventory, registry


class TestParidadeComCatalogo(unittest.TestCase):
    def test_toda_tool_do_catalogo_tem_entrada_no_inventario(self) -> None:
        faltando = registry.list_tool_names() - set(inventory._INVENTORY)
        self.assertEqual(
            faltando, set(),
            f"Tools no catálogo sem entrada no inventário: {sorted(faltando)}",
        )

    def test_nenhuma_entrada_orfa_no_inventario(self) -> None:
        orfas = set(inventory._INVENTORY) - registry.list_tool_names()
        self.assertEqual(
            orfas, set(),
            f"Entradas no inventário sem tool correspondente no catálogo: {sorted(orfas)}",
        )

    def test_get_inventory_entry_para_tool_inexistente_devolve_none(self) -> None:
        self.assertIsNone(inventory.get_inventory_entry("tool_que_nao_existe"))

    def test_list_inventory_devolve_copia_nao_o_dict_interno(self) -> None:
        copia = inventory.list_inventory()
        copia["tool_espuria"] = None
        self.assertNotIn("tool_espuria", inventory._INVENTORY)


class TestConsistenciaDosCampos(unittest.TestCase):
    """Nenhuma tool anunciada sem execução (aceite do P03): cada entrada usa
    tipos/enums válidos e não deixa campos textuais vazios."""

    def test_todos_os_campos_obrigatorios_preenchidos(self) -> None:
        for nome, entrada in inventory._INVENTORY.items():
            with self.subTest(tool=nome):
                self.assertTrue(entrada.dominio.strip(), f"{nome}: dominio vazio")
                self.assertIsInstance(entrada.leitura_escrita, inventory.LeituraEscrita)
                self.assertIsInstance(entrada.reversibilidade, inventory.Reversibilidade)
                self.assertIsInstance(entrada.necessidade_de_rede, bool)
                self.assertIsInstance(entrada.dados_sensiveis, bool)
                self.assertIsInstance(entrada.classe_efeito, ClasseEfeito)
                self.assertTrue(entrada.verificador.strip(), f"{nome}: verificador vazio")

    def test_rede_true_implica_servico_descrito(self) -> None:
        for nome, entrada in inventory._INVENTORY.items():
            if entrada.necessidade_de_rede:
                with self.subTest(tool=nome):
                    self.assertTrue(
                        entrada.rede_servico and entrada.rede_servico.strip(),
                        f"{nome}: necessidade_de_rede=True sem rede_servico descrito",
                    )

    def test_dados_sensiveis_true_implica_categoria_descrita(self) -> None:
        for nome, entrada in inventory._INVENTORY.items():
            if entrada.dados_sensiveis:
                with self.subTest(tool=nome):
                    self.assertTrue(
                        entrada.dados_sensiveis_categoria
                        and entrada.dados_sensiveis_categoria.strip(),
                        f"{nome}: dados_sensiveis=True sem categoria descrita",
                    )

    def test_leitura_pura_nao_e_classificada_como_reversivel_ou_irreversivel(self) -> None:
        """'Ferramenta somente leitura não é marcada como escrita por acidente'
        (aceite do P03) -- aqui a checagem análoga para reversibilidade: uma
        tool puramente de leitura não tem reversibilidade aplicável."""
        for nome, entrada in inventory._INVENTORY.items():
            if entrada.leitura_escrita is inventory.LeituraEscrita.LEITURA:
                with self.subTest(tool=nome):
                    self.assertEqual(
                        entrada.reversibilidade, inventory.Reversibilidade.NAO_APLICA,
                        f"{nome}: leitura pura com reversibilidade diferente de nao_aplica",
                    )

    def test_escrita_pura_nao_fica_nao_aplica(self) -> None:
        for nome, entrada in inventory._INVENTORY.items():
            if entrada.leitura_escrita is inventory.LeituraEscrita.ESCRITA:
                with self.subTest(tool=nome):
                    self.assertNotEqual(
                        entrada.reversibilidade, inventory.Reversibilidade.NAO_APLICA,
                        f"{nome}: tool de escrita com reversibilidade nao_aplica",
                    )

    def test_dominio_rede_e_enum_valido_ou_ausente(self) -> None:
        for nome, entrada in inventory._INVENTORY.items():
            with self.subTest(tool=nome):
                self.assertTrue(
                    entrada.dominio_rede is None or isinstance(entrada.dominio_rede, inventory.DominioRede),
                    f"{nome}: dominio_rede não é None nem DominioRede válido",
                )

    def test_dominio_rede_so_e_classificado_quando_ha_necessidade_de_rede(self) -> None:
        """`dominio_rede` (P03 sub-entrega 7/N) é o "qual" de `necessidade_de_rede`
        -- não faz sentido classificar o domínio de uma tool que não usa rede
        nenhuma."""
        for nome, entrada in inventory._INVENTORY.items():
            if entrada.dominio_rede is not None:
                with self.subTest(tool=nome):
                    self.assertTrue(
                        entrada.necessidade_de_rede,
                        f"{nome}: dominio_rede classificado sem necessidade_de_rede=True",
                    )

    def test_leitura_e_escrita_com_reversibilidade_nao_aplica_exige_nota_explicando(self) -> None:
        """Achado da revisão adversarial (sub-entrega P03 1/N): o filtro original só
        comparava contra ESCRITA (`is`), nunca contra LEITURA_E_ESCRITA -- ficava sem
        cobertura nenhuma a categoria mista. Aqui a invariante é mais específica: uma
        tool leitura_e_escrita SÓ pode ficar nao_aplica quando a escrita é um efeito
        colateral passivo, e isso precisa estar documentado em `nota` (não presumido)."""
        for nome, entrada in inventory._INVENTORY.items():
            if entrada.leitura_escrita is inventory.LeituraEscrita.LEITURA_E_ESCRITA:
                with self.subTest(tool=nome):
                    if entrada.reversibilidade is inventory.Reversibilidade.NAO_APLICA:
                        self.assertTrue(
                            entrada.nota and entrada.nota.strip(),
                            f"{nome}: leitura_e_escrita com reversibilidade nao_aplica precisa de "
                            "nota explicando por que a escrita é um efeito colateral passivo",
                        )


if __name__ == "__main__":
    unittest.main()
