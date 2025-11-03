#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Экспорт всех кампаний из Keitaro со всеми настройками, потоками и постбэками.
Сохраняет полную структуру для последующего импорта.
"""

import os
import json
import time
import requests
from datetime import datetime
from urllib.parse import urlencode

# ======================== CONFIG ========================
CONFIG = {
    "BASE_URL": None,  # будет загружено из .env
    "API_KEY": None,   # будет загружено из .env
    "PER_PAGE": 200,
    "TIMEOUT": 90,
    "OUT_DIR": None,  # по умолчанию campaigns_export_<timestamp>
    "SLEEP_BETWEEN": 0.2,
}
# ====================== /CONFIG ========================


def load_config_from_env():
    """Загрузить настройки из .env файла"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        CONFIG["BASE_URL"] = os.getenv("KEITARO_TRACKER_URL")
        CONFIG["API_KEY"] = os.getenv("KEITARO_API_KEY")
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


def _api(base: str, path: str, params: dict | None = None) -> str:
    base = base.rstrip("/")
    path = path.lstrip("/")
    url = f"{base}/admin_api/v1/{path}"
    if params:
        url += "?" + urlencode(params)
    return url


def iter_campaigns(
    s: requests.Session, base: str, per_page: int, timeout: int
):
    """Итерация по всем кампаниям с пагинацией"""
    page = 1
    while True:
        url = _api(base, "campaigns", {"per_page": per_page, "page": page})
        r = s.get(url, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            break
        for it in items:
            yield it

        # Проверка пагинации
        if isinstance(data, dict):
            meta = data.get("meta", {})
            pagination = meta.get("pagination", {})
            total_pages = pagination.get("total_pages")
            if not total_pages or page >= int(total_pages):
                break
        page += 1


def get_campaign_details(
    s: requests.Session, base: str, campaign_id: int, timeout: int
) -> dict | None:
    """Получить детальную информацию о кампании"""
    try:
        url = _api(base, f"campaigns/{campaign_id}")
        r = s.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        print(f"    ✗ Ошибка получения деталей: {e}")
        return None


def get_campaign_flows(
    s: requests.Session, base: str, campaign_id: int, timeout: int
) -> list:
    """Получить потоки кампании"""
    try:
        url = _api(base, f"campaigns/{campaign_id}/flows")
        r = s.get(url, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else data.get("data", [])
    except requests.RequestException:
        return []


def get_all_offers(s: requests.Session, base: str, timeout: int) -> dict:
    """Получить все офферы для маппинга. Возвращает {id: name}"""
    offers = {}
    try:
        page = 1
        while True:
            url = _api(base, "offers", {"per_page": 200, "page": page})
            r = s.get(url, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            items = data.get("data") if isinstance(data, dict) else data
            if not items:
                break
            for offer in items:
                offers[offer.get("id")] = offer.get("name")

            if isinstance(data, dict):
                meta = data.get("meta", {})
                pagination = meta.get("pagination", {})
                total_pages = pagination.get("total_pages")
                if not total_pages or page >= int(total_pages):
                    break
            page += 1
    except requests.RequestException:
        pass
    return offers


def get_all_landings(s: requests.Session, base: str, timeout: int) -> dict:
    """Получить все лендинги для маппинга. Возвращает {id: name}"""
    landings = {}

    # Пробуем оба эндпоинта
    for endpoint in ("landing_pages", "landings"):
        try:
            page = 1
            while True:
                url = _api(base, endpoint, {"per_page": 200, "page": page})
                r = s.get(url, timeout=timeout)
                if r.status_code != 200:
                    break
                data = r.json()
                items = data.get("data") if isinstance(data, dict) else data
                if not items:
                    break
                for landing in items:
                    landings[landing.get("id")] = landing.get("name")

                if isinstance(data, dict):
                    meta = data.get("meta", {})
                    pagination = meta.get("pagination", {})
                    total_pages = pagination.get("total_pages")
                    if not total_pages or page >= int(total_pages):
                        break
                page += 1

            if landings:
                break
        except requests.RequestException:
            continue

    return landings


def get_all_groups(s: requests.Session, base: str, timeout: int) -> dict:
    """Получить все группы. Возвращает {id: name}"""
    groups = {}
    try:
        url = _api(base, "groups", {"per_page": 500})
        r = s.get(url, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        items = data.get("data") if isinstance(data, dict) else data
        if items:
            for g in items:
                groups[g.get("id")] = g.get("name")
    except requests.RequestException:
        pass
    return groups


def get_all_domains(s: requests.Session, base: str, timeout: int) -> dict:
    """Получить все домены. Возвращает {id: name}"""
    domains = {}
    try:
        url = _api(base, "domains", {"per_page": 500})
        r = s.get(url, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        items = data.get("data") if isinstance(data, dict) else data
        if items:
            for d in items:
                domains[d.get("id")] = d.get("name")
    except requests.RequestException:
        pass
    return domains


def main():
    load_config_from_env()

    base = CONFIG["BASE_URL"]
    api_key = CONFIG["API_KEY"]

    if not base or not api_key:
        print("❌ ОШИБКА: Не указаны KEITARO_TRACKER_URL или KEITARO_API_KEY в .env")
        return

    timeout = CONFIG["TIMEOUT"]
    out_root = (
        CONFIG["OUT_DIR"]
        or f"campaigns_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(out_root, exist_ok=True)

    s = _session(api_key)
    print(f"[INFO] Подключение к: {base}")
    print(f"[INFO] Папка экспорта: {out_root}")
    print()

    # Получаем маппинги для читаемости
    print("[1/6] Получение офферов...")
    offers_map = get_all_offers(s, base, timeout)
    print(f"    Найдено офферов: {len(offers_map)}")

    print("[2/6] Получение лендингов...")
    landings_map = get_all_landings(s, base, timeout)
    print(f"    Найдено лендингов: {len(landings_map)}")

    print("[3/6] Получение групп...")
    groups_map = get_all_groups(s, base, timeout)
    print(f"    Найдено групп: {len(groups_map)}")

    print("[4/6] Получение доменов...")
    domains_map = get_all_domains(s, base, timeout)
    print(f"    Найдено доменов: {len(domains_map)}")

    # Сохраняем маппинги
    mappings = {
        "offers": offers_map,
        "landings": landings_map,
        "groups": groups_map,
        "domains": domains_map,
    }
    mappings_file = os.path.join(out_root, "_mappings.json")
    with open(mappings_file, "w", encoding="utf-8") as f:
        json.dump(mappings, f, ensure_ascii=False, indent=2)
    print(f"[5/6] Маппинги сохранены: {mappings_file}")

    print("[6/6] Экспорт кампаний...")
    print()

    campaigns_data = []
    total = 0
    success = 0

    for campaign in iter_campaigns(s, base, CONFIG["PER_PAGE"], timeout):
        total += 1
        campaign_id = campaign.get("id")
        name = campaign.get("name", f"campaign_{campaign_id}")

        print(f"[{total}] Кампания: {name} (ID: {campaign_id})")

        # Получаем полные детали
        details = get_campaign_details(s, base, campaign_id, timeout)
        if not details:
            print(f"    ✗ Не удалось получить детали")
            continue

        # Получаем потоки
        flows = get_campaign_flows(s, base, campaign_id, timeout)
        details["flows"] = flows

        # Добавляем читаемые имена для удобства
        if details.get("group_id"):
            details["_group_name"] = groups_map.get(details["group_id"], "")
        if details.get("domain_id"):
            details["_domain_name"] = domains_map.get(details["domain_id"], "")

        # Добавляем читаемые имена в потоки
        for flow in flows:
            if flow.get("offer_id"):
                flow["_offer_name"] = offers_map.get(flow["offer_id"], "")
            if flow.get("landing_id"):
                flow["_landing_name"] = landings_map.get(flow["landing_id"], "")

        campaigns_data.append(details)
        success += 1
        print(f"    ✓ Экспортирована с {len(flows)} потоками")

        time.sleep(CONFIG["SLEEP_BETWEEN"])

    # Сохраняем все кампании
    campaigns_file = os.path.join(out_root, "campaigns.json")
    with open(campaigns_file, "w", encoding="utf-8") as f:
        json.dump(campaigns_data, f, ensure_ascii=False, indent=2)

    # Сохраняем индекс
    index_data = []
    for c in campaigns_data:
        index_data.append({
            "id": c.get("id"),
            "name": c.get("name"),
            "alias": c.get("alias"),
            "group": c.get("_group_name", ""),
            "type": c.get("type"),
            "state": c.get("state"),
            "flows_count": len(c.get("flows", [])),
            "postbacks_count": len(c.get("postbacks", [])),
        })

    index_file = os.path.join(out_root, "campaigns_index.json")
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    # Финальная статистика
    print("\n" + "=" * 60)
    print("СТАТИСТИКА ЭКСПОРТА КАМПАНИЙ")
    print("=" * 60)
    print(f"Всего кампаний:       {total}")
    print(f"Успешно экспортировано: {success}")
    print(f"\nРезультаты в папке:   {out_root}")
    print(f"Кампании:             {campaigns_file}")
    print(f"Индекс:               {index_file}")
    print(f"Маппинги:             {mappings_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
