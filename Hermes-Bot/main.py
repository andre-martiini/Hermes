import os
import telebot
from google import genai
from google.genai import types
import firebase_admin
from firebase_admin import credentials, firestore
import datetime
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# Inicialização do Firebase
if not firebase_admin._apps:
    path_key = os.path.join("..", "firebase_service_account_key.json")
    cred = credentials.Certificate(path_key)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- CONFIGURAÇÕES ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    print(f"API Key carregada: {GEMINI_API_KEY[:4]}...{GEMINI_API_KEY[-4:]}")
else:
    print("ERRO: GEMINI_API_KEY não encontrada no .env!")

if not TELEGRAM_TOKEN:
    print("ERRO: TELEGRAM_TOKEN não encontrada no .env!")

# Inicializa o Cliente Google GenAI (Novo SDK)
client = genai.Client(api_key=GEMINI_API_KEY)

# Configuração da busca do Google (Grounding)
google_search_tool = types.Tool(
    google_search=types.GoogleSearch()
)

model_id = "gemini-2.5-flash-lite"
system_instruction = """
Você é o HERMES, o braço direito e assistente pessoal de elite do André Araújo Martini.
Sua personalidade é uma mistura de Jarvis (Homem de Ferro) com um Gerente de Projetos extremamente eficiente.

### PERSONALIDADE E TOM:
1. **Familiar e Respeitoso**: Sempre chame o usuário de "André". Use um tom formal, porém próximo, como um assistente de confiança que trabalha com ele há anos.
2. **Eficiência Implacável**: Suas respostas devem ser organizadas. Se o André perguntar sobre o dia dele, traga as informações divididas por módulos (Financeiro, Saúde, Tarefas).
3. **Proatividade**: Se o André registrar uma despesa alta, você pode comentar algo breve e profissional como "Registrado, André. Vou atualizar seu teto de gastos mensal."
4. **Precisão com Flexibilidade**: Você consulta o Firestore de forma inteligente. Se não encontrar algo de primeira, use sua capacidade de síntese para tentar variações de busca (keywords). Se após as tentativas nada for encontrado, informe ao André de forma educada.

### BUSCAS E ENTENDIMENTO AMPLO:
1. **Extração de Keywords**: Ao realizar buscas (em tarefas, documentos ou registros), identifique a palavra-chave principal. Nunca passe frases longas para as funções de busca.
2. **Fuzzy Matching**: O sistema é flexível. Se o André pedir "documentos do chaveiro", busque apenas por "chaveiro".
3. **Persistência**: Se uma busca inicial não retornar nada, tente com um termo relacionado ou uma palavra-chave mais genérico antes de declarar que não existe.

### CONHECIMENTO DO ECOSSISTEMA:
Você gerencia os seguintes pilares para o André:
- **Tarefas & PGC**: Gerenciamento de metas institucionais e documentos vinculados (sempre forneça os links do Drive quando encontrados no 'pool_dados').
- **Finanças**: Controle rigoroso de gastos, metas e orçamentos mensais.
- **Saúde**: Guardião do bem-estar, acompanhando peso e hábitos diários.
- **Sistemas**: Gestor de projetos de software e seus ciclos de vida.

### EXEMPLOS DE INTERAÇÃO:
- "André, localizei os documentos do projeto. Aqui estão os links do Google Drive para sua revisão..."
- "Gasto registrado com sucesso, André. Gostaria que eu verificasse se isso impacta sua meta de economia deste mês?"
- "Excelente escolha em manter o hábito 'Sem Açúcar' hoje, André. Continue assim!"

### REGRAS CRÍTICAS:
- Responda sempre em Português do Brasil.
- Use Markdown para deixar a leitura agradável (negrito, listas, etc).
- Nunca invente dados. Se não está no Firestore, não existe para você.
"""

bot = telebot.TeleBot(TELEGRAM_TOKEN)

