#!/usr/bin/env python3
# -*- coding: utf-8 -*-






"""

Универсальный скрипт для скачивания лендингов или офферов из Keitaro.
Выберите что скачивать через переменную EXPORT_TYPE.

ВАЖНО СОЗДАТЬ ТАКОЙФАЙЛ 
# Keitaro API настройки ENV
KEITARO_TRACKER_URL=https://your-tracker-domain.com
KEITARO_API_KEY=your-api-k
"""

import os
import csv
import json
import time
import requests
from datetime import datetime
from urllib.parse import urlencode

# ======================== CONFIG ========================
CONFIG = {
    "BASE_URL": None,  # будет загружено из .env
    "API_KEY": None,   # будет загружено из .env

    # ========== ВЫБЕРИТЕ ЧТО СКАЧИВАТЬ ==========
    "EXPORT_TYPE": "offers",  # "offers" или "landings"
    # ============================================

    "PER_PAGE": 200,
    "TIMEOUT": 90,
    "OUT_DIR": None,  # по умолчанию {type}_exports_<timestamp>
    "GROUP_UNGROUPED": "__NO_GROUP__",
    "RETRY_DOWNLOADS": 2,
    "SLEEP_BETWEEN": 0.2,  # сек между запросами
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


def _safe(s: str | None, fallback="item") -> str:
    s = (s or "").strip()
    if not s:
        s = fallback
    return "".join(
        ch if ch.isalnum() or ch in (" ", "-", "_", ".", "+") else "_" for ch in s
    ).strip("._ ")[:150]


def _api(base: str, path: str, params: dict | None = None) -> str:
    base = base.rstrip("/")
    path = path.lstrip("/")
    url = f"{base}/admin_api/v1/{path}"
    if params:
        url += "?" + urlencode(params)
    return url


def detect_landings_endpoint(
    s: requests.Session, base: str, per_page: int, timeout: int
) -> str:
    """Определяет правильный эндпоинт для лендингов: landing_pages или landings"""
    for ep in ("landing_pages", "landings"):
        url = _api(base, ep, {"per_page": 1, "page": 1})
        try:
            r = s.get(url, timeout=timeout)
            if r.status_code == 200:
                return ep
        except requests.RequestException:
            pass
    raise RuntimeError(
        "Не удалось определить эндпоинт лендингов (landing_pages/landings)."
    )


def iter_items(
    s: requests.Session, base: str, endpoint: str, per_page: int, timeout: int
):
    """Итерация по всем элементам с пагинацией"""
    page = 1
    while True:
        url = _api(base, endpoint, {"per_page": per_page, "page": page})
        r = s.get(url, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        items = data.get("data") if isinstance(data, dict) else data
        if not items:
            break
        for it in items:
            yield it
        total_pages = None
        if isinstance(data, dict):
            meta = data.get("meta") or {}
            pagination = meta.get("pagination") or {}
            total_pages = pagination.get("total_pages")
        if not total_pages or page >= int(total_pages):
            break
        page += 1


def as_group_name(group_field, default_name: str) -> str:
    """Извлечь название группы из поля"""
    if isinstance(group_field, str):
        name = group_field
    elif isinstance(group_field, dict):
        name = group_field.get("name") or group_field.get("title") or ""
    else:
        name = ""
    return _safe(name or default_name, fallback=default_name)


def try_direct_url(
    s: requests.Session, url: str, timeout: int
) -> requests.Response | None:
    """Попытка скачать напрямую по URL"""
    if not url:
        return None
    try:
        r = s.get(url, timeout=timeout, stream=True)
        if r.status_code == 200 and (
            "application/zip" in r.headers.get("Content-Type", "").lower()
            or r.headers.get("Content-Disposition", "").lower().find(".zip") != -1
        ):
            return r
    except requests.RequestException:
        pass
    return None


def try_download_endpoints(
    s: requests.Session, base: str, endpoint: str, item_id, timeout: int
) -> requests.Response | None:
    """Пробуем несколько вариантов эндпоинтов для скачивания"""
    candidates = [
        _api(base, f"{endpoint}/{item_id}/export"),
        _api(base, f"{endpoint}/{item_id}/download"),
        _api(base, f"{endpoint}/{item_id}/archive"),
        # без admin_api (редко, но бывает)
        f"{base.rstrip('/')}/{endpoint}/{item_id}/export",
        f"{base.rstrip('/')}/{endpoint}/{item_id}/download",
        f"{base.rstrip('/')}/{endpoint}/{item_id}/archive",
    ]

    for url in candidates:
        try:
            r = s.get(url, timeout=timeout, stream=True)
            if r.status_code == 200 and (
                "application/zip" in r.headers.get("Content-Type", "").lower()
                or "attachment" in r.headers.get("Content-Disposition", "").lower()
                or len(r.content) > 100
            ):
                return r
        except requests.RequestException:
            pass
    return None


def get_item_details(
    s: requests.Session, base: str, endpoint: str, item_id, timeout: int
) -> dict | None:
    """Получить детальную информацию об элементе"""
    try:
        url = _api(base, f"{endpoint}/{item_id}")
        r = s.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None


def save_stream(resp: requests.Response, dst_path: str) -> None:
    """Сохранить поток в файл"""
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    with open(dst_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 128):
            if chunk:
                f.write(chunk)


def save_as_json(data: dict, dst_path: str) -> None:
    """Сохранить данные как JSON (запасной вариант)"""
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    with open(dst_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    load_config_from_env()

    base = CONFIG["BASE_URL"]
    api_key = CONFIG["API_KEY"]
    export_type = CONFIG["EXPORT_TYPE"].lower()

    if not base or not api_key:
        print("❌ ОШИБКА: Не указаны KEITARO_TRACKER_URL или KEITARO_API_KEY в .env")
        return

    if export_type not in ("offers", "landings"):
        print(f"❌ ОШИБКА: EXPORT_TYPE должен быть 'offers' или 'landings', а не '{export_type}'")
        return

    per_page = CONFIG["PER_PAGE"]
    timeout = CONFIG["TIMEOUT"]
    ungrouped = CONFIG["GROUP_UNGROUPED"]

    # Определяем эндпоинт
    if export_type == "landings":
        s_temp = _session(api_key)
        endpoint = detect_landings_endpoint(s_temp, base, per_page, timeout)
        item_type_ru = "лендинг"
        item_type_ru_plural = "лендингов"
    else:
        endpoint = "offers"
        item_type_ru = "оффер"
        item_type_ru_plural = "офферов"

    out_root = (
        CONFIG["OUT_DIR"]
        or f"{export_type}_exports_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(out_root, exist_ok=True)

    s = _session(api_key)
    print(f"[INFO] Режим: {export_type.upper()}")
    print(f"[INFO] Эндпоинт: {endpoint}")
    print(f"[INFO] Подключение к: {base}")
    print(f"[INFO] Папка экспорта: {out_root}")

    index_rows: list[dict] = []
    failed: list[dict] = []
    total = 0
    ok = 0
    saved_as_json = 0

    for item in iter_items(s, base, endpoint, per_page, timeout):
        total += 1
        item_id = item.get("id")
        name = _safe(item.get("name") or f"{export_type}_{item_id}")

        # Группа может быть в разных полях
        group = as_group_name(
            item.get("group_name") or item.get("group"),
            ungrouped
        )

        dst_dir = os.path.join(out_root, group)
        dst_zip = os.path.join(dst_dir, f"{item_id}_{name}.zip")
        dst_json = os.path.join(dst_dir, f"{item_id}_{name}.json")
        os.makedirs(dst_dir, exist_ok=True)

        print(f"\n[{total}] {item_type_ru.capitalize()}: {name} (ID: {item_id}, Группа: {group})")

        # 1) Прямые URL в объекте (если есть)
        direct_urls = [
            (item.get("archive_url") or ""),
            (item.get("export_url") or ""),
            (item.get("download_url") or ""),
            (item.get("zip_url") or ""),
        ]
        resp = None
        for u in direct_urls:
            resp = try_direct_url(s, u, timeout)
            if resp:
                print(f"    ✓ Найден прямой URL")
                break

        # 2) Стандартные REST-пути
        if not resp:
            resp = try_download_endpoints(s, base, endpoint, item_id, timeout)
            if resp:
                print(f"    ✓ Скачано через эндпоинт")

        # 3) Если ничего не помогло - сохраняем детали как JSON
        if not resp:
            print(f"    ⚠ ZIP недоступен, пробую получить детали...")
            details = get_item_details(s, base, endpoint, item_id, timeout)
            if details:
                try:
                    save_as_json(details, dst_json)
                    saved_as_json += 1
                    ok += 1
                    print(f"    ✓ Сохранен как JSON → {dst_json}")
                    index_rows.append(
                        {
                            "id": item_id,
                            "name": name,
                            "group": group,
                            "file_path": os.path.relpath(dst_json, out_root),
                            "type": "json",
                            "source": "details_api",
                        }
                    )
                except OSError as e:
                    failed.append(
                        {
                            "id": item_id,
                            "name": name,
                            "group": group,
                            "reason": f"write_error: {e}",
                        }
                    )
                    print(f"    ✗ Ошибка записи: {e}")
            else:
                failed.append(
                    {
                        "id": item_id,
                        "name": name,
                        "group": group,
                        "reason": "no_data_available",
                    }
                )
                print(f"    ✗ Не удалось получить данные")
        else:
            # Скачивание ZIP
            try:
                save_stream(resp, dst_zip)
                ok += 1
                print(f"    ✓ Сохранен ZIP → {dst_zip}")
                index_rows.append(
                    {
                        "id": item_id,
                        "name": name,
                        "group": group,
                        "file_path": os.path.relpath(dst_zip, out_root),
                        "type": "zip",
                        "source": "archive_endpoint",
                    }
                )
            except OSError as e:
                failed.append(
                    {
                        "id": item_id,
                        "name": name,
                        "group": group,
                        "reason": f"write_error: {e}",
                    }
                )
                print(f"    ✗ Ошибка записи: {e}")

        time.sleep(CONFIG["SLEEP_BETWEEN"])

    # Сохраняем index.csv
    index_file = os.path.join(out_root, "index.csv")
    with open(index_file, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["id", "name", "group", "file_path", "type", "source"]
        )
        w.writeheader()
        for row in index_rows:
            w.writerow(row)

    # Сохраняем failed.json если есть ошибки
    if failed:
        failed_file = os.path.join(out_root, "failed.json")
        with open(failed_file, "w", encoding="utf-8") as f:
            json.dump(failed, f, ensure_ascii=False, indent=2)

    # Финальная статистика
    print("\n" + "=" * 60)
    print("СТАТИСТИКА ЭКСПОРТА")
    print("=" * 60)
    print(f"Тип экспорта:         {export_type.upper()}")
    print(f"Всего {item_type_ru_plural}:        {total}")
    print(f"Успешно скачано:      {ok}")
    print(f"  - как ZIP:          {ok - saved_as_json}")
    print(f"  - как JSON:         {saved_as_json}")
    print(f"Не удалось скачать:   {len(failed)}")
    print(f"\nРезультаты в папке:   {out_root}")
    print(f"Индекс:               {index_file}")
    if failed:
        print(f"Ошибки:               {os.path.join(out_root, 'failed.json')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
