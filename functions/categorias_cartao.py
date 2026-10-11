"""Categoria e natureza dos lancamentos do cartao, por regra de estabelecimento.

As regras sao aplicadas na LEITURA (consultar_fatura_cartao), nao gravadas em
cada lancamento: corrigir uma regra vale para o passado sem regravar nada.

Duas camadas:
- REGRAS_PADRAO, aqui no codigo, montadas a partir dos estabelecimentos reais
  das faturas (set/2025 a out/2026);
- regras do dono em `cartao_regras_categoria/{padrao}`, que acrescentam,
  substituem uma padrao com o mesmo padrao, ou a desligam (`ativo: false`).

Natureza: "pessoal", "projeto" ou "misto". IA e software e "misto" por decisao
do dono (09/10/2026): uso profissional e pessoal, sem separar.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

COLECAO = "cartao_regras_categoria"
SEM_CATEGORIA = "Sem categoria"
NATUREZAS = ("pessoal", "projeto", "misto")

CATEGORIAS = (
    "Mercado",
    "Restaurantes e lanches",
    "Transporte",
    "IA e software",
    "Assinaturas e apps",
    "Saúde e farmácia",
    "Casa e construção",
    "Compras online",
    "Vestuário e calçados",
    "Beleza e cuidados",
    "Esporte e educação",
    "Viagem e lazer",
    "Telefonia e eletrônicos",
    "Serviços e taxas",
)

# (padrao, categoria, natureza, prioridade). Prioridade 0 = regra generica de
# marketplace/plataforma: so vale se nenhuma especifica casar.
_P = "pessoal"
REGRAS_PADRAO: tuple[tuple[str, str, str, int], ...] = (
    # IA e software (misto)
    ("openai", "IA e software", "misto", 1), ("chatgpt", "IA e software", "misto", 1),
    ("anthropic", "IA e software", "misto", 1), ("claude", "IA e software", "misto", 1),
    ("google cloud", "IA e software", "misto", 1), ("elevenlabs", "IA e software", "misto", 1),
    ("aqua voice", "IA e software", "misto", 1), ("typesafe", "IA e software", "misto", 1),
    ("microsoft", "IA e software", "misto", 1), ("dl google kling", "IA e software", "misto", 1),
    # Assinaturas e apps
    ("disney", "Assinaturas e apps", _P, 1), ("telecine", "Assinaturas e apps", _P, 1),
    ("spotify", "Assinaturas e apps", _P, 1), ("amazon prime", "Assinaturas e apps", _P, 1),
    ("amazonprimebr", "Assinaturas e apps", _P, 1), ("globoplay", "Assinaturas e apps", _P, 1),
    ("smiles", "Assinaturas e apps", _P, 1), ("youtube", "Assinaturas e apps", _P, 1),
    ("youtub", "Assinaturas e apps", _P, 1), ("dl google", "Assinaturas e apps", _P, 0),
    # Transporte
    ("uber", "Transporte", _P, 1), ("posto", "Transporte", _P, 1),
    ("auto servico", "Transporte", _P, 1), ("viacao", "Transporte", _P, 1),
    ("jet patinetes", "Transporte", _P, 1), ("efvm", "Transporte", _P, 1),
    ("moovit", "Transporte", _P, 1), ("tom tom", "Transporte", _P, 1),
    # Mercado
    ("supermercado", "Mercado", _P, 1), ("supermercados", "Mercado", _P, 1),
    ("extrabom", "Mercado", _P, 1), ("perim", "Mercado", _P, 1), ("atacadao", "Mercado", _P, 1),
    ("carone", "Mercado", _P, 1), ("sup", "Mercado", _P, 1), ("mercadinho", "Mercado", _P, 1),
    ("mini mercado", "Mercado", _P, 1), ("mercado soma", "Mercado", _P, 1),
    ("mercado sete", "Mercado", _P, 1), ("horti", "Mercado", _P, 1), ("hortifruti", "Mercado", _P, 1),
    ("hortalicas", "Mercado", _P, 1), ("hortalicaswol", "Mercado", _P, 1), ("feira", "Mercado", _P, 1),
    ("varejao", "Mercado", _P, 1), ("baratao", "Mercado", _P, 1), ("condimentos", "Mercado", _P, 1),
    ("greenvix", "Mercado", _P, 1), ("bubach", "Mercado", _P, 1), ("leodoqueijo", "Mercado", _P, 1),
    ("frescoco", "Mercado", _P, 1), ("distribuidora pollet", "Mercado", _P, 1),
    # Restaurantes e lanches
    ("ifd", "Restaurantes e lanches", _P, 1), ("ifood", "Restaurantes e lanches", _P, 1),
    ("restaurante", "Restaurantes e lanches", _P, 1), ("pizzaria", "Restaurantes e lanches", _P, 1),
    ("padaria", "Restaurantes e lanches", _P, 1), ("panificadora", "Restaurantes e lanches", _P, 1),
    ("cafe", "Restaurantes e lanches", _P, 1), ("coffee", "Restaurantes e lanches", _P, 1),
    ("goldcafes", "Restaurantes e lanches", _P, 1), ("churrasc", "Restaurantes e lanches", _P, 1),
    ("churrascaria", "Restaurantes e lanches", _P, 1), ("coronel picanha", "Restaurantes e lanches", _P, 1),
    ("picanha", "Restaurantes e lanches", _P, 1), ("bob s", "Restaurantes e lanches", _P, 1),
    ("bobs", "Restaurantes e lanches", _P, 1), ("subway", "Restaurantes e lanches", _P, 1),
    ("pastel", "Restaurantes e lanches", _P, 1), ("lanches", "Restaurantes e lanches", _P, 1),
    ("tatalanches", "Restaurantes e lanches", _P, 1), ("sena gourmet", "Restaurantes e lanches", _P, 1),
    ("cacau show", "Restaurantes e lanches", _P, 1), ("lindt", "Restaurantes e lanches", _P, 1),
    ("gelato", "Restaurantes e lanches", _P, 1), ("doces", "Restaurantes e lanches", _P, 1),
    ("garapa", "Restaurantes e lanches", _P, 1), ("bolos", "Restaurantes e lanches", _P, 1),
    ("pipoca", "Restaurantes e lanches", _P, 1), ("acai", "Restaurantes e lanches", _P, 1),
    ("self service", "Restaurantes e lanches", _P, 1), ("grazie e vero", "Restaurantes e lanches", _P, 1),
    ("monterrey", "Restaurantes e lanches", _P, 1), ("beerexpress", "Restaurantes e lanches", _P, 1),
    ("hunger", "Restaurantes e lanches", _P, 1), ("ki delicia", "Restaurantes e lanches", _P, 1),
    ("rjrestaurante", "Restaurantes e lanches", _P, 1), ("spg bossa", "Restaurantes e lanches", _P, 1),
    # Saude e farmacia
    ("drogaria", "Saúde e farmácia", _P, 1), ("drogarias", "Saúde e farmácia", _P, 1),
    ("drogasil", "Saúde e farmácia", _P, 1), ("drogazilda", "Saúde e farmácia", _P, 1),
    ("drogariaribeiro", "Saúde e farmácia", _P, 1), ("farmacia", "Saúde e farmácia", _P, 1),
    ("pharma", "Saúde e farmácia", _P, 1), ("fermacoltda", "Saúde e farmácia", _P, 1),
    ("nutreline", "Saúde e farmácia", _P, 1),
    # Casa e construcao
    ("obramax", "Casa e construção", _P, 1), ("tintas", "Casa e construção", _P, 1),
    ("friovixco", "Casa e construção", _P, 1), ("ar con", "Casa e construção", _P, 1),
    ("moveis", "Casa e construção", _P, 1), ("fienimoveise", "Casa e construção", _P, 1),
    ("constrular", "Casa e construção", _P, 1), ("casa rara", "Casa e construção", _P, 1),
    ("utilidades", "Casa e construção", _P, 1), ("galpoutilidade", "Casa e construção", _P, 1),
    ("embalagens", "Casa e construção", _P, 1), ("tl gas", "Casa e construção", _P, 1),
    ("gecore", "Casa e construção", _P, 1), ("concertodemaquinas", "Casa e construção", _P, 1),
    ("casa cardoso", "Casa e construção", _P, 1),
    # Vestuario e calcados
    ("riachuelo", "Vestuário e calçados", _P, 1), ("calcados", "Vestuário e calçados", _P, 1),
    ("centauro", "Vestuário e calçados", _P, 1), ("territorio da moda", "Vestuário e calçados", _P, 1),
    ("noivas", "Vestuário e calçados", _P, 1), ("bagaggio", "Vestuário e calçados", _P, 1),
    ("lojas avenida", "Vestuário e calçados", _P, 1), ("cea", "Vestuário e calçados", _P, 1),
    ("malubaby", "Vestuário e calçados", _P, 1), ("joalheria", "Vestuário e calçados", _P, 1),
    ("totebag", "Vestuário e calçados", _P, 1), ("aviamentos", "Vestuário e calçados", _P, 1),
    ("confecesaguila", "Vestuário e calçados", _P, 1), ("modantima", "Vestuário e calçados", _P, 1),
    # Beleza e cuidados
    ("oboticario", "Beleza e cuidados", _P, 1), ("cosmeticos", "Beleza e cuidados", _P, 1),
    ("barbearia", "Beleza e cuidados", _P, 1), ("salaomarina", "Beleza e cuidados", _P, 1),
    ("helicanails", "Beleza e cuidados", _P, 1), ("cgcbeleza", "Beleza e cuidados", _P, 1),
    ("gbocosmeticos", "Beleza e cuidados", _P, 1),
    # Esporte e educacao
    ("iron academia", "Esporte e educação", _P, 1), ("projeto caveira", "Esporte e educação", _P, 1),
    ("decathlon", "Esporte e educação", _P, 1), ("papelaria", "Esporte e educação", _P, 1),
    ("republicamaterial", "Esporte e educação", _P, 1), ("fazenda musica", "Esporte e educação", _P, 1),
    ("take kids", "Esporte e educação", _P, 1),
    # Viagem e lazer
    ("cvc", "Viagem e lazer", _P, 1), ("hotel", "Viagem e lazer", _P, 1), ("plenotel", "Viagem e lazer", _P, 1),
    ("cinemark", "Viagem e lazer", _P, 1), ("barraca", "Viagem e lazer", _P, 1),
    ("barracadoleo", "Viagem e lazer", _P, 1), ("barracadepeixedake", "Viagem e lazer", _P, 1),
    ("onticket", "Viagem e lazer", _P, 1), ("equilibriumfestiv", "Viagem e lazer", _P, 1),
    # Telefonia e eletronicos
    ("claro", "Telefonia e eletrônicos", _P, 1), ("vivo", "Telefonia e eletrônicos", _P, 1),
    ("celular", "Telefonia e eletrônicos", _P, 1), ("play cell", "Telefonia e eletrônicos", _P, 1),
    ("casa da case", "Telefonia e eletrônicos", _P, 1), ("brtecheletroni", "Telefonia e eletrônicos", _P, 1),
    ("terabyte", "Telefonia e eletrônicos", _P, 1), ("tntinfoco", "Telefonia e eletrônicos", _P, 1),
    ("bauruinfo", "Telefonia e eletrônicos", _P, 1), ("shpstecnologia", "Telefonia e eletrônicos", _P, 1),
    # Servicos e taxas
    ("cra es", "Serviços e taxas", _P, 1),
    # Plataformas genericas (so quando nada especifico casa)
    ("amazon", "Compras online", _P, 0), ("amazonmktplc", "Compras online", _P, 0),
    ("amazonmktcpi", "Compras online", _P, 0), ("mercadolivre", "Compras online", _P, 0),
    ("mercado mercadolivre", "Compras online", _P, 0), ("mp mercadolivre", "Compras online", _P, 0),
    ("ec mercadolivre", "Compras online", _P, 0), ("shopee", "Compras online", _P, 0),
    ("americanas", "Compras online", _P, 0), ("melimais", "Compras online", _P, 0),
    ("novaexpress", "Compras online", _P, 0), ("lasa", "Compras online", _P, 0),
)


def normalizar(texto) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or ""))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c)).lower()
    # "DROGASIL3655" -> "drogasil 3655": a filial grudada no nome nao esconde a loja.
    sem_acento = re.sub(r"(?<=[a-z])(?=[0-9])|(?<=[0-9])(?=[a-z])", " ", sem_acento)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sem_acento).split())


def _regra(padrao, categoria, natureza, prioridade, origem):
    return {"padrao": normalizar(padrao), "categoria": categoria, "natureza": natureza,
            "prioridade": prioridade, "origem": origem}


def carregar_regras(db) -> list[dict]:
    """Padrao do codigo com as regras do dono por cima (mesmo padrao substitui)."""
    regras = {normalizar(p): _regra(p, c, n, pr, "padrao") for p, c, n, pr in REGRAS_PADRAO}
    for snap in db.collection(COLECAO).stream():
        dados = snap.to_dict() or {}
        padrao = normalizar(dados.get("padrao") or snap.id)
        if not padrao:
            continue
        if dados.get("ativo") is False:
            regras.pop(padrao, None)
            continue
        regras[padrao] = _regra(padrao, dados.get("categoria") or SEM_CATEGORIA,
                                dados.get("natureza") or "pessoal",
                                # Regra do dono vale mais que qualquer padrao.
                                2, "dono")
    return list(regras.values())


def classificar(estabelecimento: str, regras: list[dict]) -> dict:
    """Melhor regra que casa por palavras inteiras: maior prioridade, depois a mais longa."""
    texto = f" {normalizar(estabelecimento)} "
    melhor = None
    for regra in regras:
        if f" {regra['padrao']} " not in texto:
            continue
        chave = (regra["prioridade"], len(regra["padrao"]))
        if melhor is None or chave > (melhor["prioridade"], len(melhor["padrao"])):
            melhor = regra
    if melhor is None:
        return {"categoria": SEM_CATEGORIA, "natureza": None, "regra": None}
    return {"categoria": melhor["categoria"], "natureza": melhor["natureza"], "regra": melhor["padrao"]}


def definir(db, padrao: str, categoria: str, natureza: str = "pessoal") -> dict:
    chave = normalizar(padrao)
    if len(chave) < 3:
        raise ValueError("O padrao precisa ter pelo menos 3 letras (ex.: 'uber', 'google cloud').")
    if not str(categoria or "").strip():
        raise ValueError("Informe a categoria.")
    if natureza not in NATUREZAS:
        raise ValueError(f"Natureza deve ser uma de: {', '.join(NATUREZAS)}.")
    ref = db.collection(COLECAO).document(chave.replace(" ", "_"))
    ref.set({"padrao": chave, "categoria": categoria.strip(), "natureza": natureza, "ativo": True,
             "atualizado_em": datetime.now(timezone.utc).isoformat()})
    return ref.get().to_dict() or {}


def remover(db, padrao: str) -> dict:
    """Desliga a regra: a do dono e a padrao com o mesmo padrao deixam de valer."""
    chave = normalizar(padrao)
    ref = db.collection(COLECAO).document(chave.replace(" ", "_"))
    ref.set({"padrao": chave, "ativo": False, "atualizado_em": datetime.now(timezone.utc).isoformat()})
    return ref.get().to_dict() or {}
