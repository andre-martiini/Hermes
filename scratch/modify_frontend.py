import re

with open('src/views/TaskExecutionView.tsx', 'r') as f:
    content = f.read()

# 1. Adicionar os state hooks para pesquisa
# hooks to add:
#   const [pendingDeepResearchId, setPendingDeepResearchId] = useState<string | null>(null);
#   const [isDeepResearching, setIsDeepResearching] = useState(false);
#   const [deepResearchTopic, setDeepResearchTopic] = useState('');
#   const [showDeepResearchModal, setShowDeepResearchModal] = useState(false);

# Let's insert them near chat states
chat_states_pattern = r"const \[chatMessages, setChatMessages\] = useState<ChatMessage\[\]>\(currentTaskData\.chat_history \|\| \[\]\);\n  const \[chatInput, setChatInput\] = useState\(''\);\n  const \[isChatLoading, setIsChatLoading\] = useState\(false\);"
chat_states_replacement = """const [chatMessages, setChatMessages] = useState<ChatMessage[]>(currentTaskData.chat_history || []);
  const [chatInput, setChatInput] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [pendingDeepResearchId, setPendingDeepResearchId] = useState<string | null>(null);
  const [isDeepResearching, setIsDeepResearching] = useState(false);
  const [deepResearchTopic, setDeepResearchTopic] = useState('');
  const [showDeepResearchModal, setShowDeepResearchModal] = useState(false);"""

content = re.sub(chat_states_pattern, chat_states_replacement, content)


# 2. Add firestore onSnapshot for deep research tracking
effect_pattern = r"const chatEndRef = useRef<HTMLDivElement>\(null\);"
effect_replacement = """const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!pendingDeepResearchId) return;

    // Fallback timer (2 hours)
    const fallbackTimer = setTimeout(() => {
      setIsDeepResearching(false);
      showToast('A pesquisa profunda pode ter falhado por timeout (mais de 2 horas).', 'error');
      setPendingDeepResearchId(null);
    }, 2 * 60 * 60 * 1000);

    const unsub = onSnapshot(doc(db, 'deep_research_tasks', pendingDeepResearchId), (docSnap) => {
      if (docSnap.exists()) {
        const data = docSnap.data();
        if (data.status === 'COMPLETED' || data.status === 'FAILED' || data.status === 'CANCELLED') {
           setIsDeepResearching(false);
           if (data.status === 'COMPLETED') {
             showToast('Pesquisa Profunda concluída! Verifique o acervo global.', 'success');
           } else if (data.status === 'CANCELLED') {
             showToast('Pesquisa Profunda cancelada.', 'info');
           } else {
             showToast('Pesquisa Profunda falhou.', 'error');
           }
           setPendingDeepResearchId(null);
           clearTimeout(fallbackTimer);
        }
      }
    });

    return () => {
       unsub();
       clearTimeout(fallbackTimer);
    };
  }, [pendingDeepResearchId]);"""

content = re.sub(effect_pattern, effect_replacement, content)

# 3. Importar onSnapshot
import_pattern = r"import \{ doc, updateDoc, arrayUnion \} from 'firebase/firestore';"
import_replacement = "import { doc, updateDoc, arrayUnion, onSnapshot } from 'firebase/firestore';"
content = re.sub(import_pattern, import_replacement, content)


# 4. Handle commands in handleSendMessage
send_msg_pattern = r"const handleSendMessage = \(\) => \{\n    const msg = chatInput\.trim\(\);\n    if \(!msg\) return;\n    setChatInput\(''\);\n    sendChatMessage\(msg\);\n  \};"
send_msg_replacement = """const handleSendMessage = async () => {
    const msg = chatInput.trim();
    if (!msg) return;
    setChatInput('');

    if (msg.startsWith('/pesquisa-profunda')) {
      const topic = msg.replace('/pesquisa-profunda', '').trim();
      if (!topic) {
        showToast('Por favor, informe um tema. Ex: /pesquisa-profunda Inteligência Artificial', 'warning');
        return;
      }
      setDeepResearchTopic(topic);
      setShowDeepResearchModal(true);
      return;
    }

    if (msg.startsWith('/cancelar-pesquisa')) {
      const parts = msg.split(' ');
      const idToCancel = parts.length > 1 ? parts[1] : pendingDeepResearchId;
      if (!idToCancel) {
         showToast('Nenhuma pesquisa em andamento ou ID inválido.', 'warning');
         return;
      }
      try {
         const fn = httpsCallable(functions, 'cancelDeepResearch');
         await fn({ taskId: idToCancel });
         showToast('Solicitação de cancelamento enviada.', 'success');
      } catch (e) {
         console.error('Erro ao cancelar:', e);
         showToast('Erro ao cancelar pesquisa.', 'error');
      }
      return;
    }

    sendChatMessage(msg);
  };"""