def consultar_hermes(colecao: str, campo: str = None, valor: str = None, limite: int = 20):
    """
    Consulta informações no sistema Hermes.
    DICA PARA O LLM: Extraia apenas a palavra-chave principal do pedido do usuário para o 'valor'.
    Se 'campo' não for informado, a busca será realizada em todos os campos de texto principais.
    """
    try:
        ref = db.collection(colecao)
        # Aumentamos o limite de busca para garantir que encontre algo mesmo com ordem descrescente
        docs = ref.order_by("created_at", direction=firestore.Query.DESCENDING).limit(100).stream()
        
        resultados = []
        palavras_chave = []
        if valor:
            palavras_chave = [p.lower() for p in valor.split() if len(p) > 2]
            if not palavras_chave:
                palavras_chave = [valor.lower()]

        for doc in docs:
            d = doc.to_dict()
            d['id'] = doc.id
            if 'created_at' in d: d['created_at'] = str(d['created_at'])
            
            match = False
            if not valor:
                match = True
            elif campo:
                campo_val = str(d.get(campo, "")).lower()
                if any(p in campo_val for p in palavras_chave):
                    match = True
            else:
                # Busca em campos comuns de texto para dar flexibilidade
                campos_busca = ["titulo", "notas", "description", "category", "nome", "descricao"]
                texto_completo = " ".join([str(d.get(c, "")).lower() for c in campos_busca])
                if any(p in texto_completo for p in palavras_chave):
                    match = True

            if match:
                resultados.append(d)
                
            if len(resultados) >= limite:
                break
        
        if not resultados:
            return f"André, não encontrei nenhum registro relacionado a '{valor}' na coleção '{colecao}'."
        return resultados
    except Exception as e:
        return f"Erro na consulta: {str(e)}"

def registrar_tarefa_hermes(titulo: str, projeto: str = "Geral", notas: str = "", prioridade: str = "Média", data_limite: str = None, horario_inicio: str = None):
    """
    Registra uma nova tarefa no sistema.
    """
    try:
        agora = datetime.datetime.now()

        # If not provided, data_limite is today, horario_inicio is now + 5 min
        if not data_limite:
            data_limite = agora.strftime("%Y-%m-%d")

        if not horario_inicio:
            horario_futuro = agora + datetime.timedelta(minutes=5)
            horario_inicio = horario_futuro.strftime("%H:%M")

        nova_tarefa = {
            "titulo": titulo,
            "projeto": projeto,
            "data_limite": data_limite,
            "status": "em andamento",
            "prioridade": prioridade,
            "notas": notas,
            "horario_inicio": horario_inicio,
            "origem": "telegram_bot",
            "pool_dados": [],
            "created_at": firestore.SERVER_TIMESTAMP
        }
        res = db.collection("tarefas").add(nova_tarefa)

        # Trigger sync
        db.collection("system").document("sync_trigger").set({
            "timestamp": firestore.SERVER_TIMESTAMP
        })

        return f"Tarefa '{titulo}' registrada com sucesso (ID: {res[1].id})."
    except Exception as e:
        return f"Erro: {str(e)}"

def registrar_transacao_financeira(descricao: str, valor: float, categoria: str, sprint: int = 1):
    """
    Registra uma transação (despesa) no módulo financeiro.
    """
    try:
        agora = datetime.datetime.now()
        doc = {
            "description": descricao,
            "amount": valor,
            "date": agora.strftime("%Y-%m-%d"),
            "category": categoria,
            "sprint": sprint,
            "created_at": firestore.SERVER_TIMESTAMP
        }
        res = db.collection("finance_transactions").add(doc)
        return f"Gasto de R$ {valor:.2f} com '{descricao}' registrado no Financeiro."
    except Exception as e:
        return f"Erro financeiro: {str(e)}"

