#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Импорт кампаний в Keitaro из экспорта.
Автоматически сопоставляет офферы, лендинги, группы и домены по именам.
Создает недостающие группы, воссоздает потоки и постбэки.
"""

import os
import json
import time
import requests
from typing import Dict, List, Optional

# ======================== CONFIG ========================
CONFIG = {
    "BASE_URL": None,  # будет загружено из .env
    "API_KEY": None,   # будет загружено из .env
    "IMPORT_DIR": None,  # путь к папке с экспортом
    "TIMEOUT": 90,
    "SLEEP_BETWEEN": 0.3,
    "CREATE_GROUPS": True,
    "SKIP_EXISTING": True,  # пропускать если есть с таким именем
    "MATCH_BY_NAME": True,  # сопоставлять офферы/лендинги по именам
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
            "Content-Type": "application/json",
        }
    )
    return s


def _api(base: str, path: str) -> str:
    base = base.rstrip("/")
    path = path.lstrip("/")
    return f"{base}/admin_api/v1/{path}"


def get_all_items(s: requests.Session, base: str, endpoint: str, timeout: int) -> Dict[str, int]:
    """Получить все элементы. Возвращает {name: id}"""
    items = {}
    page = 1
    per_page = 200

    while True:
        try:
            url = _api(base, f"{endpoint}?per_page={per_page}&page={page}")
            r = s.get(url, timeout=timeout)
            if r.status_code != 200:
                break
            data = r.json()
            entries = data.get("data") if isinstance(data, dict) else data
            if not entries:
                break

            for item in entries:
                name = item.get("name", "")
                if name:
                    items[name] = item.get("id")

            # Пагинация
            if isinstance(data, dict):
                meta = data.get("meta", {})
                pagination = meta.get("pagination", {})
                total_pages = pagination.get("total_pages")
                if not total_pages or page >= int(total_pages):
                    break
            page += 1
        except requests.RequestException:
            break

    return items


def detect_landings_endpoint(s: requests.Session, base: str, timeout: int) -> str:
    """Определяет правильный эндпоинт для лендингов"""
    for ep in ("landing_pages", "landings"):
        try:
            url = _api(base, f"{ep}?per_page=1")
            r = s.get(url, timeout=timeout)
            if r.status_code == 200:
                return ep
        except requests.RequestException:
            pass
    return "landings"


def create_group(s: requests.Session, base: str, name: str, timeout: int) -> Optional[int]:
    """Создать группу"""
    try:
        url = _api(base, "groups")
        r = s.post(url, json={"name": name}, timeout=timeout)
        r.raise_for_status()
        return r.json().get("id")
    except requests.RequestException:
        return None


def create_campaign(
    s: requests.Session,
    base: str,
    campaign_data: dict,
    group_id: Optional[int],
    domain_id: Optional[int],
    timeout: int,
) -> Optional[dict]:
    """Создать кампанию"""
    try:
        url = _api(base, "campaigns")

        # Основные поля для создания
        payload = {
            "name": campaign_data.get("name"),
            "type": campaign_data.get("type", "default"),
            "state": campaign_data.get("state", "active"),
        }

        # Опциональные поля
        optional_fields = [
            "uniqueness_method",
            "cookies_ttl",
            "cost_type",
            "cost_value",
            "cost_currency",
            "cost_auto",
            "notes",
            "parameters",
            "bind_visitors",
            "traffic_source_id",
            "uniqueness_use_cookies",
            "traffic_loss",
            "bypass_cache",
        ]

        for field in optional_fields:
            if field in campaign_data and campaign_data[field] is not None:
                payload[field] = campaign_data[field]

        # ID маппинги
        if group_id:
            payload["group_id"] = group_id
        if domain_id:
            payload["domain_id"] = domain_id

        r = s.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        print(f"    ✗ Ошибка создания кампании: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"    Response: {e.response.text}")
        return None


def create_flow(
    s: requests.Session,
    base: str,
    campaign_id: int,
    flow_data: dict,
    offer_id: Optional[int],
    landing_id: Optional[int],
    timeout: int,
) -> Optional[dict]:
    """Создать поток в кампании"""
    try:
        url = _api(base, f"campaigns/{campaign_id}/flows")

        payload = {
            "type": flow_data.get("type", "regular"),
            "weight": flow_data.get("weight", 100),
        }

        # Опциональные поля
        optional_fields = [
            "name",
            "position",
            "state",
            "schema",
            "action_options",
            "filter_or",
            "filters",
        ]

        for field in optional_fields:
            if field in flow_data and flow_data[field] is not None:
                payload[field] = flow_data[field]

        # ID маппинги
        if offer_id:
            payload["offer_id"] = offer_id
        if landing_id:
            payload["landing_id"] = landing_id

        r = s.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        print(f"      ✗ Ошибка создания потока: {e}")
        return None


def create_postback(
    s: requests.Session,
    base: str,
    campaign_id: int,
    postback_data: dict,
    timeout: int,
) -> Optional[dict]:
    """Создать постбэк для кампании"""
    try:
        url = _api(base, f"campaigns/{campaign_id}/postbacks")

        payload = {
            "url": postback_data.get("url"),
            "method": postback_data.get("method", "GET"),
        }

        if "statuses" in postback_data:
            payload["statuses"] = postback_data["statuses"]

        r = s.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        print(f"      ✗ Ошибка создания постбэка: {e}")
        return None


def main():
    load_config_from_env()

    base = CONFIG["BASE_URL"]
    api_key = CONFIG["API_KEY"]
    import_dir = CONFIG["IMPORT_DIR"]

    if not base or not api_key:
        print("❌ ОШИБКА: Не указаны KEITARO_TARGET_URL и KEITARO_TARGET_API_KEY")
        return

    if not import_dir:
        print("❌ ОШИБКА: Укажите IMPORT_DIR - путь к папке с экспортом")
        return

    if not os.path.isdir(import_dir):
        print(f"❌ ОШИБКА: Папка '{import_dir}' не найдена")
        return

    # Проверяем файлы
    campaigns_file = os.path.join(import_dir, "campaigns.json")
    mappings_file = os.path.join(import_dir, "_mappings.json")

    if not os.path.isfile(campaigns_file):
        print(f"❌ ОШИБКА: Файл '{campaigns_file}' не найден")
        return

    timeout = CONFIG["TIMEOUT"]
    s = _session(api_key)

    print(f"[INFO] Целевой трекер: {base}")
    print(f"[INFO] Папка импорта: {import_dir}")
    print()

    # Загружаем экспортированные данные
    print("[1/7] Загрузка экспортированных кампаний...")
    with open(campaigns_file, "r", encoding="utf-8") as f:
        campaigns_data = json.load(f)
    print(f"    Найдено кампаний: {len(campaigns_data)}")

    # Загружаем маппинги (если есть)
    source_mappings = {}
    if os.path.isfile(mappings_file):
        with open(mappings_file, "r", encoding="utf-8") as f:
            source_mappings = json.load(f)

    # Получаем текущие данные целевого трекера
    print("[2/7] Получение групп...")
    groups_map = get_all_items(s, base, "groups", timeout)
    print(f"    Найдено групп: {len(groups_map)}")

    print("[3/7] Получение доменов...")
    domains_map = get_all_items(s, base, "domains", timeout)
    print(f"    Найдено доменов: {len(domains_map)}")

    print("[4/7] Получение офферов...")
    offers_map = get_all_items(s, base, "offers", timeout)
    print(f"    Найдено офферов: {len(offers_map)}")

    print("[5/7] Получение лендингов...")
    landings_endpoint = detect_landings_endpoint(s, base, timeout)
    landings_map = get_all_items(s, base, landings_endpoint, timeout)
    print(f"    Найдено лендингов: {len(landings_map)}")

    # Получаем существующие кампании
    if CONFIG["SKIP_EXISTING"]:
        print("[6/7] Получение существующих кампаний...")
        existing_campaigns = get_all_items(s, base, "campaigns", timeout)
        print(f"    Найдено существующих: {len(existing_campaigns)}")
    else:
        existing_campaigns = {}
        print("[6/7] Пропуск проверки существующих (SKIP_EXISTING=False)")

    # Импорт
    print("[7/7] Начинаем импорт кампаний...")
    print()

    total = 0
    success = 0
    skipped = 0
    failed_list = []

    for campaign in campaigns_data:
        total += 1
        name = campaign.get("name", f"campaign_{total}")

        print(f"[{total}/{len(campaigns_data)}] Кампания: {name}")

        # Пропускаем если уже есть
        if CONFIG["SKIP_EXISTING"] and name in existing_campaigns:
            print(f"    ⊘ Пропущена (уже существует)")
            skipped += 1
            time.sleep(CONFIG["SLEEP_BETWEEN"])
            continue

        # Маппинг группы
        group_id = None
        group_name = campaign.get("_group_name", "")
        if group_name:
            if group_name in groups_map:
                group_id = groups_map[group_name]
            elif CONFIG["CREATE_GROUPS"]:
                group_id = create_group(s, base, group_name, timeout)
                if group_id:
                    groups_map[group_name] = group_id
                    print(f"    ✓ Создана группа: {group_name}")

        # Маппинг домена (по имени)
        domain_id = None
        domain_name = campaign.get("_domain_name", "")
        if domain_name and domain_name in domains_map:
            domain_id = domains_map[domain_name]

        # Создаем кампанию
        print(f"    → Создание кампании...")
        new_campaign = create_campaign(s, base, campaign, group_id, domain_id, timeout)

        if not new_campaign:
            failed_list.append({"name": name, "reason": "creation_failed"})
            continue

        new_campaign_id = new_campaign.get("id")
        print(f"    ✓ Создана кампания (ID: {new_campaign_id})")

        # Создаем потоки
        flows = campaign.get("flows", [])
        if flows:
            print(f"    → Создание {len(flows)} потоков...")
            flows_created = 0

            for flow in flows:
                # Маппинг оффера
                offer_id = None
                offer_name = flow.get("_offer_name", "")
                if offer_name and offer_name in offers_map:
                    offer_id = offers_map[offer_name]

                # Маппинг лендинга
                landing_id = None
                landing_name = flow.get("_landing_name", "")
                if landing_name and landing_name in landings_map:
                    landing_id = landings_map[landing_name]

                if create_flow(s, base, new_campaign_id, flow, offer_id, landing_id, timeout):
                    flows_created += 1

            print(f"    ✓ Создано потоков: {flows_created}/{len(flows)}")

        # Создаем постбэки
        postbacks = campaign.get("postbacks", [])
        if postbacks:
            print(f"    → Создание {len(postbacks)} постбэков...")
            postbacks_created = 0

            for postback in postbacks:
                if create_postback(s, base, new_campaign_id, postback, timeout):
                    postbacks_created += 1

            print(f"    ✓ Создано постбэков: {postbacks_created}/{len(postbacks)}")

        success += 1
        time.sleep(CONFIG["SLEEP_BETWEEN"])

    # Сохраняем отчет об ошибках
    if failed_list:
        failed_file = os.path.join(import_dir, "campaigns_import_failed.json")
        with open(failed_file, "w", encoding="utf-8") as f:
            json.dump(failed_list, f, ensure_ascii=False, indent=2)

    # Финальная статистика
    print("\n" + "=" * 60)
    print("СТАТИСТИКА ИМПОРТА КАМПАНИЙ")
    print("=" * 60)
    print(f"Всего кампаний:        {total}")
    print(f"Успешно импортировано: {success}")
    print(f"Пропущено (есть):      {skipped}")
    print(f"Ошибок:                {len(failed_list)}")
    if failed_list:
        print(f"\nОшибки сохранены:      {os.path.join(import_dir, 'campaigns_import_failed.json')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
