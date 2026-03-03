import unittest

class TestSyncTasksPayload(unittest.TestCase):
    def test_payload_format(self):
        # Moca o dicionário de tarefa
        tarefas = [
            {"status": "concluído", "data_limite": "2026-03-03", "horario_inicio": "14:30"},
            {"status": "em andamento", "data_limite": "2026-03-03", "horario_inicio": None},
            {"status": "em andamento", "data_limite": "-", "horario_inicio": None},
        ]

        results = []
        for t in tarefas:
            g_status = 'completed' if t.get('status') == 'concluído' else 'needsAction'
            if t.get('data_limite') and t.get('data_limite') != '-':
                if t.get('horario_inicio'):
                    g_due = f"{t.get('data_limite')}T{t['horario_inicio']}:00.000Z"
                else:
                    g_due = f"{t.get('data_limite')}T00:00:00.000Z"
            else:
                g_due = None
            results.append((g_status, g_due))

        # Check tempo exato:
        self.assertEqual(results[0][1], "2026-03-03T14:30:00.000Z")
        self.assertEqual(results[0][0], "completed")

        # Check dia inteiro
        self.assertEqual(results[1][1], "2026-03-03T00:00:00.000Z")
        self.assertEqual(results[1][0], "needsAction")

        # Check sem data
        self.assertIsNone(results[2][1])

if __name__ == '__main__':
    unittest.main()
