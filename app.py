import os
import importlib.util
import sys

# Adiciona a pasta sistemapousada ao caminho de busca do Python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(BASE_DIR, 'sistemapousada')
sys.path.insert(0, APP_DIR)

# Carrega o app do arquivo interno
spec = importlib.util.spec_from_file_location('sistemapousada_app', os.path.join(APP_DIR, 'app.py'))
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
app = app_module.app

if __name__ == '__main__':
    # ... resto do código ...