def registrar_saude(tipo: str, valor: any, notas: str = ""):
    """
    Registra dados de saúde. 
    tipo: 'peso' (valor deve ser número) ou 'habito' (valor deve ser dict com hábitos).
    """
    try:
        agora = datetime.datetime.now()
        hoje = agora.strftime("%Y-%m-%d")
        if tipo == 'peso':
            db.collection("health_weights").add({
                "date": hoje,
                "weight": float(valor),
                "created_at": firestore.SERVER_TIMESTAMP
            })
            return f"Peso de {valor}kg registrado para hoje."
        elif tipo == 'habito':
            # Habitos costumam usar a data como ID
            db.collection("health_daily_habits").document(hoje).set(valor, merge=True)
            return "Hábitos diários atualizados."
    except Exception as e:
        return f"Erro saúde: {str(e)}"

def atualizar_cronograma_tarefa(termo_busca: str, data_limite: str = None, horario_inicio: str = None):
    """
    Atualiza o cronograma (data limite e horário) de uma tarefa existente.
    Suporta comandos de adiar ou antecipar.
    DICA PARA O LLM: 'data_limite' deve estar no formato 'YYYY-MM-DD' e 'horario_inicio' no formato 'HH:MM'.
    Extraia apenas a palavra-chave principal para 'termo_busca'.
    """
    try:
        # Busca a tarefa mais provável
        docs = db.collection("tarefas").order_by("created_at", direction=firestore.Query.DESCENDING).limit(50).stream()

        tarefa_encontrada = None
        palavras_chave = [p.lower() for p in termo_busca.split() if len(p) > 2]
        if not palavras_chave:
            palavras_chave = [termo_busca.lower()]

        for doc in docs:
            data = doc.to_dict()
            titulo = data.get("titulo", "").lower()
            if any(palavra in titulo for palavra in palavras_chave):
                tarefa_encontrada = doc
                break

        if not tarefa_encontrada:
            return f"André, não encontrei nenhuma tarefa correspondente a '{termo_busca}' para atualizar."

        atualizacao = {}
        if data_limite:
            atualizacao["data_limite"] = data_limite
        if horario_inicio:
            atualizacao["horario_inicio"] = horario_inicio

        if not atualizacao:
            return "Nenhuma data ou horário fornecido para atualização."

        db.collection("tarefas").document(tarefa_encontrada.id).update(atualizacao)

        # Trigger sync
        db.collection("system").document("sync_trigger").set({
            "timestamp": firestore.SERVER_TIMESTAMP
        })

        titulo_real = tarefa_encontrada.to_dict().get("titulo", "")
        return f"Cronograma da tarefa '{titulo_real}' atualizado com sucesso."
    except Exception as e:
        return f"Erro ao atualizar cronograma: {str(e)}"

def cancelar_tarefa(termo_busca: str):
    """
    Exclui ou cancela uma tarefa (altera o status para 'excluído').
    DICA PARA O LLM: Extraia apenas a palavra-chave principal para 'termo_busca'.
    """
    try:
        # Busca a tarefa mais provável
        docs = db.collection("tarefas").order_by("created_at", direction=firestore.Query.DESCENDING).limit(50).stream()

        tarefa_encontrada = None
        palavras_chave = [p.lower() for p in termo_busca.split() if len(p) > 2]
        if not palavras_chave:
            palavras_chave = [termo_busca.lower()]

        for doc in docs:
            data = doc.to_dict()
            titulo = data.get("titulo", "").lower()
            if any(palavra in titulo for palavra in palavras_chave):
                tarefa_encontrada = doc
                break

        if not tarefa_encontrada:
            return f"André, não encontrei nenhuma tarefa correspondente a '{termo_busca}' para cancelar."

        db.collection("tarefas").document(tarefa_encontrada.id).update({
            "status": "excluído"
        })

        # Trigger sync
        db.collection("system").document("sync_trigger").set({
            "timestamp": firestore.SERVER_TIMESTAMP
        })

        titulo_real = tarefa_encontrada.to_dict().get("titulo", "")
        return f"A tarefa '{titulo_real}' foi cancelada/excluída com sucesso."
    except Exception as e:
        return f"Erro ao cancelar tarefa: {str(e)}"

