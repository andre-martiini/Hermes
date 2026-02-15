"""
Script de setup para verificar as credenciais do Google Tasks
As credenciais OAuth já existem em token.json e serão usadas pela Cloud Function
"""

import os
import sys

def setup_credentials():
    """
    Verifica se as credenciais OAuth já existem
    """
    # Volta para o diretório raiz
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    token_path = os.path.join(root_dir, 'token.json')
    creds_path = os.path.join(root_dir, 'credentials.json')
    
    print("\n🔍 Verificando credenciais do Google Tasks...\n")
    
    # Verifica credentials.json
    if not os.path.exists(creds_path):
        print("❌ ERRO: 'credentials.json' não encontrado!")
        print("   Baixe do Google Cloud Console e coloque na raiz do projeto.")
        return False
    else:
        print("✅ credentials.json encontrado")
    
    # Verifica token.json
    if not os.path.exists(token_path):
        print("❌ ERRO: 'token.json' não encontrado!")
        print("   Execute 'python hermes_cli.py watch' uma vez para gerar o token.")
        return False
    else:
        print("✅ token.json encontrado")
    
    print("\n" + "="*50)
    print("✅ CREDENCIAIS VERIFICADAS COM SUCESSO!")
    print("="*50)
    print("\n📝 PRÓXIMO PASSO:")
    print("   Execute: deploy_function.bat")
    print("\n💡 NOTA:")
    print("   A Cloud Function usará as credenciais do token.json")
    print("   automaticamente durante o deploy.")
    print("\n")
    
    return True

if __name__ == '__main__':
    success = setup_credentials()
    sys.exit(0 if success else 1)
