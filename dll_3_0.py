import os
import shutil
import sys
import platform
from log import configurar_logger

# Inicializa o logger
log = configurar_logger()

def resource_path(relative_path):
    """ Ajusta o caminho para PyInstaller ou modo script .py """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    # Procura na pasta onde o script atual está salvo
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

def obter_pasta_sistema_windows():
    """ 
    Detecta a pasta do Windows (C:, D:, etc) e retorna o caminho 
    correto para DLLs 32-bit (Firebird 32-bit).
    """
    # SystemRoot pega a letra do disco automática (ex: C:\Windows ou D:\Windows)
    pasta_windows = os.environ.get('SystemRoot') or os.environ.get('WINDIR')
    
    # Verifica se o Windows é 64 bits
    is_64bit_os = platform.machine().endswith('64') or os.environ.get('PROCESSOR_ARCHITEW6432')
    
    if is_64bit_os:
        # No Win 64-bit, DLLs 32-bit ficam na SysWOW64
        return os.path.join(pasta_windows, "SysWOW64")
    else:
        # No Win 32-bit, DLLs 32-bit ficam na System32
        return os.path.join(pasta_windows, "System32")

def semear_dependencias_fb3(diretorio_raiz_erp):
    """
    Copia as DLLs do FB 3.0 para a raiz do ERP, subpastas e sistema Windows.
    """
    NOME_PASTA_RECURSO = "dlls_fb3"
    dlls_para_copiar = ["fbclient.dll", "msvcp100.dll", "msvcr100.dll"]
    
    # 1. Lista de subpastas do ERP (Mercosistem)
    subpastas_erp = ["", "Caixa", "IntegradorECommerce", "PreVenda", "Copex"]
    
    # 2. Adiciona a pasta do sistema Windows na lista de alvos
    pasta_sistema = obter_pasta_sistema_windows()
    
    caminho_origem_recurso = resource_path(NOME_PASTA_RECURSO)

    if not os.path.exists(caminho_origem_recurso):
        log.error(f"Erro crítico: Pasta '{NOME_PASTA_RECURSO}' não encontrada na origem.")
        return False

    # --- PARTE 1: SEMEAR NO ERP ---
    log.info(f"Distribuindo DLLs nas pastas do ERP em: {diretorio_raiz_erp}")
    for sub in subpastas_erp:
        destino = os.path.join(diretorio_raiz_erp, sub)
        if os.path.exists(destino):
            for dll in dlls_para_copiar:
                copiar_arquivo(os.path.join(caminho_origem_recurso, dll), os.path.join(destino, dll))
        elif sub:
            log.info(f"Subpasta {sub} não encontrada no ERP. Pulando...")

    # --- PARTE 2: SEMEAR NO WINDOWS ---
    log.info(f"Distribuindo DLLs no sistema Windows: {pasta_sistema}")
    for dll in dlls_para_copiar:
        copiar_arquivo(os.path.join(caminho_origem_recurso, dll), os.path.join(pasta_sistema, dll))

    return True

def copiar_arquivo(origem, destino):
    """ Função auxiliar para copiar e sobrescrever com tratamento de erro """
    if not os.path.exists(origem):
        log.warning(f"Origem não encontrada: {origem}")
        return

    try:
        if os.path.exists(destino):
            os.chmod(destino, 0o777) # Tira o "Somente Leitura" se houver
        shutil.copy2(origem, destino)
        log.info(f"Sucesso: {os.path.basename(destino)} -> {os.path.dirname(destino)}")
    except PermissionError:
        log.error(f"ERRO: Arquivo em uso (Acesso Negado) em: {destino}")
    except Exception as e:
        log.error(f"Erro ao copiar para {destino}: {e}")

if __name__ == "__main__":
    # Teste Seguro: Cria uma pasta de simulação para não sujar o projeto
    pasta_teste = os.path.join(os.path.abspath("."), "Simulacao_Instalacao")
    if not os.path.exists(pasta_teste):
        os.makedirs(os.path.join(pasta_teste, "Caixa"))
    
    print(f"Iniciando teste de distribuição simulada em: {pasta_teste}")
    semear_dependencias_fb3(pasta_teste)