# 🚀 Guia Rápido - Hermes

## Iniciar o Sistema (Mais Fácil)

Basta executar:

```bash
.\start.bat
```

Isso abrirá automaticamente:
- ✅ Frontend web (http://localhost:5173)
- ✅ Sincronização com Google Tasks (em background)

## Ou Iniciar Manualmente

### Terminal 1: Frontend
```bash
npm run dev
```

### Terminal 2: Sincronização
```bash
python hermes_cli.py watch
```

## Como Usar

1. Abra http://localhost:5173
2. Clique em "Sync Google" para sincronizar tarefas
3. A sincronização acontece automaticamente!

## Estrutura

- `start.bat` - Inicia tudo automaticamente ⭐ **RECOMENDADO**
- `index.tsx` - Aplicação web principal
- `hermes_cli.py` - Script de sincronização
- `functions/` - Cloud Function (para deploy futuro)

## Próximos Passos (Opcional)

Se quiser deployar uma Cloud Function para não precisar rodar o script local:

1. Leia `functions/DEPLOY.md`
2. Execute `deploy_function.bat`

Mas para uso pessoal, o `start.bat` é mais simples e funciona perfeitamente!
