import os
import subprocess
import logging


log = logging.getLogger(__name__)

def parar_servico_firebird():
    log.info("Parando serviço Firebird 2.5...")
    subprocess.run(["net", "stop", "FirebirdServerDefaultInstance"], shell=True)

def desinstalar_firebird_25(gbak_path):
    log.info("Iniciando desinstalação do Firebird 2.5...")

    # sobe duas pastas (bin -> Firebird_2_5)
    pasta_firebird = os.path.dirname(os.path.dirname(gbak_path))
    uninstaller = os.path.join(pasta_firebird, "unins000.exe")

    if not os.path.exists(uninstaller):
        log.error("Uninstaller do Firebird 2.5 não encontrado!")
        return False

    try:
        subprocess.run([
            uninstaller,
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART"
        ], check=True)

        log.info("Firebird 2.5 removido com sucesso.")
        return True

    except subprocess.CalledProcessError as e:
        log.error(f"Erro ao desinstalar Firebird 2.5: {e}")
        return False