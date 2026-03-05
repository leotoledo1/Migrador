import subprocess
import os
from datetime import datetime
import sys
import time
from dotenv import load_dotenv
from retrocompatibilidade import configurar_retrocompatibilidade, reiniciar_servico_firebird

# --- GERENCIAMENTO DE RECURSOS ---
def resource_path(relative_path):
    """ 
    Ajusta o caminho dos arquivos (como o .env) para que funcionem 
    tanto rodando o script .py quanto rodando o executável (.exe) gerado pelo PyInstaller.
    """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# Carrega as variáveis de ambiente sensíveis (senhas e hosts)
caminho_env = resource_path(".env")
if os.path.exists(caminho_env):
    load_dotenv(caminho_env)
else:
    raise Exception("Erro crítico: Arquivo .env não encontrado.")

# Captura das credenciais via variáveis de ambiente
FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS_PREFIX = os.getenv("FTP_PASS_PREFIX")
FB_USER = os.getenv("FB_USER")
FB_PASS = os.getenv("FB_PASS")

# Importações de módulos locais do projeto
from encontrar_gbak import gbak_path
from emcontrar_caminho import caminho_base, encontrar_banco_base, capturar_portas_firebird, obter_bases
from log_discord import enviar_log_discord
import fdb
import re 
import shutil
import ftplib
from interface import mostrar_loading
from log import configurar_logger
from desinstalar import desinstalar_firebird_25
from desinstalar import parar_servico_firebird
from encontrar_gbak3_0 import encontrar_gbak_30

log = configurar_logger()

# --- PREPARAÇÃO DO AMBIENTE ---
# Define bases e pastas onde os arquivos temporários de backup serão gerados
base = caminho_base()
empresa_db = encontrar_banco_base(base)

if not empresa_db:
    raise Exception("Nenhum banco base encontrado (EMPRESA.GDB ou GESTAO.FDB)")

portas_firebird = capturar_portas_firebird()

bases = obter_bases(empresa_db, portas_firebird) if empresa_db.lower().endswith("empresa.gdb") else [empresa_db]

PASTA_RAIZ = "Migracao_Firebird"
PASTA_BACKUP = os.path.join(PASTA_RAIZ, "backup2_5")
PASTA_RESTORE = os.path.join(PASTA_RAIZ, "restore3_0")

os.makedirs(PASTA_BACKUP, exist_ok=True)
os.makedirs(PASTA_RESTORE, exist_ok=True)
log.info(f"Pasta de backup: {PASTA_BACKUP}")
log.info(f"Pasta de restore: {PASTA_RESTORE}")

def matar_atualizador():
    """Encerra processos que podem travar o acesso exclusivo ao banco de dados."""
    processos = [
        "atualizador.exe",
        "Gestao.exe",
        "DataSnap.exe",
        "IntegradorECommerce.exe",
        "PreVenda.exe",
        "Caixa.exe",
        "ReplServer.exe",
        "ReplServer.exe"
    ]
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE  # Executa sem abrir janela do CMD

        for processo in processos:
            subprocess.run(
                ["taskkill", "/F", "/IM", processo],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                startupinfo=si
            )

        log.info("Processos finalizados (se estavam em execução).")

    except Exception as e:
        log.warning(f"Erro ao tentar finalizar processos: {e}")


def buscar_cod_empresa(dsn):
    """Busca o NUMSERIE apenas se for GESTAO.FDB."""
    # Extrai o nome do arquivo do DSN
    nome_arquivo = os.path.basename(dsn.split(":")[-1]).upper()

    if "GESTAO.FDB" not in nome_arquivo:
        log.info(f"Banco {nome_arquivo} não possui NUMSERIE. Usando DESCONHECIDO.")
        return "DESCONHECIDO"

    try:
        conn = fdb.connect(dsn=dsn, user=FB_USER, password=FB_PASS)
        cur = conn.cursor()
        cur.execute("SELECT FIRST 1 NUMSERIE FROM EMPRESA")
        row = cur.fetchone()
        conn.close()

        codigo = re.sub(r"[^0-9\-]", "", str(row[0])) if row and row[0] else None
        log.info(f"Código da empresa encontrado: {codigo if codigo else 'DESCONHECIDO'}")
        return codigo or "DESCONHECIDO"

    except Exception as e:
        log.warning(f"Não foi possível obter NUMSERIE do banco {nome_arquivo}: {e}")
        return "DESCONHECIDO"


