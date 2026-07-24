# -*- coding: utf-8 -*-
import csv
import os
import re
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'
EXTRATO_PATH = r'C:\Users\T-GAMER\Downloads\extrato-2026-07-01-2026-07-23.csv'

def init_db():
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()

def parse_valor(v):
    v = v.replace('\u2212', '-').replace('R$', '').strip()
    sign = -1 if v.startswith('-') else 1
    v = v.lstrip('-+').strip()
    v = v.replace('.', '').replace(',', '.')
    return sign * float(v)

# --- 1. Ler extrato real do PicPay ---
real_rows = []
with open(EXTRATO_PATH, encoding='utf-8-sig') as f:
    reader = csv.DictReader(f, delimiter=',')
    for row in reader:
        if not row.get('data'):
            continue
        valor = parse_valor(row['valor'])
        real_rows.append({
            'date': row['data'],
            'time': row['hora'],
            'tipo': row['tipo'],
            'origem_destino': row['origem / destino'],
            'valor': valor,
        })

# Excluir par de transferencia interna "Dinheiro guardado" / "Pix recebido ANDRE ARAUJO MARTINI" mesmo valor mesmo dia
internal_transfer_pairs = []
for i, r in enumerate(real_rows):
    if r['tipo'] == 'Dinheiro guardado':
        for j, r2 in enumerate(real_rows):
            if j != i and r2['tipo'] == 'Pix recebido' and r2['origem_destino'] == 'ANDRE ARAUJO MARTINI' and abs(r2['valor'] - abs(r['valor'])) < 0.01 and r2['date'] == r['date']:
                internal_transfer_pairs.append(i)
                internal_transfer_pairs.append(j)

real_rows_filtered = [r for idx, r in enumerate(real_rows) if idx not in internal_transfer_pairs]

real_expenses = [r for r in real_rows_filtered if r['valor'] < 0]
real_income = [r for r in real_rows_filtered if r['valor'] > 0]

print(f"Extrato real (excluindo transferencia interna cofrinho): {len(real_expenses)} saidas, {len(real_income)} entradas")
print(f"Total saidas reais: R$ {sum(-r['valor'] for r in real_expenses):.2f}")
print(f"Total entradas reais: R$ {sum(r['valor'] for r in real_income):.2f}")

# --- 2. Ler Hermes (Firestore) ---
def in_period(date_str):
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime(2026,7,1,tzinfo=timezone.utc) <= dt <= datetime(2026,7,24,tzinfo=timezone.utc)
    except:
        return False

hermes_expenses = []
for doc in db.collection('finance_transactions').stream():
    d = doc.to_dict()
    if d.get('status') == 'deleted':
        continue
    date_str = d.get('date', '')
    if not in_period(date_str):
        continue
    hermes_expenses.append({
        'id': doc.id,
        'amount': float(d.get('amount', 0.0)),
        'date': date_str,
        'desc': d.get('description', ''),
    })

hermes_income = []
for doc in db.collection('finance_income').stream():
    d = doc.to_dict()
    if d.get('status') == 'deleted':
        continue
    date_str = d.get('date', '')
    if not in_period(date_str):
        continue
    hermes_income.append({
        'id': doc.id,
        'amount': float(d.get('amount', 0.0)),
        'date': date_str,
        'desc': d.get('description', ''),
    })

print(f"\nHermes (periodo 01/07-23/07): {len(hermes_expenses)} finance_transactions ativos, {len(hermes_income)} finance_income ativos")
print(f"Total finance_transactions: R$ {sum(h['amount'] for h in hermes_expenses):.2f}")
print(f"Total finance_income: R$ {sum(h['amount'] for h in hermes_income):.2f}")

# --- 3. Matching guloso por dia + valor ---
def day_of(date_str):
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d')
    except:
        return date_str[:10]

def match(real_list, hermes_list, label):
    used_hermes = set()
    unmatched_real = []
    for r in real_list:
        amt = abs(r['valor'])
        found = None
        # tenta mesmo dia primeiro, depois +-1 dia (fuso horario)
        for h in hermes_list:
            if h['id'] in used_hermes:
                continue
            if abs(h['amount'] - amt) < 0.01:
                hday = day_of(h['date'])
                if hday == r['date']:
                    found = h
                    break
        if not found:
            from datetime import timedelta
            rdate = datetime.strptime(r['date'], '%Y-%m-%d')
            for delta in (-1, 1):
                target_day = (rdate + timedelta(days=delta)).strftime('%Y-%m-%d')
                for h in hermes_list:
                    if h['id'] in used_hermes:
                        continue
                    if abs(h['amount'] - amt) < 0.01 and day_of(h['date']) == target_day:
                        found = h
                        break
                if found:
                    break
        if found:
            used_hermes.add(found['id'])
        else:
            unmatched_real.append(r)

    unmatched_hermes = [h for h in hermes_list if h['id'] not in used_hermes]

    print(f"\n--- {label}: NAO encontrados no Hermes (existem no extrato real mas faltam no Hermes) ---")
    for r in unmatched_real:
        print(f"  {r['date']} {r['time']} {r['tipo']} '{r['origem_destino']}' R$ {abs(r['valor']):.2f}")

    print(f"--- {label}: SOBRANDO no Hermes (nao correspondem a nenhum movimento real) ---")
    for h in unmatched_hermes:
        print(f"  id={h['id']} date={h['date']} R$ {h['amount']:.2f} desc={h['desc']!r}")

    return unmatched_real, unmatched_hermes

un_real_exp, un_hermes_exp = match(real_expenses, hermes_expenses, "SAIDAS")
un_real_inc, un_hermes_inc = match(real_income, hermes_income, "ENTRADAS")

print("\n=== RESUMO ===")
print(f"Saidas reais nao lancadas no Hermes: {len(un_real_exp)} | Total: R$ {sum(abs(r['valor']) for r in un_real_exp):.2f}")
print(f"Lancamentos de saida no Hermes sem correspondencia real: {len(un_hermes_exp)} | Total: R$ {sum(h['amount'] for h in un_hermes_exp):.2f}")
print(f"Entradas reais nao lancadas no Hermes: {len(un_real_inc)} | Total: R$ {sum(abs(r['valor']) for r in un_real_inc):.2f}")
print(f"Lancamentos de entrada no Hermes sem correspondencia real: {len(un_hermes_inc)} | Total: R$ {sum(h['amount'] for h in un_hermes_inc):.2f}")