content = re.sub(send_msg_pattern, send_msg_replacement, content)


# 5. Modal and Execution function
fn_pattern = r"const handleSummarizeWithAI = async \(\) => \{"
fn_replacement = """const confirmDeepResearch = async () => {
    setShowDeepResearchModal(false);
    setIsDeepResearching(true);

    // Add to chat immediately
    const userMsg: ChatMessage = { role: 'user', content: `/pesquisa-profunda ${deepResearchTopic}` };
    const sysMsg: ChatMessage = { role: 'assistant', content: `Iniciando pesquisa profunda sobre: "${deepResearchTopic}". Isso pode levar até 60 minutos. Use /cancelar-pesquisa para interromper.` };
    setChatMessages(prev => [...prev, userMsg, sysMsg]);

    try {
      const fn = httpsCallable(functions, 'startDeepResearch');
      const res = await fn({
        topic: deepResearchTopic,
        requester_email: currentUser?.email,
        telegram_chat_id: currentUser?.uid // Adapt according to how we store it, usually user uid maps to some config, but we pass what we can here.
      });
      const data = res.data as { taskId: string };
      setPendingDeepResearchId(data.taskId);
      showToast(`Pesquisa iniciada. ID: ${data.taskId}`, 'success');
    } catch (e) {
      console.error(e);
      showToast('Erro ao iniciar pesquisa profunda.', 'error');
      setIsDeepResearching(false);
    }
  };

  const handleSummarizeWithAI = async () => {"""
content = re.sub(fn_pattern, fn_replacement, content)


# 6. Render Modal UI
ui_pattern = r"\{showAttachMenu && \(\n                <div className=\"absolute bottom-14 left-0"
ui_replacement = """{showDeepResearchModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-[#1E1E1E] p-6 rounded-xl shadow-2xl max-w-md w-full border border-neutral-800">
            <h3 className="text-xl font-bold text-white mb-4">Confirmar Pesquisa Profunda</h3>
            <p className="text-neutral-400 mb-6 leading-relaxed">
              Você está prestes a iniciar uma Pesquisa Profunda Max sobre:
              <br/><br/>
              <strong className="text-emerald-400">"{deepResearchTopic}"</strong>
              <br/><br/>
              Isso iniciará um processo automatizado intensivo usando o modelo Gemini Max que pode demorar <strong>até 60 minutos</strong> para ser concluído.
              Você receberá o resultado em formato PDF/HTML no Acervo Global assim que finalizado.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowDeepResearchModal(false)}
                className="px-4 py-2 text-neutral-400 hover:text-white transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={confirmDeepResearch}
                className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition-colors font-medium"
              >
                Iniciar Pesquisa
              </button>
            </div>
          </div>
        </div>
      )}

      {showAttachMenu && (
                <div className="absolute bottom-14 left-0"""
content = re.sub(ui_pattern, ui_replacement, content)


# 7. Loading UI
loading_pattern = r"\{isChatLoading && \(\n                  <div className=\"flex justify-start opacity-70 animate-pulse\">\n                    <div className=\"bg-neutral-800/80 p-3 rounded-xl rounded-tl-sm text-neutral-400 text-sm\">\n                      O copiloto está pensando\.\.\.\n                    <\/div>\n                  <\/div>\n                \)\}"

loading_replacement = """{isChatLoading && (
                  <div className="flex justify-start opacity-70 animate-pulse">
                    <div className="bg-neutral-800/80 p-3 rounded-xl rounded-tl-sm text-neutral-400 text-sm">
                      O copiloto está pensando...
                    </div>
                  </div>
                )}
                {isDeepResearching && (
                  <div className="flex justify-start opacity-70 animate-pulse">
                     <div className="bg-emerald-900/40 border border-emerald-800/50 p-3 rounded-xl rounded-tl-sm text-emerald-400 text-sm flex flex-col gap-1">
                       <span><strong>[Pesquisa Profunda Max]</strong> em andamento...</span>
                       <span className="text-xs text-emerald-500">Isso pode levar até 60 minutos. Acompanhe a notificação ou use /cancelar-pesquisa.</span>
                     </div>
                  </div>
                )}"""
content = re.sub(loading_pattern, loading_replacement, content)


with open('src/views/TaskExecutionView.tsx', 'w') as f:
    f.write(content)
