import os
import re
from encontrar_gbak import gbak_path
import subprocess
from log import configurar_logger

# Inicialização do logger para registrar as etapas da configuração
log = configurar_logger()

def obter_pasta_firebird():
    """
    Retorna o diretório raiz da instalação do Firebird baseando-se no caminho do gbak.
    Sobe dois níveis a partir da pasta /bin para encontrar a pasta principal.
    """
    return os.path.dirname(os.path.dirname(gbak_path))


def configurar_retrocompatibilidade():
    """
    Modifica o arquivo firebird.conf para permitir que sistemas antigos 
    continuem se conectando ao Firebird 3.0 (Legacy Auth).
    """
    pasta_fb = obter_pasta_firebird()
    conf_path = os.path.join(pasta_fb, "firebird.conf")

    # Valida se o arquivo de configuração existe no caminho mapeado
    if not os.path.exists(conf_path):
        log.error(f"firebird.conf não encontrado em: {conf_path}")
        return False

    with open(conf_path, "r", encoding="utf-8") as f:
        conteudo = f.read()

    # Mapeamento de chaves que precisam ser alteradas para suportar conexões legadas
    # Srp é o padrão novo, Legacy_Auth permite o padrão antigo de senhas
    ajustes = {
        "AuthServer": "AuthServer = Srp, Legacy_Auth",
        "AuthClient": "AuthClient = Srp, Legacy_Auth",
        "WireCrypt": "WireCrypt = Enabled", # Permite conexão sem criptografia obrigatória se necessário
        "UserManager": "UserManager = Srp, Legacy_UserManager"
    }

    # Aplica as alterações usando Regex para substituir linhas comentadas ou já existentes
    for chave, valor in ajustes.items():
        conteudo = re.sub(rf"#?{chave}.*", valor, conteudo)

    # Grava as novas configurações de volta no arquivo
    with open(conf_path, "w", encoding="utf-8") as f:
        f.write(conteudo)

    log.info("Retrocompatibilidade configurada com sucesso.")
    return True


def reiniciar_servico_firebird():
    """
    Reinicia o serviço do Firebird no Windows para que as alterações do 
    arquivo .conf entrem em vigor imediatamente.
    """
    try:
        # Utiliza o comando 'net' do Windows para parar e iniciar a instância padrão
        subprocess.run(["net", "stop", "FirebirdServerDefaultInstance"], stdout=subprocess.DEVNULL)
        subprocess.run(["net", "start", "FirebirdServerDefaultInstance"], stdout=subprocess.DEVNULL)
        log.info("Serviço Firebird reiniciado com sucesso.")
        return True
    except Exception as e:
        log.error(f"Erro ao reiniciar serviço: {e}", exc_info=True)
        return False