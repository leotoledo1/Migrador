import os
import re
from encontrar_gbak import gbak_path
import subprocess
from log import configurar_logger
log = configurar_logger()

def obter_pasta_firebird():
    return os.path.dirname(os.path.dirname(gbak_path))


def configurar_retrocompatibilidade():
    pasta_fb = obter_pasta_firebird()
    conf_path = os.path.join(pasta_fb, "firebird.conf")

    if not os.path.exists(conf_path):
        log.error(f"firebird.conf não encontrado em: {conf_path}")
        return False

    with open(conf_path, "r", encoding="utf-8") as f:
        conteudo = f.read()

    ajustes = {
        "AuthServer": "AuthServer = Srp, Legacy_Auth",
        "AuthClient": "AuthClient = Srp, Legacy_Auth",
        "WireCrypt": "WireCrypt = Enabled",
        "UserManager": "UserManager = Srp, Legacy_UserManager"
    }

    for chave, valor in ajustes.items():
        conteudo = re.sub(rf"#?{chave}.*", valor, conteudo)

    with open(conf_path, "w", encoding="utf-8") as f:
        f.write(conteudo)

    log.info("Retrocompatibilidade configurada com sucesso.")
    return True


def reiniciar_servico_firebird():
    try:
        subprocess.run(["net", "stop", "FirebirdServerDefaultInstance"], stdout=subprocess.DEVNULL)
        subprocess.run(["net", "start", "FirebirdServerDefaultInstance"], stdout=subprocess.DEVNULL)
        log.info("Serviço Firebird reiniciado com sucesso.")
        return True
    except Exception as e:
        log.error(f"Erro ao reiniciar serviço: {e}", exc_info=True)
        return False