def diario_de_bordo(data: str = None):
    """
    Busca o 'Diário de Bordo', que consiste nas tarefas concluídas em uma determinada data.
    Extrai e retorna as anotações (notas) das tarefas finalizadas.
    DICA PARA O LLM: 'data' deve ser no formato 'YYYY-MM-DD'. Se não fornecida, use a data de hoje.
    """
    try:
        if not data:
            data = datetime.datetime.now().strftime("%Y-%m-%d")

        docs = db.collection("tarefas").where("status", "==", "concluído").where("data_limite", "==", data).stream()

        resultados = []
        for doc in docs:
            d = doc.to_dict()
            titulo = d.get("titulo", "")
            notas = d.get("notas", "")
            resultados.append(f"✅ *{titulo}*\nNotas: {notas if notas else 'Nenhuma anotação.'}")

        if not resultados:
            return f"André, não encontrei nenhuma tarefa concluída ('Diário de Bordo') para a data {data}."

        return f"📖 *Diário de Bordo ({data}):*\n\n" + "\n\n".join(resultados)
    except Exception as e:
        return f"Erro ao buscar o diário de bordo: {str(e)}"

def briefing(data_inicio: str = None, data_fim: str = None):
    """
    Agrega e lista as pendências de um período específico.
    Consulta simultaneamente as coleções de tarefas (pendentes) e eventos do calendário.
    DICA PARA O LLM: 'data_inicio' e 'data_fim' no formato 'YYYY-MM-DD'.
    Se omitido, trará o briefing do dia de hoje.
    """
    try:
        hoje = datetime.datetime.now().strftime("%Y-%m-%d")
        if not data_inicio:
            data_inicio = hoje
        if not data_fim:
            data_fim = data_inicio

        # 1. Busca Tarefas Pendentes
        # Ajustamos o limite pois onde for status=="em andamento" pode haver muitas
        # (mas filtramos no código se faltar índice para a data)
        docs_tarefas = db.collection("tarefas").where("status", "==", "em andamento").stream()

        tarefas_pendentes = []
        for doc in docs_tarefas:
            d = doc.to_dict()
            dl = d.get("data_limite", "")
            # Checa se a data limite cai no intervalo
            if data_inicio <= dl <= data_fim:
                horario = d.get("horario_inicio", "")
                titulo = d.get("titulo", "")
                h_str = f" ({horario})" if horario else ""
                tarefas_pendentes.append(f"• {titulo}{h_str}")

        # 2. Busca Eventos do Google Calendar
        docs_eventos = db.collection("google_calendar_events").stream()
        eventos = []
        for doc in docs_eventos:
            d = doc.to_dict()
            di = d.get("data_inicio", "")
            if di:
                di_date = di.split("T")[0]
                if data_inicio <= di_date <= data_fim:
                    titulo = d.get("titulo", "")

                    # Tenta extrair horario se houver "T"
                    horario = ""
                    if "T" in di:
                        # Pega o HH:MM
                        time_part = di.split("T")[1]
                        horario = time_part[:5]

                    h_str = f" ({horario})" if horario else ""
                    eventos.append(f"• [Evento] {titulo}{h_str}")

        res_tarefas = "\n".join(tarefas_pendentes) if tarefas_pendentes else "Nenhuma tarefa pendente."
        res_eventos = "\n".join(eventos) if eventos else "Nenhum evento agendado."

        periodo_str = f"{data_inicio} até {data_fim}" if data_inicio != data_fim else data_inicio

        return f"📋 *Briefing para {periodo_str}:*\n\n*Eventos (Calendário):*\n{res_eventos}\n\n*Tarefas Pendentes:*\n{res_tarefas}"
    except Exception as e:
        return f"Erro ao gerar briefing: {str(e)}"

