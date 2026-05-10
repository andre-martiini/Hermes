import sys

def fix_classification():
    path = r'C:\Users\T-GAMER\Documents\gestao-Hermes\functions\main.py'
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    found = False
    for i in range(len(lines)):
        if 'CLASSIFICAÇÃO:' in lines[i] and 'NIVEL_1 (Crítico): contradição lógica clara' in lines[i+1]:
            # Found the block to replace.
            new_classification = [
                'CLASSIFICAÇÃO:\n',
                '- NIVEL_1 (Crítico): Erro lógico real (ex: planejar algo para o passado ou pós-conclusão), gargalo crítico esquecido.\n',
                '- NIVEL_2 (Otimização): Sugestão de melhoria ou passo faltante.\n',
                '- NIVEL_3 (Ideia Criativa): Conexões estratégicas ou ideias laterais.\n',
                '- SEM_INSIGHT: situação adequada.\n',
                '\n',
                'REGRAS ADICIONAIS:\n',
                '- NUNCA critique a "Data de Execução" se ela for antes do evento mencionado (isso é ANTECIPAÇÃO).\n',
                '- Só critique a "Data de Execução" se ela for DEPOIS do "Prazo Final" (se existir).\n',
                '- Seja conciso e evite ser óbvio.\n'
            ]
            # Replace lines[i:i+5]
            lines[i:i+5] = new_classification
            found = True
            break
    
    if found:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print("Classification updated successfully.")
    else:
        print("Could not find classification block.")

if __name__ == "__main__":
    fix_classification()
