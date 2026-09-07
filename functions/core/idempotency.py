"""Deduplicação idempotente por chave (ex.: delivery_id de webhook, update_id
de bot) usando um documento-sentinela em `idempotency/{key}`, criado dentro de
uma transação Firestore para que duas chamadas concorrentes com a mesma chave
não possam ambas concluir que a chave é nova.

O sentinela tem dois estados: RESERVADO (uma tentativa começou a processar) e
CONCLUIDO (o processamento com efeito terminou de verdade). Só CONCLUIDO é
tratado como duplicata — ver check_and_register/mark_complete abaixo.
"""

from datetime import datetime, timezone, timedelta

from firebase_admin import firestore as _fs

STATUS_RESERVADO = "reservado"
STATUS_CONCLUIDO = "concluido"

# Achado do Codex na PR #188: se o commit da reserva for ambíguo (o cliente
# recebe timeout/erro, mas o Firestore já tinha escrito o documento no
# servidor), a exceção propagada por check_and_register faz o chamador
# responder erro para o remetente reentregar — mas se "documento existe"
# bastasse para considerar a chave "já processada", a reentrega encontraria
# o sentinela e pularia para sempre, mesmo que o processamento de fato nunca
# tenha rodado. Por isso uma reserva sozinha (sem conclusão) NUNCA é tratada
# como sucesso/duplicata: enquanto for recente, check_and_register levanta
# ReservaEmAndamentoError em vez de devolver False — só depois de expirada é
# que uma nova tentativa pode retomar e reprocessar de verdade.
RESERVA_EXPIRA_APOS = timedelta(minutes=5)


class ReservaEmAndamentoError(RuntimeError):
    """Levantada por check_and_register quando existe uma reserva recente
    para a mesma chave, de uma tentativa que pode estar processando agora
    mesmo, ou pode ter morrido sem confirmar (commit ambíguo, crash, exceção
    não tratada no meio do processamento) — não dá para distinguir os dois
    casos a partir daqui, então nenhum dos dois pode ser tratado como
    sucesso.

    É subclasse de RuntimeError de propósito: no `main.py` HOJE implantado
    (verificado em `git show HEAD:functions/main.py` — sem nenhum try/except
    ao redor da chamada a check_and_register), levantar esta exceção (como
    qualquer outra que já podia vir daqui, ex.: falha real de transação) sobe
    sem tratamento até o framework (functions_framework/flask), que responde
    500 via seu crash_handler — nunca 200. Ou seja: já é seguro (nunca vira
    "sucesso" silencioso) mesmo sem nenhuma edição adicional em main.py,
    porque a ausência de captura também nunca deixa a exceção virar sucesso.
    O rascunho local de main.py (bloqueado de shipar por limite de tamanho de
    escrita do Argos — ver docs/autonomia/execucao.md) adiciona um
    `except ReservaEmAndamentoError` específico antes do `except Exception`
    genérico, para responder 503 (recuperável, sem vazar o texto da exceção
    no corpo da resposta como o 500 do crash_handler faz) e logar de forma
    diferenciada — mas isso é uma melhoria de ergonomia/observabilidade, não
    uma correção de segurança: o comportamento já é seguro sem ela. Um
    chamador que queira capturar esta classe especificamente antes de um
    Exception genérico pode fazê-lo a qualquer momento.

    Uma reentrega correta do remetente, mais cedo ou mais tarde, sempre
    resolve isto para um dos dois estados estáveis: `check_and_register`
    volta a levantar (se a reserva ainda for recente), devolve False (se a
    tentativa original chamou mark_complete nesse meio-tempo) ou devolve True
    (se a reserva expirou sem conclusão, e pode ser retomada). Nunca fica
    travado neste estado, desde que o remetente continue reentregando.
    """


