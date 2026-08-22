"""
Rotinas de saúde padrão do Hermes (lembretes enviados só pelo Telegram).

Fonte única no lado Python: consumida pelo motor de lembretes
(`main.check_and_send_reminders`, que sobrepõe estas entradas com o que estiver
gravado em `health_telegram_reminders`) e pelo Resumo Matinal
(`morning_summary._coletar_saude`, que precisa saber quais rotinas o dia de hoje
espera).

Mantenha em sincronia com DEFAULT_HEALTH_REMINDERS em HealthView.tsx (mesmos
id/title/message/time/daysOfWeek/category) — não há fonte única entre Python e
TypeScript, então qualquer mudança aqui precisa ser replicada lá.

`daysOfWeek` segue a convenção do `Date.getDay()` do JavaScript: domingo=0.
"""

DEFAULT_HEALTH_REMINDERS = [
{
    "id": "lunch_slow",
    "title": "Almoço com calma",
    "message": "André, lembre de comer devagar no almoço. Ritmo baixo também é estratégia.",
    "time": "11:45",
    "enabled": True,
    "daysOfWeek": [0, 1, 2, 3, 4, 5, 6],
    "category": "nutrition",
},
{
    "id": "food_window",
    "title": "Janela alimentar",
    "message": "André, última janela alimentar chegando. Se for comer, mantenha leve.",
    "time": "17:30",
    "enabled": True,
    "daysOfWeek": [0, 1, 2, 3, 4, 5, 6],
    "category": "nutrition",
},
{
    "id": "morning_checkin",
    "title": "Check-in da manhã",
    "message": "André, hora do check-in da manhã — 3 perguntas rápidas sobre dor e sono.",
    "time": "12:00",
    "enabled": True,
    "daysOfWeek": [0, 1, 2, 3, 4, 5, 6],
    "category": "checkin_morning",
},
{
    "id": "night_checkin",
    "title": "Check-in da noite",
    "message": "André, hora do check-in da noite — uma pergunta por vez, leva menos de 1 minuto.",
    "time": "19:00",
    "enabled": True,
    "daysOfWeek": [0, 1, 2, 3, 4, 5, 6],
    "category": "checkin_night",
},
{
    "id": "strength_training",
    "title": "Treino de força — Seg e Sex",
    "message": "André, hoje é dia de treino de força (bloco A ou B).",
    "time": "17:20",
    "enabled": True,
    "daysOfWeek": [1, 5],
    "category": "spine",
},
{
    "id": "strength_training_wed",
    "title": "Treino de força — Quarta (antes da acupuntura)",
    "message": "André, hoje é dia de treino de força (bloco A ou B) — mais cedo por causa da acupuntura às 17h.",
    "time": "15:05",
    "enabled": True,
    "daysOfWeek": [3],
    "category": "spine",
},
{
    "id": "daily_weighin",
    "title": "Pesagem diária",
    "message": "André, pese-se ao acordar, antes do café — antes da caminhada.",
    "time": "04:20",
    "enabled": True,
    "daysOfWeek": [0, 1, 2, 3, 4, 5, 6],
    "category": "custom",
},
{
    "id": "waist_saturday",
    "title": "Cintura da semana",
    "message": "André, meça a circunferência de cintura na altura do umbigo.",
    "time": "08:00",
    "enabled": True,
    "daysOfWeek": [6],
    "category": "custom",
},
{
    "id": "batch_cooking_sunday",
    "title": "Batch cooking",
    "message": "André, hora de preparar as refeições da semana.",
    "time": "09:45",
    "enabled": True,
    "daysOfWeek": [0],
    "category": "nutrition",
},
{
    "id": "fexofenadina_reminder",
    "title": "Fexofenadina",
    "message": "André, tome a fexofenadina com água — longe de suco e de antiácido, que reduzem a absorção em 30–40%.",
    "time": "08:00",
    "enabled": True,
    "daysOfWeek": [0, 1, 2, 3, 4, 5, 6],
    "category": "custom",
},
]
