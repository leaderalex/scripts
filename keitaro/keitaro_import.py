#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Импорт офферов или лендингов в Keitaro из ранее экспортированных архивов.
Автоматически создает группы если их нет, загружает ZIP-архивы.
Работает с результатами скрипта keitaro_universal_export.py


# Keitaro API настройки (источник для экспорта)
KEITARO_TRACKER_URL=https://your-tracker-domain.com
KEITARO_API_KEY=your-api-key-here

# Keitaro API настройки (цель для импорта)
KEITARO_TARGET_URL=https://your-target-tracker-domain.com
KEITARO_TARGET_API_KEY=your-target-api-key-here


"""

import os
import csv
import json
import time
import requests
from datetime import datetime
from pathlib import Path

# ======================== CONFIG ========================
CONFIG = {
    "BASE_URL": None,  # будет загружено из .env
    "API_KEY": None,   # будет загружено из .env

    # ========== НАСТРОЙКИ ИМПОРТА ==========
    "IMPORT_TYPE": "offers",  # "offers" или "landings"
    "IMPORT_DIR": None,  # путь к папке с экспортом (например: "offer_exports_20250103_123456")
    # =======================================

    "TIMEOUT": 90,
    "SLEEP_BETWEEN": 0.3,  # сек между запросами
    "CREATE_GROUPS": True,  # создавать группы если их нет
    "SKIP_EXISTING": True,  # пропускать если уже есть с таким именем
}
# ====================== /CONFIG ========================


def load_config_from_env():
    """Загрузить настройки из .env файла"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        CONFIG["BASE_URL"] = os.getenv("KEITARO_TARGET_URL") or os.getenv("KEITARO_TRACKER_URL")
        CONFIG["API_KEY"] = os.getenv("KEITARO_TARGET_API_KEY") or os.getenv("KEITARO_API_KEY")
    except ImportError:
        print("[WARNING] dotenv не установлен, используйте переменные окружения")


def _session(api_key: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "Api-Key": api_key,
            "Accept": "application/json",
        }
    )
    return s


def _api(base: str, path: str) -> str:
    base = base.rstrip("/")
    path = path.lstrip("/")
    return f"{base}/admin_api/v1/{path}"


def detect_landings_endpoint(
    s: requests.Session, base: str, timeout: int
) -> str:
    """Определяет правильный эндпоинт для лендингов"""
    for ep in ("landing_pages", "landings"):
        url = _api(base, f"{ep}?per_page=1")
        try:
            r = s.get(url, timeout=timeout)
            if r.status_code == 200:
                return ep
        except requests.RequestException:
            pass
    raise RuntimeError("Не удалось определить эндпоинт лендингов")


