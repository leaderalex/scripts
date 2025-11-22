import os
import base64
import requests
import shutil
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# === Настройки ===
KEITARO_API_URL = "http://1.1.1./admin_api/v1/offers"
API_KEY = "21r2rgetr32fgetr23r3gte"

ARCHIVE_DIR = "./All-offers"
RESULT_DIR = "./result"

os.makedirs(RESULT_DIR, exist_ok=True)

# Настраиваем сессию с повторными попытками
session = requests.Session()
retry = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retry)
session.mount("http://", adapter)
session.mount("https://", adapter)


def upload_archive(zip_path, name):
    with open(zip_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "offer_type": "local",
        "action_type": "local_file",
        "action_payload": "payload",
        "archive": f"data:application/zip;base64,{encoded}",
        "name": name,
    }

    headers = {"Api-Key": API_KEY, "Content-Type": "application/json"}

    try:
        response = session.post(
            KEITARO_API_URL, json=payload, headers=headers, verify=False, timeout=30
        )

        if response.status_code == 200:
            print(f"✅ Загружен: {name}")
            return True
        elif response.status_code == 422 and "Name has already used" in response.text:
            print(f"⚠️ Уже существует (но считаем успехом): {name}")
            return True
        else:
            print(
                f"❌ Ошибка при загрузке {name}: {response.status_code} | {response.text}"
            )
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка при загрузке {name}: {str(e)}")
        return False


# Проходим по архивам
for file_name in os.listdir(ARCHIVE_DIR):
    if file_name.endswith(".zip"):
        file_path = os.path.join(ARCHIVE_DIR, file_name)
        offer_name = os.path.splitext(file_name)[0]  # Название без .zip

        if upload_archive(file_path, offer_name):
            result_path = os.path.join(RESULT_DIR, file_name)
            shutil.move(file_path, result_path)
            print(f"📁 Перемещён в result: {file_name}")
