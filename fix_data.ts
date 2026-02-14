
import { db } from './firebase';
import { collection, getDocs, updateDoc, doc, deleteField } from 'firebase/firestore';

const today = new Date().toISOString().split('T')[0];

const fixData = async () => {
  try {
    console.log('Iniciando mesclagem de campos...');
    const tarefasCol = collection(db, 'tarefas');
    const snapshot = await getDocs(tarefasCol);

    for (const docRef of snapshot.docs) {
      const data = docRef.data();
      
      // Pegar campos antigos
      const desc = data.descricao || '';
      const obs = data.observacoes || '';
      
      // Se não tiver nada, pula ou coloca um placeholder
      if (!desc && !obs) continue;

      let notaMesclada = '';
      if (desc && obs) {
        notaMesclada = `${desc}\n\nObservações: ${obs}`;
      } else {
        notaMesclada = desc || obs;
      }

      // Criar o novo array de acompanhamento
      const novoAcompanhamento = [
        {
          data: today,
          nota: notaMesclada
        }
      ];

      // Atualizar o documento e remover campos antigos
      await updateDoc(doc(db, 'tarefas', docRef.id), {
        acompanhamento: novoAcompanhamento,
        descricao: deleteField(),
        observacoes: deleteField(),
        prioridade: deleteField() // Aproveitando para limpar prioridade também
      });

      console.log(`✔ Tarefa "${data.titulo}" (ID: ${docRef.id}) atualizada.`);
    }

    console.log('\nTodos os dados foram migrados para a Timeline com sucesso!');
    process.exit(0);
  } catch (error) {
    console.error('Erro ao processar dados:', error);
    process.exit(1);
  }
};

fixData();