def get_all_groups(s: requests.Session, base: str, timeout: int) -> dict:
    """Получить все группы. Возвращает {name: id}"""
    groups = {}
    try:
        url = _api(base, "groups?per_page=500")
        r = s.get(url, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        items = data.get("data") if isinstance(data, dict) else data
        if items:
            for g in items:
                name = g.get("name") or g.get("title") or ""
                if name:
                    groups[name] = g.get("id")
    except requests.RequestException as e:
        print(f"[WARNING] Не удалось получить список групп: {e}")
    return groups


def create_group(s: requests.Session, base: str, group_name: str, timeout: int) -> int | None:
    """Создать группу. Возвращает ID группы"""
    try:
        url = _api(base, "groups")
        payload = {"name": group_name}
        r = s.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        group_id = data.get("id")
        print(f"    ✓ Создана группа: {group_name} (ID: {group_id})")
        return group_id
    except requests.RequestException as e:
        print(f"    ✗ Не удалось создать группу '{group_name}': {e}")
        return None


def get_existing_items(
    s: requests.Session, base: str, endpoint: str, timeout: int
) -> dict:
    """Получить существующие элементы. Возвращает {name: id}"""
    items = {}
    page = 1
    per_page = 200
    while True:
        try:
            url = _api(base, f"{endpoint}?per_page={per_page}&page={page}")
            r = s.get(url, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            entries = data.get("data") if isinstance(data, dict) else data
            if not entries:
                break
            for item in entries:
                name = item.get("name") or ""
                if name:
                    items[name] = item.get("id")

            # Проверяем пагинацию
            total_pages = None
            if isinstance(data, dict):
                meta = data.get("meta") or {}
                pagination = meta.get("pagination") or {}
                total_pages = pagination.get("total_pages")
            if not total_pages or page >= int(total_pages):
                break
            page += 1
        except requests.RequestException:
            break
    return items


def upload_zip(
    s: requests.Session,
    base: str,
    endpoint: str,
    zip_path: str,
    name: str,
    group_id: int | None,
    timeout: int,
) -> dict | None:
    """Загрузить ZIP-архив"""
    try:
        url = _api(base, f"{endpoint}/import")

        with open(zip_path, "rb") as f:
            files = {"file": (os.path.basename(zip_path), f, "application/zip")}
            data = {"name": name}
            if group_id:
                data["group_id"] = group_id

            r = s.post(url, files=files, data=data, timeout=timeout)
            r.raise_for_status()
            return r.json()
    except requests.RequestException as e:
        print(f"    ✗ Ошибка загрузки ZIP: {e}")
        return None


def create_from_json(
    s: requests.Session,
    base: str,
    endpoint: str,
    json_data: dict,
    name: str,
    group_id: int | None,
    timeout: int,
) -> dict | None:
    """Создать элемент из JSON данных"""
    try:
        url = _api(base, endpoint)

        # Базовые поля
        payload = {
            "name": name,
        }

        if group_id:
            payload["group_id"] = group_id

        # Копируем важные поля из JSON
        important_fields = [
            "archive_type",
            "state",
            "country",
            "action_type",
            "action_payload",
            "action_options",
            "notes",
        ]

        for field in important_fields:
            if field in json_data and json_data[field] is not None:
                payload[field] = json_data[field]

        r = s.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        print(f"    ✗ Ошибка создания из JSON: {e}")
        return None


def main():
    load_config_from_env()

    base = CONFIG["BASE_URL"]
    api_key = CONFIG["API_KEY"]
    import_type = CONFIG["IMPORT_TYPE"].lower()
    import_dir = CONFIG["IMPORT_DIR"]

    if not base or not api_key:
        print("❌ ОШИБКА: Не указаны KEITARO_TARGET_URL и KEITARO_TARGET_API_KEY в .env")
        print("   Или используйте KEITARO_TRACKER_URL и KEITARO_API_KEY")
        return

    if import_type not in ("offers", "landings"):
        print(f"❌ ОШИБКА: IMPORT_TYPE должен быть 'offers' или 'landings'")
        return

    if not import_dir:
        print("❌ ОШИБКА: Укажите IMPORT_DIR - путь к папке с экспортом")
        return

    if not os.path.isdir(import_dir):
        print(f"❌ ОШИБКА: Папка '{import_dir}' не найдена")
        return

    # Проверяем index.csv
    index_file = os.path.join(import_dir, "index.csv")
    if not os.path.isfile(index_file):
        print(f"❌ ОШИБКА: Файл '{index_file}' не найден")
        return

    timeout = CONFIG["TIMEOUT"]
    s = _session(api_key)

    # Определяем эндпоинт
    if import_type == "landings":
        endpoint = detect_landings_endpoint(s, base, timeout)
        item_type_ru = "лендинг"
    else:
        endpoint = "offers"
        item_type_ru = "оффер"

    print(f"[INFO] Режим импорта: {import_type.upper()}")
    print(f"[INFO] Эндпоинт: {endpoint}")
    print(f"[INFO] Целевой трекер: {base}")
    print(f"[INFO] Папка импорта: {import_dir}")
    print()

    # Получаем существующие группы
    print("[1/4] Получение списка групп...")
    groups_map = get_all_groups(s, base, timeout)
    print(f"    Найдено групп: {len(groups_map)}")

    # Получаем существующие элементы
    if CONFIG["SKIP_EXISTING"]:
        print(f"[2/4] Получение списка существующих {import_type}...")
        existing_items = get_existing_items(s, base, endpoint, timeout)
        print(f"    Найдено существующих: {len(existing_items)}")
    else:
        existing_items = {}
        print("[2/4] Пропуск проверки существующих (SKIP_EXISTING=False)")

    # Читаем index.csv
    print("[3/4] Чтение index.csv...")
    items_to_import = []
    with open(index_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            items_to_import.append(row)
    print(f"    Найдено записей: {len(items_to_import)}")

    # Импорт
    print(f"[4/4] Начинаем импорт...")
    print()

    total = 0
    success = 0
    skipped = 0
    failed_list = []

    for item in items_to_import:
        total += 1
        item_id = item.get("id")
        name = item.get("name")
        group_name = item.get("group")
        file_path = item.get("file_path")
        file_type = item.get("type")

        print(f"[{total}/{len(items_to_import)}] {item_type_ru.capitalize()}: {name}")

        # Пропускаем если уже есть
        if CONFIG["SKIP_EXISTING"] and name in existing_items:
            print(f"    ⊘ Пропущен (уже существует)")
            skipped += 1
            time.sleep(CONFIG["SLEEP_BETWEEN"])
            continue

        # Получаем или создаем группу
        group_id = None
        if group_name and group_name != CONFIG.get("GROUP_UNGROUPED", "__NO_GROUP__"):
            if group_name in groups_map:
                group_id = groups_map[group_name]
            elif CONFIG["CREATE_GROUPS"]:
                group_id = create_group(s, base, group_name, timeout)
                if group_id:
                    groups_map[group_name] = group_id

        # Полный путь к файлу
        full_path = os.path.join(import_dir, file_path)

        if not os.path.isfile(full_path):
            print(f"    ✗ Файл не найден: {full_path}")
            failed_list.append(
                {"id": item_id, "name": name, "reason": "file_not_found"}
            )
            continue

        # Импортируем
        result = None
        if file_type == "zip":
            print(f"    → Загрузка ZIP...")
            result = upload_zip(s, base, endpoint, full_path, name, group_id, timeout)
        elif file_type == "json":
            print(f"    → Создание из JSON...")
            with open(full_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)
            result = create_from_json(
                s, base, endpoint, json_data, name, group_id, timeout
            )

        if result:
            success += 1
            result_id = result.get("id")
            print(f"    ✓ Успешно импортирован (ID: {result_id})")
        else:
            failed_list.append(
                {"id": item_id, "name": name, "reason": "import_failed"}
            )

        time.sleep(CONFIG["SLEEP_BETWEEN"])

    # Сохраняем отчет об ошибках
    if failed_list:
        failed_file = os.path.join(import_dir, "import_failed.json")
        with open(failed_file, "w", encoding="utf-8") as f:
            json.dump(failed_list, f, ensure_ascii=False, indent=2)

    # Финальная статистика
    print("\n" + "=" * 60)
    print("СТАТИСТИКА ИМПОРТА")
    print("=" * 60)
    print(f"Тип импорта:          {import_type.upper()}")
    print(f"Всего записей:        {total}")
    print(f"Успешно импортировано: {success}")
    print(f"Пропущено (есть):     {skipped}")
    print(f"Ошибок:               {len(failed_list)}")
    if failed_list:
        print(f"\nОшибки сохранены:     {os.path.join(import_dir, 'import_failed.json')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
