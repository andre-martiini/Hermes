import re

with open('src/views/TaskExecutionView.tsx', 'r') as f:
    content = f.read()

# Fix import onSnapshot
if 'onSnapshot' not in content:
    content = content.replace("import { doc, updateDoc, arrayUnion } from 'firebase/firestore';", "import { doc, updateDoc, arrayUnion, onSnapshot } from 'firebase/firestore';")

# Fix modal injection (it was not properly injected previously)
# We need to find the JSX return block and insert the modal
# Let's search for the root div in return (
#       <div className="flex flex-col h-full bg-[#1A1A1A] text-white">
root_pattern = r"(<div className=\"flex flex-col h-full bg-\[\#1A1A1A\] text-white\">)"
modal_jsx = """
      {showDeepResearchModal && (
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
"""
if "showDeepResearchModal &&" not in content:
    content = re.sub(root_pattern, r"\1\n" + modal_jsx, content, count=1)


# Also ensure currentUser is correctly accessed if not already in scope (we assume it's not, we should get it from auth)
if "currentUser?.email" in content and "import { getAuth } from 'firebase/auth';" not in content:
    content = content.replace("import { httpsCallable } from 'firebase/functions';", "import { httpsCallable } from 'firebase/functions';\nimport { getAuth } from 'firebase/auth';")
    # also add const auth = getAuth(); const currentUser = auth.currentUser;
    if "const confirmDeepResearch" in content:
         content = content.replace("const confirmDeepResearch = async () => {", "const confirmDeepResearch = async () => {\n    const auth = getAuth();\n    const currentUser = auth.currentUser;")

with open('src/views/TaskExecutionView.tsx', 'w') as f:
    f.write(content)

# Fix python backend firestore.firestore.SERVER_TIMESTAMP -> firestore.SERVER_TIMESTAMP
with open('functions/main.py', 'r') as f:
    backend_content = f.read()

backend_content = backend_content.replace("firestore.firestore.SERVER_TIMESTAMP", "firestore.SERVER_TIMESTAMP")

with open('functions/main.py', 'w') as f:
    f.write(backend_content)
