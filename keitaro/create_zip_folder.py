
import os
import zipfile
from datetime import datetime

# где лежат лендинги (подпапки)
LANDER_ROOT = "lander"
# куда складывать zip-файлы
OUT_ROOT = f"lander_zips_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# файлы, которые пропускаем
SKIP_NAMES = {".DS_Store", "Thumbs.db"}


def main():
    if not os.path.isdir(LANDER_ROOT):
        print(f"❌ Папка '{LANDER_ROOT}' не найдена")
        return

    os.makedirs(OUT_ROOT, exist_ok=True)

    # все подпапки = отдельные лендинги
    landers = [
        d
        for d in os.listdir(LANDER_ROOT)
        if os.path.isdir(os.path.join(LANDER_ROOT, d))
    ]
    landers.sort()

    if not landers:
        print(f"❌ В '{LANDER_ROOT}' нет подпапок")
        return

    print(f"[INFO] Найдено лендингов: {len(landers)}")
    print(f"[INFO] ZIP-файлы будут в папке: {OUT_ROOT}\n")

    for idx, name in enumerate(landers, start=1):
        src_dir = os.path.join(LANDER_ROOT, name)
        zip_path = os.path.join(OUT_ROOT, f"{name}.zip")

        print(f"[{idx}/{len(landers)}] Пакую '{src_dir}' → '{zip_path}'")

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, files in os.walk(src_dir):
                for fn in files:
                    if fn in SKIP_NAMES:
                        continue
                    full = os.path.join(root, fn)
                    # путь внутри архива — относительно корня лендинга
                    rel = os.path.relpath(full, src_dir)
                    z.write(full, rel)

        print(f"    ✓ Готово ({name}.zip)\n")

    print("[DONE] Все лендинги упакованы.")
    print(f"Папка с архивами: {OUT_ROOT}")


if __name__ == "__main__":
    main()