def compactar_fbk(fbk_file):
    """Compacta o .fbk em formato ZIP."""

    base_name, _ = os.path.splitext(fbk_file)
    zip_name = base_name + ".zip"

    shutil.make_archive(
        base_name,  
        "zip",
        root_dir=os.path.dirname(fbk_file),
        base_dir=os.path.basename(fbk_file)
    )

    return zip_name

def enviar_ftp(zip_name, codigo_empresa):
    """ Realiza o upload do arquivo compactado para o servidor FTP da empresa. """
    try:
        senha = FTP_PASS_PREFIX + datetime.now().strftime("%d%m%y")
        ftp = ftplib.FTP(FTP_HOST)
        ftp.login(FTP_USER, senha)
        pasta = f"/ENTRADAS/{codigo_empresa}"
        try: ftp.mkd(pasta) 
        except: pass  
        ftp.cwd(pasta)
        with open(zip_name, "rb") as arq:
            ftp.storbinary(f"STOR {os.path.basename(zip_name)}", arq)
        ftp.quit()
    except Exception as e:
        log.error(f"Erro ao enviar FTP (empresa {codigo_empresa})", exc_info=True)

def instalar_firebird_30():
    try:
        caminho_instalador = resource_path(
            os.path.join("instaladorfb30", "Firebird3.0.exe")
        )

        if not os.path.exists(caminho_instalador):
            log.error("Instalador do Firebird 3.0 não encontrado.")
            return False

        log.info("Iniciando instalação do Firebird 3.0...")

        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE

        subprocess.run(
            [caminho_instalador, "/verysilent", "/norestart"],
            check=True,
            startupinfo=si
        )

        log.info("Firebird 3.0 instalado com sucesso!")
        return True

    except Exception as e:
        log.error(f"Erro ao instalar Firebird 3.0: {e}")
        return False
    
def restaurar_no_fb30(fbk_path, destino_fdb):
    gbak_30 = encontrar_gbak_30()

    if not gbak_30:
        log.error("gbak 3.0 não encontrado.")
        return False
    try:
        log.info("Iniciando restore no Firebird 3.0...")

        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE

        subprocess.run([
            gbak_30,
            "-c",
            "-p", "4096",
            "-user", FB_USER,
            "-password", FB_PASS,
            fbk_path,
            destino_fdb
        ], check=True, startupinfo=si)

        if any(x in fbk_path.upper() for x in ["EMPRESA.GDB", "REPLICADOR.FDB"]):
            log.info(f"FBK mantido (não excluído): {fbk_path}")
        else:
            try:
                os.remove(fbk_path)
                log.info(f"FBK removido após restore: {fbk_path}")
            except Exception as e:
                log.warning(f"Não foi possível remover o FBK: {e}")

        log.info("Restore no Firebird 3.0 concluído com sucesso!")
        return True

    except Exception as e:
        log.error(f"Erro no restore FB 3.0: {e}", exc_info=True)
        return False

    except Exception as e:
        log.error(f"Erro no restore FB 3.0: {e}", exc_info=True)
        return False
    

