import re
file_path = 'src/components/modals/Modals.tsx'

with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

replacements = {
    "AÂ§Ã£o": "Ação",
    "Ação": "Ação", # just in case
    "Ações": "Ações",
    "AçÃµes": "Ações",
    "AÃ§Ã£o": "Ação",
    "AÃ§ão": "Ação",
    "InÃ­cio": "Início",
    "AtenÃ§ão": "Atenção",
    "Ã reas": "Áreas",
    "balanÃ§a": "balança",
    "TerÃ§a": "Terça",
    "OrÃ§amentário": "Orçamentário",
    "mÃªs": "mês",
    "AdiÃ§ão": "Adição",
    "notificaÃ§ão": "notificação",
    "NotificaÃ§ão": "Notificação",
    "ASSISTÃŠNCIA": "ASSISTÊNCIA",
    "vocÃª": "você",
    "mÃ³dulo": "módulo",
    "execuÃ§ão": "execução",
    "Ãºltimos": "últimos",
    "IntegraÃ§ão": "Integração",
    "Ã©": "é",
    "AÃ§Ãºcar": "Açúcar",
    "Ã lcool": "Álcool",
    "atÃ©": "até",
    "NÃƒO CLASSIFICADA": "NÃO CLASSIFICADA",
    "TÃ­tulo": "Título",
    "ClassificaÃ§ão": "Classificação",
    "concluÃ­do": "concluído",
    "ConcluÃ­do": "Concluído",
    "Ã rea": "Área",
    "OrÃ§amentÃ¡rio": "Orçamentário",
    "AssistÃªncia": "Assistência",
    "InÃ\xadcio": "Início",
}

for k, v in replacements.items():
    text = text.replace(k, v)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)

print("Encoding artifacts fixed in Modals.tsx")
