# StarCraft II GameStrings Translator & Automator

A simple tool for automatic translation of StarCraft II localization files (GameStrings.txt, ObjectStrings.txt, etc.) with tag protection, batch processing, and change detection.

---

[Русский (Russian)](#русский-инструкция) | [English (Current)](#starcraft-ii-gamestrings-translator--automator)

---

## Key Features
- **Tag Protection**: Automatically identifies and protects XML tags and variables (e.g., <c val="FF0000">, %Name%, [Button]) to prevent corruption during translation.
- **Change Detection**: The script compares your current file with the previous version (stored in last/) and only translates new or updated lines.
- **Full Mod Synchronization**: Sync your entire mod's localization (GameStrings, ObjectStrings, TriggerStrings, GameHotkeys) with a single command.
- **Auto-folder Creation**: Automatically creates necessary locale folders (e.g., ruRU.SC2Data) inside your mod.
- **Progress Tracking**: Status bar showing percentage, elapsed time, and the number of changed strings.

## Installation Guide

### 1. Install Python
1. Visit python.org/downloads/.
2. Click Download Python.
3. IMPORTANT: While installing, make sure to check "Add Python to PATH".
4. Click Install Now.

### 2. Install Libraries
1. Open the script folder (translate/).
2. Click on the address bar in File Explorer, type cmd, and press Enter.
3. In the command prompt, type:
   ```bash
   pip install -r requirements.txt
   ```
4. Wait for it to finish. You're ready!

## Usage Examples

### 1. Full Mod Sync (Recommended)
Sync your entire mod localization across all 11 non-English locales:
```bash
python translate/translate.py --mod "Path/To/Your/Mod.SC2Mod"
```

### 2. Sync Selected Locales
You can specify locales at the end or use the `--langs` flag:
```bash
python translate/translate.py --mod "Path/To/Your/Mod.SC2Mod" ruRU koKR
# OR
python translate/translate.py --mod "Path/To/Your/Mod.SC2Mod" --langs ruRU,koKR
```

### 3. Translate Specific File
```bash
python translate/translate.py -i "input.txt" -o "output_{lang}.txt" ruRU koKR
```

---

# Русский (Инструкция)

Простой инструмент для автоматического перевода файлов локализации StarCraft II (GameStrings.txt, ObjectStrings.txt и др.) с поддержкой защиты тегов, пакетной обработки и обнаружения изменений.

## Возможности
- **Защита тегов**: Автоматически находит и защищает XML-переменные (например, <c val="FF0000">, %Name%, [Button]), чтобы они не повредились при переводе.
- **Обнаружение изменений**: Скрипт сравнивает текущий файл с предыдущей версией (хранится в last/) и переводит только новые или измененные строки.
- **Полная синхронизация мода**: Одной командой обрабатывает все основные файлы локализации (GameStrings, ObjectStrings, TriggerStrings, GameHotkeys).
- **Автоматизация структуры**: Сам создает недостающие папки локализаций (например, ruRU.SC2Data) внутри вашего мода.

## Инструкция по установке

### 1. Установка Python
1. Перейдите на python.org/downloads/.
2. Нажмите Download Python.
3. ВАЖНО: При запуске установщика обязательно поставьте галочку "Add Python to PATH".
4. Нажмите Install Now.

### 2. Установка библиотек
1. Откройте папку со скриптом (translate/).
2. Нажмите на адресную строку вверху проводника, введите cmd и нажмите Enter.
3. В черном окне введите команду:
   ```bash
   pip install -r requirements.txt
   ```

## Примеры использования

### 1. Полная синхронизация мода (Рекомендуется)
```bash
python translate/translate.py --mod "Путь/К/Вашему/Моду.SC2Mod"
```

### 2. Синхронизация выборочных локализаций
Вы можете указать нужные языки в конце команды или через флаг `--langs`:
```bash
python translate/translate.py --mod "Путь/К/Вашему/Моду.SC2Mod" ruRU koKR
# ИЛИ
python translate/translate.py --mod "Путь/К/Вашему/Моду.SC2Mod" --langs ruRU,koKR
```

### 3. Перевод конкретного файла
```bash
python translate/translate.py -i "input.txt" -o "output_{lang}.txt" ruRU koKR
```

---

## Advanced Options / Дополнительные опции
- --mod (-m): Path to mod folder for full sync / Путь к папке мода.
- --langs: Selected languages (comma-separated: ruRU,koKR) / Выбранные языки через запятую.
- --list: List all supported locales / Список всех поддерживаемых локализаций.
- --last (-l): Path for comparison files (defaults to last/) / Путь к файлам сравнения.
- --copy-only: Only sync via copying (skip translation) / Синхронизация без перевода.
- --eta: Show estimated time in progress bar / Показывать оставшееся время.
- --translator: Force use a specific translator (libre, google, papago) / Принудительное использование конкретного переводчика (libre, google, papago).
- --force: Force translation of all strings, ignoring last file / Принудительный перевод всех строк, игнорируя последний файл.

## Config (config.json)
You can set `default_langs` in `config.json` to avoid typing them every time:
```json
{
    "default_langs": ["ruRU", "koKR"],
    "translators": { ... }
}
```

## Interface / Интерфейс
[ruRU] Progress: 1250/3022 (5) |███████████-------------| 41.4% | 01:15
- (5) — Strings to translate/copy / Количество новых или измененных строк.
- 01:15 — Elapsed time / Прошедшее время.

---

## Important / Важно
- Encoding / Кодировка: Files must be UTF-8 with BOM (standard for SC2). / Файлы должны быть в формате UTF-8 с BOM.
- Max Chars: Do not exceed max_chars: 4800 in config.json for Google Translate. / Рекомендуем не превышать max_chars: 4800 для Google API.


## test example

python translate.py -i input/gamestrings.txt -o output/gamestrings_ruRU_llama.txt ruRU --force --translator llama