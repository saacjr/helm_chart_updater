import requests
import base64
from threading import Semaphore, Thread
import time
import yaml
import sys
import logging

def setup_logger(name, log_file, level=logging.INFO):
    handler = logging.FileHandler(log_file)        
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.addHandler(logging.StreamHandler(sys.stdout))
    return logger

random_tag = int(time.time())
versions_log = setup_logger('versions_log', f'./versions/versions_log_{random_tag}.log')
process_log = setup_logger('process_log', f'./logs/process_log_{random_tag}.log')

BASE_URL_FONTES = '<fontes>'
BASE_URL_CANAIS = '<canais>'
TOKEN_CANAIS = '<token>'
TOKEN_FONTES = '<token>'
MAX_THREADS = 10
SEMAPHORE = Semaphore(MAX_THREADS)

def get_repo_name(repo_url: str) -> str:
    repo_name = repo_url.rsplit('/', 1)[-1]
    if '.' in repo_name:
        repo_name = repo_name.split('.')[0]
    print(repo_name)
    return repo_name

def get_base_url(repo_url):
    if 'canais.fontes' in repo_url:
        BASE_URL = BASE_URL_CANAIS
    else:
        BASE_URL = BASE_URL_FONTES
    return BASE_URL

def get_token(repo_url):
    if 'canais.fontes' in repo_url:
        TOKEN = TOKEN_CANAIS
    else:
        TOKEN = TOKEN_FONTES
    return TOKEN

def get_url_search(repo_url):
    repo_name = get_repo_name(repo_url)
    search_path = f'/projects?search={repo_name}&simple=true&order_by=similarity'
    BASE_URL = get_base_url(repo_url)
    URL = BASE_URL + search_path
    return URL

def get_project_id_path(repo_url : str) -> dict:
    URL, TOKEN = get_url_search(repo_url), get_token(repo_url)
    repo_name = get_repo_name(repo_url)

    response = requests.get(URL, headers={'PRIVATE-TOKEN': TOKEN}, verify=False)
    if response.status_code != 200: print(f'Failed to get projects: {response.json()}')
    data = response.json()
    if len(data) == 0: 
        print(f'Repositório não encontrado: {repo_name}')
        return {}

    project = data[0]
    return {'id': project['id'], 'path': project['path_with_namespace']}

def get_repository_file_content(repo_url, file_path):
    repo = get_project_id_path(repo_url)
    BASE_URL = get_base_url(repo_url)
    TOKEN = get_token(repo_url)
    try:
        URL = BASE_URL + f'/projects/{repo["id"]}/repository/files/{file_path}?ref=master'
        response = requests.get(URL, headers={'PRIVATE-TOKEN': TOKEN}, verify=False)
        content = base64.b64decode(response.json()['content']).decode('utf-8')
    except Exception:
        raise Exception(f'ERROR: {repo["path"]} não possui o arquivo {file_path}')
    return content

def update_chart_version(contents):
    if  contents['apiVersion'] == 'v1':
        contents['apiVersion'] = 'v2'
    return contents

def include_deps_chart(contents, requirements):
    contents = update_chart_version(contents)
    if contents.get('dependencies'):
        contents['dependencies'] = {}
    dependencies = requirements.get('dependencies')
    if dependencies is not None:
        contents['dependencies'] = dependencies
    return contents

def update_repository_chart(repo_url, file, commit_message):
    BASE_URL = get_base_url(repo_url)
    TOKEN = get_token(repo_url)
    repo = get_project_id_path(repo_url)
    URL = BASE_URL + f'/projects/{repo["id"]}/repository/commits'
    body = {
        'branch': 'master', 
        'commit_message': commit_message,  
        'actions': [{
            'action': 'update', 
            'file_path': 'Chart.yaml',
            'content': file
        }]
    }
    response = requests.post(URL, json=body, headers={'PRIVATE-TOKEN': TOKEN}, verify=False)
    return response

def update_chart_file(repo_url):
    repo = get_project_id_path(repo_url)
    try:
        file = get_repository_file_content(repo_url, 'Chart.yaml')
        contents = yaml.safe_load(file)

        print('CHART: ',contents)

        requirements_file = get_repository_file_content(repo_url, 'requirements.yaml')
        requirements = yaml.safe_load(requirements_file)
        
        print('REQUIREMENTS: ', requirements)

        contents = include_deps_chart(contents, requirements)
        #RETIRAR TESTE AO RODAR EM PRODUÇÃO
        commit_message = "Update do Helm Chart para versão 3 #teste"
        file = yaml.dump(contents)
        response = update_repository_chart(repo_url, file, commit_message)
        if response.status_code == 201:
            process_log.info(f'{repo["path"]} : repositório alterado com sucesso')
            print(f'{repo["path"]} : repositório alterado com sucesso')
        else:
            print(f'{repo["path"]} : erro ao alterar repositório : {response.json()}')
    except Exception as e:
        process_log.info(f'{repo["path"]} : erro ao alterar repositório : {e}')
    finally:
        SEMAPHORE.release()


if __name__=='__main__':
    print('Teste de alteração no ambiente de desenvolvimento')
    repo_url = "<url_teste>"
    SEMAPHORE.acquire()
    Thread(
        target=update_chart_file, 
        args=[repo_url]
    ).start()
