
import { db } from './firebase';
import { collection, doc, setDoc } from 'firebase/firestore';
import tarefas from './tarefas_andre.json';
import atividades from './atividades_fevereiro.json';

const migrate = async () => {
  try {
    console.log('Iniciando migração...');

    // Migrar Tarefas
    for (const tarefa of tarefas) {
      await setDoc(doc(collection(db, 'tarefas'), tarefa.id), tarefa);
      console.log(`Tarefa ${tarefa.id} migrada`);
    }

    // Migrar Atividades
    for (const atividade of atividades) {
      await setDoc(doc(collection(db, 'atividades'), atividade.id), atividade);
      console.log(`Atividade ${atividade.id} migrada`);
    }

    console.log('Migração concluída com sucesso!');
    process.exit(0);
  } catch (error) {
    console.error('Erro na migração:', error);
    process.exit(1);
  }
};

migrate();
