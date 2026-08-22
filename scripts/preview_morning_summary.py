"""Preview do Resumo Matinal (Camada 1) contra o Firestore real, sem gravar
nada por padrao -- mesmo papel de scripts/preview_weekly_report.py.

Diferente daquele, aqui e seguro importar functions/main.py: o init do Firebase
Admin la e guardado por `get_app()` (main.py:103), entao ele reaproveita o app
que este script cria com a chave de servico em vez de tentar inicializar outro.

O coletor nao chama nenhum modelo -- o que sai aqui e exatamente o que a tela
'home' vai mostrar.

Uso: functions/venv/Scripts/python.exe scripts/preview_morning_summary.py [YYYY-MM-DD] [--json] [--gravar]
     --json    imprime o dict cru em vez do relatorio legivel
     --gravar  persiste em resumo_matinal/{data} (o que o scheduler das 4h30 faz)
"""
import json
import sys

sys.path.insert(0, 'functions')

import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'


def init_db():
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()


def _linha(rotulo, valor):
    print(f"  {rotulo:.<34} {valor}")


def imprimir(r: dict) -> None:
    c = r["contadores"]

    print(f"\n{'=' * 72}")
    print(f"  RESUMO MATINAL — {r['dia_semana']}, {r['data']}   (versao {r['versao']})")
    print(f"{'=' * 72}")

    print("\nESTADO")
    _linha("acoes ativas no sistema", c["ativas"])
    _linha("caem hoje", c["hoje"])
    _linha("  ...herdadas do reset da meia-noite", c["herdadas"])
    _linha("  ...em degradacao critica (3+ adiamentos)", c["criticas"])
    _linha("  ...viraram [COBRAR]", c["cobrar"])
    _linha("  ...sem plano de acao", c["sem_plano"])
    _linha("pendencias em fila", c["pendencias"])

    print(f"\nFOCO DO DIA ({len(r['foco'])})")
    if not r["foco"]:
        print("  (nenhum — dia sem acao programada)")
    for i, f in enumerate(r["foco"], 1):
        hora = f" [{f['horario_inicio']}]" if f["horario_inicio"] else ""
        print(f"  {i}. {f['titulo']}{hora}")
        print(f"     regra: {f['regra']}")
        print(f"     {f['motivo']}")
        if f["proximo_passo"]:
            print(f"     -> {f['proximo_passo']}")

    print("\nAGENDA")
    if not r["agenda"]:
        print("  (vazia)")
    for ev in r["agenda"]:
        quando = "dia inteiro" if ev["dia_inteiro"] else f"{ev['inicio']}–{ev['fim'] or '?'}"
        print(f"  {quando:>14}  {ev['titulo']}")
    if r["janelas_livres"]:
        livres = ", ".join(f"{j['inicio']}–{j['fim']} ({j['minutos']}min)" for j in r["janelas_livres"])
        print(f"  janelas livres: {livres}")

    print("\nACOES DE HOJE")
    for lane in ("avanco", "continuo", "aguardando_terceiro", "atrasadas"):
        itens = r["hoje"][lane]
        if not itens:
            continue
        print(f"  [{lane}] {len(itens)}")
        for a in itens:
            marcas = []
            if a["herdada"]:
                marcas.append("herdada")
            if a["degradation_count"] >= 3:
                marcas.append(f"{a['degradation_count']}x adiada")
            if a["cobrar"]:
                marcas.append("cobrar")
            sufixo = f"  ({', '.join(marcas)})" if marcas else ""
            hora = f"{a['horario_inicio']} " if a["horario_inicio"] else ""
            print(f"    - {hora}{a['titulo']}{sufixo}")
            if a["proximo_passo"]:
                print(f"        -> {a['proximo_passo']} ({a['etapas_feitas']}/{a['etapas_totais']})")

    print("\nPRAZOS FINAIS (7 dias)")
    if not r["prazos_duros"]:
        print("  (nenhum)")
    for p in r["prazos_duros"]:
        print(f"  {p['prazo_final']}  (em {p['dias']}d)  {p['titulo']}")

    print("\nESPERANDO DECISAO")
    vazio = True
    for chave, fila in r["filas"].items():
        if not fila.get("total"):
            continue
        vazio = False
        print(f"  {chave}: {fila['total']}")
        for item in fila["amostra"]:
            print(f"    - {str(item.get('titulo'))[:80]}")
    if vazio:
        print("  (nenhuma fila parada)")

    print("\nESTRATEGIA")
    est = r["estrategia"]
    print(f"  {est['servidas_hoje']} de {est['total_geridas_por_acoes']} meta(s) gerida(s) por acoes recebem trabalho hoje")
    fora = [m for m in est["metas"] if not m["gerida_por_acoes"]]
    if fora:
        print(f"  ({len(fora)} meta(s) fora da conta — pilar nao executado por acoes)")
    for m in est["metas"]:
        if m["acoes_hoje"]:
            print(f"  + {m['objetivo']} — {m['acoes_hoje']} acao(oes) hoje")
    for m in est["paradas"]:
        dias = m["dias_parada"]
        print(f"  ! {m['objetivo']} — parada ha {dias} dia(s)" if dias is not None
              else f"  ! {m['objetivo']} — sem movimento registrado")

    print("\nCORPO")
    s = r["saude"]
    if s["peso"]:
        p = s["peso"]
        print(f"  peso {p['ultimo']}kg em {p['data']}  media7={p['media7']}  alvo={p['alvo']}  faltam={p['falta']}")
    if s["dor_ontem"]:
        print(f"  dor ontem: {s['dor_ontem']}")
    print(f"  ultimo registro do modulo Saude: {s['ultimo_registro']}")
    print(f"  rotinas de hoje: {len(s['rotinas_hoje'])}  (v = feito, o = pendente, sem marca = aviso)")
    for rot in s["rotinas_hoje"]:
        marca = "  " if rot["feito"] is None else ("v " if rot["feito"] else "o ")
        print(f"    {marca}{rot['hora']}  {rot['titulo']}")

    print("\nONTEM")
    print(f"  concluidas: {len(r['ontem']['concluidas'])}")
    for t in r["ontem"]["concluidas"][:8]:
        print(f"    v {t}")
    if r["ontem"]["diario"]:
        texto = r["ontem"]["diario"]["texto"].replace("\n", " ")
        print(f"  diario: {texto[:200]}...")
    else:
        print("  diario: (nao gerado)")

    print(f"\n  perfil de personalidade: {'carregado' if r['perfil'] else 'ausente'}")
    print(f"{'=' * 72}\n")


def main():
    args = [a for a in sys.argv[1:]]
    como_json = "--json" in args
    gravar = "--gravar" in args
    datas = [a for a in args if not a.startswith("--")]
    date_str = datas[0] if datas else None

    db = init_db()
    from morning_summary import build_morning_summary, _persistir

    resumo = build_morning_summary(db, date_str)

    if como_json:
        print(json.dumps(resumo, ensure_ascii=False, indent=2, default=str))
    else:
        imprimir(resumo)

    if gravar:
        _persistir(db, resumo)
        print(f"[gravado] resumo_matinal/{resumo['data']}")
    else:
        print("[read-only] nada foi gravado — use --gravar para persistir")


if __name__ == "__main__":
    main()