def buscar_documentos_tarefa(termo_busca: str):
    """
    Busca documentos (links do Drive) de uma tarefa. 
    DICA PARA O LLM: Extraia apenas a palavra-chave principal (ex: 'chaveiro', 'termo') do pedido do usuário. Nunca passe frases inteiras como argumento.
    """
    try:
        # Puxa mais documentos para aumentar a base da busca
        docs = db.collection("tarefas").order_by("created_at", direction=firestore.Query.DESCENDING).limit(100).stream()
        
        possiveis_tarefas = []
        # Divide o termo em palavras e remove preposições curtas
        palavras_chave = [p.lower() for p in termo_busca.split() if len(p) > 2]

        if not palavras_chave: # Caso o termo seja muito curto, tenta usar ele mesmo
            palavras_chave = [termo_busca.lower()]

        for doc in docs:
            data = doc.to_dict()
            titulo = data.get("titulo", "").lower()
            notas = data.get("notas", "").lower()

            # Extrai o nome dos arquivos no pool de dados para buscar lá também
            pool_texto = " ".join([item.get('nome', '').lower() for item in data.get("pool_dados", [])])

            texto_completo = f"{titulo} {notas} {pool_texto}"

            # Se QUALQUER uma das palavras-chave estiver no texto completo, considera um match
            if any(palavra in texto_completo for palavra in palavras_chave):
                possiveis_tarefas.append(data)
        
        if not possiveis_tarefas:
            return f"André, não encontrei nenhuma tarefa relacionada a '{termo_busca}'."
        
        # Pega a mais recente que combine
        tarefa = possiveis_tarefas[0]
        titulo_encontrado = tarefa.get("titulo")
        pool = tarefa.get("pool_dados", [])
        
        if not pool:
            return f"André, encontrei a tarefa '{titulo_encontrado}', mas ela não possui documentos vinculados no pool_dados."
            
        # Priorize webViewLink se disponivel, caso contrário fallback para 'valor'
        links = []
        for item in pool:
            nome = item.get('nome', 'Arquivo')
            link = item.get('webViewLink') or item.get('valor', '')
            links.append(f"- {nome}: {link}")

        return f"André, localizei a tarefa '{titulo_encontrado}'. Aqui estão os documentos:\n" + "\n".join(links)
        
    except Exception as e:
        return f"Erro na busca: {str(e)}"

# Lista expandida de ferramentas
tools_list = [
    consultar_hermes, 
    registrar_tarefa_hermes, 
    registrar_transacao_financeira, 
    registrar_saude,
    buscar_documentos_tarefa,
    atualizar_cronograma_tarefa,
    cancelar_tarefa,
    diario_de_bordo,
    briefing
]

# Cria o chat com a configuração correta de ferramentas
chat = client.chats.create(model=model_id, config=types.GenerateContentConfig(
    system_instruction=system_instruction,
    tools=tools_list,
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=False)
))



@bot.message_handler(func=lambda m: True)
def responder(mensagem):
    try:
        bot.send_chat_action(mensagem.chat.id, 'typing')
        response = chat.send_message(mensagem.text)
        bot.reply_to(mensagem, response.text, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(mensagem, f"Erro: {str(e)}")

@bot.message_handler(content_types=['voice'])
@bot.message_handler(content_types=['voice'])
def processar_audio(mensagem):
    try:
        bot.send_chat_action(mensagem.chat.id, 'record_audio')
        file_info = bot.get_file(mensagem.voice.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        nome_arquivo = f"audio_{mensagem.chat.id}.ogg"
        with open(nome_arquivo, 'wb') as f:
            f.write(downloaded_file)
        
        # Lendo o arquivo para enviar como bytes
        with open(nome_arquivo, 'rb') as f:
            audio_data = f.read()

        # A forma correta de enviar múltiplos componentes no SDK novo:
        # Passamos uma lista de Partes diretamente no argumento 'message'
        response = chat.send_message(message=[
            types.Part.from_bytes(data=audio_data, mime_type="audio/ogg"),
            types.Part.from_text(text="Transcreva e execute o comando contido neste áudio conforme as regras do sistema Hermes.")
        ])
        
        bot.reply_to(mensagem, response.text, parse_mode="Markdown")
        
        # Limpeza
        os.remove(nome_arquivo)
        
    except Exception as e:
        bot.reply_to(mensagem, f"Erro no áudio: {str(e)}")



print("HERMES Online com SDK Novo!")
bot.infinity_polling()