def check_and_register(db, update_id: str | int) -> bool:
    """Retorna True se `update_id` deve ser processado agora — chave nova, ou
    uma reserva anterior sem conclusão e já expirada (o chamador DEVE
    processar e, ao terminar com sucesso, chamar mark_complete(db,
    update_id) — sem isso a reserva volta a expirar e uma reentrega futura
    reprocessaria de novo). Retorna False se a chave já foi CONCLUÍDA antes
    (seguro responder sucesso ao remetente sem processar de novo).

    Levanta ReservaEmAndamentoError se existir uma reserva recente sem
    conclusão — ver a docstring da classe para o porquê disso nunca poder
    virar True nem False diretamente.

    Se a verificação transacional falhar por um motivo real — Firestore
    indisponível, contenção esgotando tentativas etc. — a exceção original
    também é propagada, pelo mesmo motivo (achado do plano de autonomia, P01
    passo 4): erro de idempotência em caminho com efeito deve virar resultado
    recuperável sem efeito, nunca "permitir processamento" às escondidas.
    Cabe ao chamador tratar qualquer exceção daqui (incluindo
    ReservaEmAndamentoError) como "recuperável sem efeito" — por exemplo,
    respondendo um erro HTTP a um webhook para que o remetente reentregue
    mais tarde com a mesma chave (GitHub e a maioria dos provedores de
    webhook já fazem isso automaticamente para respostas não-2xx). Mas isso
    é só uma melhoria de ergonomia: mesmo um chamador que não captura nada
    (como o main.py hoje implantado) já fica seguro, porque a exceção não
    tratada nunca vira uma resposta de sucesso — ver a docstring de
    ReservaEmAndamentoError para os detalhes verificados desse caminho.
    """
    if not update_id:
        return True

    ref = db.collection("idempotency").document(str(update_id))
    agora = datetime.now(timezone.utc)
    expires_at = agora + timedelta(hours=24)

    @_fs.transactional
    def _txn(transaction, ref):
        snap = ref.get(transaction=transaction)
        if snap.exists:
            data = snap.to_dict() or {}
            if data.get("status") == STATUS_CONCLUIDO:
                return False
            # Reserva sem conclusão (ou documento legado sem 'status'): só
            # pode ser tratada como concluída se de fato terminou. Enquanto
            # for recente o bastante para plausivelmente ainda estar em
            # andamento, não é seguro devolver nem True nem False.
            reservado_em = data.get("reserved_at")
            if isinstance(reservado_em, datetime) and (agora - reservado_em) < RESERVA_EXPIRA_APOS:
                raise ReservaEmAndamentoError(
                    f"Reserva de idempotencia recente para '{update_id}' "
                    "sem conclusao ainda; possivelmente em andamento em "
                    "outra tentativa (ou commit ambiguo de uma tentativa "
                    "anterior)."
                )
            # Reserva velha (ou sem reserved_at legível): presume-se
            # abandonada. Cai para o mesmo caminho de baixo, que renova a
            # reserva com o timestamp de agora.
        transaction.set(ref, {
            "status": STATUS_RESERVADO,
            "reserved_at": agora,
            "expires_at": expires_at,
        })
        return True

    txn = db.transaction()
    return _txn(txn, ref)


def mark_complete(db, update_id: str | int) -> None:
    """Marca `update_id` como CONCLUÍDO, depois que o processamento com efeito
    correspondente (chamado após um check_and_register que retornou True)
    termina com sucesso. Só a partir daqui uma reentrega com a mesma chave
    recebe False (duplicata); antes disso, a reserva expira sozinha (ver
    RESERVA_EXPIRA_APOS) e uma reentrega pode reprocessar.

    Não é transacional: na prática, só o processo que já "ganhou" a reserva
    (check_and_register retornou True) chama isto, dentro da mesma execução
    que fica sob o timeout da função (bem menor que RESERVA_EXPIRA_APOS),
    então não há disputa concorrente esperada nesse ponto. Isso depende de o
    tempo de execução do chamador ficar sempre bem abaixo de
    RESERVA_EXPIRA_APOS — não é garantido pelo código aqui, é
    responsabilidade de quem configura o timeout da função que usa este
    módulo.
    """
    if not update_id:
        return
    ref = db.collection("idempotency").document(str(update_id))
    ref.set(
        {"status": STATUS_CONCLUIDO, "completed_at": _fs.SERVER_TIMESTAMP},
        merge=True,
    )