def rodar_backup(callback_progresso):
    """
    Executa o ciclo:
    1. Backup (.fbk)
    2. Compactação (.zip)
    3. Upload FTP
    """

    total_bases = len(bases)

    for idx, dsn in enumerate(bases):
        inicio_cronometro = time.time()

        try:
            cod_empresa = buscar_cod_empresa(dsn) or "DESCONHECIDO"

            progresso_base = idx / total_bases
            incremento_etapa = 1.0 / total_bases / 3  # agora são 3 etapas

            log.info(f"Iniciando processamento da base: {dsn}")
            callback_progresso(progresso_base)

            # Nome do arquivo
            nome_base = os.path.basename(dsn.split(":")[-1]).replace(".FDB", "")
            data = datetime.now().strftime("%Y%m%d_%H%M%S")
            nome_arquivo = f"{nome_base}_{cod_empresa}_{data}"

            fbk = os.path.join(PASTA_BACKUP, f"{nome_arquivo}.fbk")

            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE

            # 🔥 1️⃣ BACKUP
            log.info(f"Executando GBAK Backup para: {fbk}")

            subprocess.run([
                gbak_path,
                "-b",
                "-ig",
                "-l",
                "-user", FB_USER,
                "-password", FB_PASS,
                dsn,
                fbk
            ], check=True, startupinfo=si)
            
            callback_progresso(progresso_base + incremento_etapa)
            log.info("Backup físico (.fbk) gerado com sucesso.")

            # 🔥 2️⃣ COMPACTAÇÃO DO FBK
            log.info("Compactando arquivo FBK...")
            zip_fbk = fbk.replace(".fbk", ".zip")

            shutil.make_archive(
                zip_fbk.replace(".zip", ""),
                "zip",
                root_dir=os.path.dirname(fbk),
                base_dir=os.path.basename(fbk)
            )


            callback_progresso(progresso_base + (incremento_etapa * 2))
            log.info(f"Compactação finalizada: {zip_fbk}")

            # 🔥 3️⃣ ENVIO FTP
            log.info(f"Enviando arquivo para o FTP da empresa {cod_empresa}...")

            enviar_ftp(zip_fbk, cod_empresa)
            if os.path.exists(zip_fbk) and not any(x in zip_fbk.upper() for x in ["EMPRESA.GDB", "REPLICADOR.FDB"]):
                os.remove(zip_fbk)
                log.info("ZIP removido após envio FTP.")
            else:
                log.info(f"ZIP mantido (não excluído): {zip_fbk}")


            callback_progresso(progresso_base + (incremento_etapa * 3))
            log.info("Upload concluído!")
            
            tempo_total_segundos = time.time() - inicio_cronometro
            minutos = int(tempo_total_segundos // 60)
            segundos = int(tempo_total_segundos % 60)

            enviar_log_discord(
                status="sucesso",
                codigo_empresa=cod_empresa,
                mensagem=f"Migrado com sucesso 3.0 {nome_base}",
                detalhes=(
                    f"Empresa: {cod_empresa}\n"
                    f"Tempo: {minutos}m {segundos}s\n" )    
            )

        except Exception as e:
            log.error(f"Erro no processamento da base {dsn}: {e}", exc_info=True)

            tempo_total_segundos = time.time() - inicio_cronometro
            minutos = int(tempo_total_segundos // 60)
            segundos = int(tempo_total_segundos % 60)

            enviar_log_discord(
                status="erro",
                codigo_empresa=cod_empresa,
                mensagem=f"❌ Falha no backup: {nome_base}",
                detalhes=f"⏱️ Tentativa durou: {minutos}m {segundos}s\n⚠️ Erro: {str(e)}"
            )

    callback_progresso(1.0)



def migrar_firebird():
    log.info("Parando Firebird 2.5...")
    parar_servico_firebird()

    log.info("Desinstalando Firebird 2.5...")
    if not desinstalar_firebird_25(gbak_path):
        log.error("Falha ao remover Firebird 2.5.")
        return False

    log.info("Instalando Firebird 3.0...")
    if not instalar_firebird_30():
        log.error("Falha ao instalar Firebird 3.0.")
        return False

    if configurar_retrocompatibilidade():
        reiniciar_servico_firebird()
        return True

    return False


def processo_completo(callback):
    log.info("Finalizando processos...")
    matar_atualizador()

    log.info("INICIANDO BACKUP 2.5")
    rodar_backup(callback)
    log.info("BACKUP FINALIZADO")

    log.info("INICIANDO MIGRAÇÃO PARA 3.0")

    if not migrar_firebird():
        log.critical("Falha na migração estrutural.")
        return

    log.info("Migração estrutural concluída.")

    # RESTORE
    for arquivo in os.listdir(PASTA_BACKUP):
        if arquivo.endswith(".fbk"):
            fbk_path = os.path.join(PASTA_BACKUP, arquivo)
            destino = os.path.join(PASTA_RESTORE, arquivo.replace(".fbk", "_fb30.FDB"))

            sucesso = restaurar_no_fb30(fbk_path, destino)

            if sucesso:
                try:
                    os.remove(fbk_path)
                    log.info(f"FBK removido após restore com sucesso: {fbk_path}")
                except Exception as e:
                    log.warning(f"Não foi possível remover o FBK: {e}")
    log.info("PROCESSO COMPLETO FINALIZADO")

if __name__ == "__main__":
    try:
        mostrar_loading(processo_completo)
    except Exception as e:
        log.critical(f"Erro geral no processo principal: {e}", exc_info=True)