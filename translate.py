import re
import os
import time
import sys
import json
import requests
import argparse
import shutil
import subprocess
from deep_translator import GoogleTranslator

# ======================
# PATHS & CONFIG
# ======================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(SCRIPT_DIR, "input", "GameStrings.txt")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

# Will be set dynamically based on SC2_LOCALES
DEFAULT_LANGS = []
ENCODING = "utf-8-sig"

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# Load config at start
CONFIG = load_config()

# SC2 Locales mapping to Translator API codes
SC2_LOCALES = {
    "deDE": "de",
    "enUS": "en",
    "esES": "es",
    "esMX": "es",
    "frFR": "fr",
    "itIT": "it",
    "koKR": "ko",
    "plPL": "pl",
    "ptBR": "pt",
    "ruRU": "ru",
    "zhCN": "zh-CN",
    "zhTW": "zh-TW"
}

# All supported SC2 locales
ALL_LOCALES = sorted([l for l in SC2_LOCALES.keys() if l != "enUS"])

# Default languages (from config or all)
DEFAULT_LANGS = CONFIG.get("default_langs", ALL_LOCALES)

# ======================
# TRANSLATORS
# ======================

def translate_libre(text, lang):
    libre_cfg = CONFIG.get("translators", {}).get("libre", {})
    if not libre_cfg.get("enabled", False):
        return None
    url = libre_cfg.get("url", "http://localhost:5000/translate")
    payload = {
        "q": text,
        "source": "en",
        "target": lang,
        "format": "text"
    }
    # API key (если включен на сервере)
    api_key = libre_cfg.get("api_key")
    if api_key:
        payload["api_key"] = api_key
    try:
        res = requests.post(url, json=payload, timeout=60)
        if res.status_code == 200:
            return res.json().get("translatedText")
        else:
            print("LibreTranslate error:", res.text)
    except Exception as e:
        print("LibreTranslate exception:", e)
    return None

def translate_google(text, lang):
    return GoogleTranslator(source='en', target=lang).translate(text)


def translate_papago(text, lang):
    papago_cfg = CONFIG.get("translators", {}).get("papago", {})

    if not papago_cfg.get("enabled"):
        return None

    client_id = papago_cfg.get("client_id")
    client_secret = papago_cfg.get("client_secret")

    if not client_id or not client_secret:
        return None

    url = "https://openapi.naver.com/v1/papago/n2mt"

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }

    data = {
        "source": "en",
        "target": lang,
        "text": text
    }

    res = requests.post(url, headers=headers, data=data)

    if res.status_code == 200:
        return res.json()["message"]["result"]["translatedText"]

    print("Papago error:", res.text)
    return None


def translate_llama(text, lang):
    """Translate using local Ollama Llama model."""
    llama_cfg = CONFIG.get("translators", {}).get("llama", {})

    if not llama_cfg.get("enabled", False):
        return None

    ollama_path = llama_cfg.get("ollama_path", r"C:\Users\Admin\AppData\Local\Programs\Ollama\ollama.exe")
    model = llama_cfg.get("model", "llama3")
    api_url = llama_cfg.get("api_url", "http://localhost:11434/api/generate")

    # Map lang codes to full names for better translation
    lang_names = {
        "de": "German",
        "es": "Spanish",
        "fr": "French",
        "it": "Italian",
        "ko": "Korean",
        "pl": "Polish",
        "pt": "Portuguese",
        "ru": "Russian",
        "zh-CN": "Chinese (Simplified)",
        "zh-TW": "Chinese (Traditional)"
    }
    target_lang = lang_names.get(lang, lang)


    # Load context from external file
    context_file = llama_cfg.get("context_file", "llama_context.txt")
    context_path = os.path.join(SCRIPT_DIR, context_file)
    
    if os.path.exists(context_path):
        with open(context_path, "r", encoding="utf-8") as f:
            context_template = f.read()
            # Use string replacement to avoid issues with curly braces in context
            sc2_context = context_template.replace("{target_lang}", target_lang)
    else:
        # Fallback minimal context if file not found
        sc2_context = f"Translate the following English text to {target_lang}. Only output the translation, nothing else:\n"

    # Prompt for translation
    prompt = f"{sc2_context}\n{text}"

    try:
        # Try using Ollama API first
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3
            }
        }
        res = requests.post(api_url, json=payload, timeout=300)
        if res.status_code == 200:
            result = res.json()
            return result.get("response", "").strip()
        else:
            print(f"Ollama API error: {res.status_code} - {res.text}")
    except requests.exceptions.ConnectionError:
        # Fallback to CLI if API not available
        try:
            cmd = [ollama_path, "run", model, prompt]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                encoding="utf-8",
                errors="replace"
            )
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                print(f"Ollama CLI error: {result.stderr}")
        except Exception as e:
            print(f"Ollama exception: {e}")
    except Exception as e:
        print(f"Llama translation error: {e}")

    return None


def parse_sections(lines):
    """Parse file into sections by ### HEADER ### pattern."""
    sections = {}
    current_section = "HEADERLESS"
    
    for line in lines:
        stripped = line.strip()
        # Check for section header pattern
        if stripped.startswith("###") and stripped.endswith("###"):
            current_section = stripped.strip("# ").strip()
            if current_section not in sections:
                sections[current_section] = []
        else:
            if current_section not in sections:
                sections[current_section] = []
            sections[current_section].append(line)
    
    return sections


# Global glossary for consistent translations
TRANSLATION_GLOSSARY = {}


def load_external_glossary(dest_lang):
    """Load glossary from external glossary.txt file."""
    global TRANSLATION_GLOSSARY
    
    glossary_path = os.path.join(SCRIPT_DIR, "glossary.txt")
    if not os.path.exists(glossary_path):
        return False
    
    # Language to column index mapping in glossary.txt
    # Format: en;ru;de;es;es;fr;it;ko;pl;pt;zh-CN;zh-TW
    lang_to_col = {
        "de": 2,
        "es": 3,
        "fr": 5,
        "it": 6,
        "ko": 7,
        "pl": 8,
        "pt": 9,
        "ru": 1,
        "zh-CN": 10,
        "zh-TW": 11
    }
    
    col_index = lang_to_col.get(dest_lang)
    if col_index is None:
        return False
    
    try:
        with open(glossary_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split(";")
                
                english_term = parts[0].strip()
                if not english_term:
                    continue
                
                # Single word without translation - keep as is (don't translate)
                if len(parts) == 1:
                    TRANSLATION_GLOSSARY[english_term] = english_term
                    continue
        
                # Check if we have a translation for target language
                if len(parts) > col_index:
                    translated_term = parts[col_index].strip()
                    
                    # If translation is empty or equals the english term (marked as "keep as is")
                    # then use the english term (don't translate)
                    if not translated_term or translated_term == english_term:
                        # Mark as "keep original" - will be used in apply_glossary
                        TRANSLATION_GLOSSARY[english_term] = english_term
                    else:
                        TRANSLATION_GLOSSARY[english_term] = translated_term
                else:
                    # No translation column - keep as is
                    TRANSLATION_GLOSSARY[english_term] = english_term
        
        if TRANSLATION_GLOSSARY:
            print(f"[Glossary] Loaded {len(TRANSLATION_GLOSSARY)} terms from glossary.txt")
            return True
    except Exception as e:
        print(f"[Glossary] Error loading file: {e}")
    
    return False


def build_glossary(lines, dest_lang):
    """Build translation glossary from unit/ability/weapon names."""
    global TRANSLATION_GLOSSARY
    
    # First, try to load from external file
    if load_external_glossary(dest_lang):
        return  # Successfully loaded from file
    
    # If external glossary not found, build from scratch using Llama
    print("[Glossary] External glossary not found, building from scratch...")
    
    # Patterns for keys that should be in glossary
    glossary_patterns = [
        r'^Unit/Name/',
        r'^Button/Name/',
        r'^Abil/Name/',
        r'^Weapon/Name/',
        r'^Upgrade/Name/',
        r'^Behavior/Name/',
        r'^DataCollection/Name/',
        r'^Unit/Description/',
        r'^Unit/LifeArmorName/',
        r'^Alert/Text/',
    ]
    
    glossary_items = []
    for line in lines:
        stripped = line.strip('\ufeff\n\r')
        if "=" in stripped and not stripped.startswith("#"):
            parts = stripped.split("=", 1)
            if len(parts) == 2:
                key = parts[0].strip()
                value = parts[1].strip()
                
                # Check if key matches any glossary pattern
                for pattern in glossary_patterns:
                    if re.match(pattern, key, re.IGNORECASE):
                        glossary_items.append((key, value))
                        break
    
    if not glossary_items:
        print("[Glossary] No glossary items found")
        return

    print(f"[Glossary] Building glossary with {len(glossary_items)} terms...")
    
    # Build glossary prompt
    lang_names = {
        "de": "German",
        "es": "Spanish",
        "fr": "French",
        "it": "Italian",
        "ko": "Korean",
        "pl": "Polish",
        "pt": "Portuguese",
        "ru": "Russian",
        "zh-CN": "Chinese (Simplified)",
        "zh-TW": "Chinese (Traditional)"
    }
    target_lang = lang_names.get(dest_lang, dest_lang)
    
    # Create glossary text
    glossary_text = "\n".join([f"{key} = {value}" for key, value in glossary_items])
    
    glossary_prompt = f"""You are translating game strings for a Command & Conquer style RTS game.
Create a consistent translation glossary for the following terms from English to {target_lang}.

RULES:
1. Translate unit names, ability names, weapon names consistently
2. Keep proper nouns (like CABAL, GDI, NOD faction names) in appropriate form for {target_lang}
3. Use established gaming terminology if available
4. Format: KEY = TRANSLATION (one per line)

TERMS TO TRANSLATE:
{glossary_text}

Output ONLY the translated glossary, one line per term in format: KEY = TRANSLATION
Do not add any explanations or comments."""
    
    # Translate glossary
    try:
        result = translate_with_services(glossary_prompt, dest_lang)
        if result:
            # Parse results
            TRANSLATION_GLOSSARY = {}
            for line in result.split('\n'):
                if '=' in line:
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = parts[1].strip()
                        if key and value:
                            TRANSLATION_GLOSSARY[key] = value
            
            print(f"[Glossary] Created {len(TRANSLATION_GLOSSARY)} translation rules")
        else:
            print("[Glossary] Failed to translate glossary")
    except Exception as e:
        print(f"[Glossary] Error: {e}")


def apply_glossary(text):
    """Apply glossary translations to text."""
    if not TRANSLATION_GLOSSARY:
        return text
    
    result = text
    # Sort by length descending to avoid partial replacements
    for key, value in sorted(TRANSLATION_GLOSSARY.items(), key=lambda x: len(x[0]), reverse=True):
        # Skip if key and value are the same (marked as "keep as is")
        if key == value:
            continue
        
        # Replace whole words and also partial matches (for compound names like "CABALCenturion")
        # First try whole word, then try partial
        result = re.sub(r'\b' + re.escape(key) + r'\b', value, result)
        # Also replace in compound names (case insensitive)
        result = re.sub(re.escape(key), value, result, flags=re.IGNORECASE)
    
    return result


def translate_by_blocks(current_batch, dest_lang, copy_only=False):
    """Translate by blocks/sections - groups strings by their section header."""
    if not current_batch:
        return []
    
    if copy_only:
        return [item[2] for item in current_batch]

    all_tags = []
    processed_texts = []
    tag_pattern = re.compile(r'<[^>]+>|%[\w\.]+%|\[[^\]]+\]|~[^~]+~', re.IGNORECASE)
    
    # Find tags in all texts
    for item in current_batch:
        text = item[2]
        temp_text = text
        tags = tag_pattern.findall(text)
        for tag in tags:
            placeholder = f"@TAG{len(all_tags)}@"
            all_tags.append(tag)
            temp_text = temp_text.replace(tag, placeholder, 1)
        processed_texts.append((item[0], item[1], temp_text))
    
    # Join all texts with separator
    sep = "\n---\n"
    combined_text = sep.join([item[2] for item in processed_texts])
    
    # Translate
    translated_combined = None
    wait_time = 5
    for attempt in range(15):
        try:
            time.sleep(0.3)
            translated_combined = translate_with_services(combined_text, dest_lang)
            if translated_combined:
                break
        except Exception as e:
            print(f"\n[Block] Attempt {attempt+1} error: {str(e)}. Waiting {wait_time}s...")
            time.sleep(wait_time)
            wait_time = min(wait_time + 5, 30)

    if not translated_combined:
        return None

    # Split results
    split_pattern = re.compile(r'\n?---\n?|\n?\[# # #\]\n?', re.IGNORECASE)
    results = split_pattern.split(translated_combined)
    results = [r.strip() for r in results if r.strip() and r.strip() != "---"]

    if len(results) != len(current_batch):
        print(f"\n[Warning] Block split mismatch! Expected {len(current_batch)}, got {len(results)}")
        # Fallback
        results = translated_combined.split("---")
        results = [r.strip() for r in results if r.strip()]
        
        if len(results) != len(current_batch):
            return None

    # Restore tags
    final_results = []
    for res_text in results:
        temp_res = res_text.strip()
        for i in range(len(all_tags)):
            placeholder = f"@TAG{i}@"
            if placeholder in temp_res:
                temp_res = temp_res.replace(placeholder, all_tags[i])
        
        # Apply glossary for consistent translations
        temp_res = apply_glossary(temp_res)
        
        final_results.append(temp_res)

    return final_results


TRANSLATORS = {
    lang: ["papago", "google", "llama", "libre", ] if lang == "ko" else ["google", "llama", "libre"]
    for lang in set(SC2_LOCALES.values())
}

def translate_with_services(text, lang):
    # Если задан глобальный аргумент --translator, используем только его
    if getattr(args, 'translator', None):
        engine = args.translator.lower()
        try:
            if engine == "papago":
                return translate_papago(text, lang)
            elif engine == "google":
                return translate_google(text, lang)
            elif engine == "libre":
                return translate_libre(text, lang)
            elif engine == "llama":
                return translate_llama(text, lang)
            else:
                print(f"[!] Unknown translator '{engine}', falling back to default.")
        except Exception as e:
            print(f"[{engine}] error: {e}")
        return None

    # Старое поведение: список движков по языку
    engines = TRANSLATORS.get(lang, ["google"])
    for engine in engines:
        try:
            if engine == "papago":
                result = translate_papago(text, lang)
            elif engine == "google":
                result = translate_google(text, lang)
            elif engine == "libre":
                result = translate_libre(text, lang)
            elif engine == "llama":
                result = translate_llama(text, lang)
            else:
                continue
            if result:
                return result
        except Exception as e:
            print(f"[{engine}] error: {e}")

    return None

# ======================
# CORE TRANSLATION (BATCH)
# ======================

def translate_batch(current_batch, dest_lang, max_retries=15, copy_only=False):
    if not current_batch:
        return []
    
    if copy_only:
        # Just return the original values
        return [item[2] for item in current_batch]

    # 1. Protect tags in the entire batch
    all_tags = []
    processed_texts = []
    tag_pattern = re.compile(r'<[^>]+>|%[\w\.]+%|\[[^\]]+\]|~[^~]+~', re.IGNORECASE)

    for item in current_batch:
        text = item[2] # Extract text from (index, key, value)
        temp_text = text
        tags = tag_pattern.findall(text)
        for tag in tags:
            placeholder = f"@TAG{len(all_tags)}@"
            all_tags.append(tag)
            temp_text = temp_text.replace(tag, placeholder, 1)
        processed_texts.append(temp_text)

    # 2. Join into one string with separator
    sep = "\n[###]\n"
    combined_text = sep.join(processed_texts)

    # 3. Translation
    translated_combined = None
    wait_time = 5
    for attempt in range(max_retries):
        try:
            time.sleep(1) # Base delay for stability
            time.sleep(0.3) # Base delay for stability
            translated_combined = translate_with_services(combined_text, dest_lang)
            if translated_combined:
                break
        except Exception as e:
            print(f"\n[Batch] Attempt {attempt+1} error: {str(e)}. Waiting {wait_time}s...")
            time.sleep(wait_time)
            wait_time = min(wait_time + 5, 30)

    if not translated_combined:
        return None

    # 4. Split and restore tags
    # Handle possible variations in separator after translation
    split_pattern = re.compile(r'\n?\s*\[###\]\s*\n?|\n?\[# # #\]\n?', re.IGNORECASE)
    results = split_pattern.split(translated_combined)
    
    # Remove empty first/last elements if they exist
    results = [r.strip() for r in results if r.strip() != "[###]" and r.strip() != ""]

    if len(results) != len(current_batch):
        print(f"\n[Warning] Batch split mismatch! Expected {len(current_batch)}, got {len(results)}")
        # Debug: printing a snippet of what we got
        snippet = translated_combined[:200].replace('\n', ' ')
        print(f"[Debug] Response snippet: {snippet}...")
        
        # Fallback to simple split
        results = translated_combined.split("[###]")
        results = [r.strip() for r in results if r.strip()]
        
        if len(results) != len(current_batch):
            return None

    final_results = []
    for res_text in results:
        temp_res = res_text.strip()
        for i in range(len(all_tags)):
            placeholder = f"@TAG{i}@"
            if placeholder in temp_res:
                temp_res = temp_res.replace(placeholder, all_tags[i])
        final_results.append(temp_res)

    return final_results


def load_gamestrings_map(path):
    """Loads file and returns a key -> value dictionary."""
    data = {}
    if not os.path.exists(path):
        return data
    try:
        with open(path, "r", encoding=ENCODING) as f:
            for line in f:
                stripped = line.strip('\ufeff\n\r')
                if "=" in stripped and not stripped.startswith("#"):
                    parts = stripped.split("=", 1)
                    if len(parts) == 2:
                        data[parts[0].strip()] = parts[1].strip()
    except Exception as e:
        print(f"Error loading {path}: {e}")
    return data


# ======================
# LOAD EXISTING
# ======================

def load_existing_translations(file_path):
    translations = {}
    if not os.path.exists(file_path):
        return translations

    try:
        with open(file_path, "r", encoding=ENCODING) as f:
            for line in f:
                d = line.strip('\ufeff\n\r')
                if "=" in d and not d.startswith("#"):
                    parts = d.split("=", 1)
                    if len(parts) == 2:
                        k, v = parts
                        translations[k.strip()] = v
    except:
        pass
    return translations


def format_time(seconds):
    if seconds < 0: return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0: return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# ======================
# PROCESS FILE
# ======================

def sync_file(input_file, last_file, output_pattern, target_langs, copy_only=False):
    if not os.path.exists(input_file):
        print(f"Error: Input file not found {input_file}")
        return

    input_name = os.path.basename(input_file)
    print(f"\n>>> Processing: {input_name} (Copy-only: {copy_only})")

    # Load current and previous files for comparison
    current_map = load_gamestrings_map(input_file)
    last_map = load_gamestrings_map(last_file)

    # Identify changed or new keys
    if getattr(args, 'force', False):
        changed_keys = set(current_map.keys())
    else:
        changed_keys = set()
        for k, v in current_map.items():
            if k not in last_map or last_map[k] != v:
                changed_keys.add(k)

    if changed_keys:
        print(f"Changes detected in original: {len(changed_keys)} strings.")

    # Read lines to preserve structure
    with open(input_file, "r", encoding=ENCODING) as f:
        original_lines = f.readlines()

    any_lang_updated = False
    
    # Clear glossary for each run (will be rebuilt for each target language)
    global TRANSLATION_GLOSSARY
    TRANSLATION_GLOSSARY = {}
    
    for sc2_lang in target_langs:
        # Code for API (e.g., ruRU -> ru)
        api_lang = SC2_LOCALES[sc2_lang]
        
        # Path configuration for specific locale
        output_path = output_pattern.replace("{lang}", sc2_lang).replace("{locale}", sc2_lang)
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        existing_map = load_existing_translations(output_path)

        # SPANISH LOGIC: if file is empty, check alternative dialect
        if not existing_map and api_lang == "es" and not copy_only:
            alt_lang = "esMX" if sc2_lang == "esES" else "esES"
            alt_path = output_pattern.replace("{lang}", alt_lang).replace("{locale}", alt_lang)
            if os.path.exists(alt_path):
                print(f"[{sc2_lang}] Using '{alt_lang}' as a base...")
                existing_map = load_existing_translations(alt_path)

        # If original changed, remove old translation from cache to re-translate
        for k in changed_keys:
            if k in existing_map:
                del existing_map[k]

        # Gather what actually needs to be translated
        to_translate = []
        for i, line in enumerate(original_lines):
            stripped = line.strip('\ufeff\n\r')
            if "=" in stripped and not stripped.startswith("#"):
                parts = stripped.split("=", 1)
                if len(parts) == 2:
                    key, val = parts
                    key = key.strip()
                    if key not in existing_map:
                        to_translate.append((i, key, val.strip()))

        total_new = len(to_translate)
        total_all = len(current_map)

        if total_new == 0:
            continue
        
        any_lang_updated = True

        # Показываем какой переводчик используется
        if not copy_only:
            if getattr(args, 'translator', None):
                print(f"[{sc2_lang}] Using translator: {args.translator.lower()}")
            else:
                engines = TRANSLATORS.get(api_lang, ["google"])
                print(f"[{sc2_lang}] Using translator: {engines[0]}")

        action_word = "Copying" if copy_only else "Translating"
        # Removed redundant header print
        
        # GLOBAL HARD LIMIT: 3500 (lower for better stability, API limit is 5000)
        GLOBAL_MAX = 3500
        max_chars_limit = GLOBAL_MAX
        
        # Check if using llama (for block-based translation)
        use_llama = False
        translator_arg = getattr(args, 'translator', None)
        if translator_arg:
            use_llama = translator_arg.lower() == "llama"
        else:
            engines = TRANSLATORS.get(api_lang, ["google"])
            if engines and engines[0] == "llama":
                use_llama = True
        
        # For Llama, use larger blocks (up to max_chars limit)
        if use_llama:
            llama_max = CONFIG.get("translators", {}).get("llama", {}).get("max_chars", 8000)
            max_chars_limit = llama_max
            print(f"[{sc2_lang}] Using block-based translation (Llama)")
            
            # Build glossary first for consistent translations
            if not TRANSLATION_GLOSSARY and not copy_only:
                print(f"[{sc2_lang}] Building translation glossary...")
                build_glossary(original_lines, api_lang)
        elif not copy_only:
            engines_cfg = TRANSLATORS.get(api_lang, ["google"])
            for eng in engines_cfg:
                limit = CONFIG.get("translators", {}).get(eng, {}).get("max_chars", GLOBAL_MAX)
                max_chars_limit = min(max_chars_limit, limit)

        def get_batches(items, max_len):
            chunks = []
            curr = []
            curr_len = 0
            # Separator [###] (~10 chars)
            sep_len = 11 
            # Tag replacement margin (tag <..> can become [[BTAG_100]])
            tag_margin = 15
            
            for it in items:
                # Count string len + separator + tag margin
                it_len = len(it[2]) + sep_len + tag_margin
                
                if curr and curr_len + it_len > max_len:
                    chunks.append(curr)
                    curr = [it]
                    curr_len = it_len
                else:
                    curr.append(it)
                    curr_len += it_len
            if curr: chunks.append(curr)
            return chunks

        batches_to_process = get_batches(to_translate, max_chars_limit)
        # Removed redundant batch count print

        def show_progress(current, total, elapsed=None, eta=None, batch_current=None, batch_total=None):
            percent = (current / total) * 100 if total > 0 else 0
            bar_len = 25
            filled = int(bar_len * current // total) if total > 0 else 0
            bar = '█' * filled + '-' * (bar_len - filled)
            
            time_info = ""
            if elapsed is not None:
                time_info = f" | {format_time(elapsed)}"
                if eta is not None and getattr(args, 'eta', False):
                    time_info += f" < {format_time(eta)}"

            batch_info = ""
            if batch_current is not None and batch_total is not None:
                batch_info = f" ({batch_current}/{batch_total})"

            sys.stdout.write(f"\r[{sc2_lang}] Progress: {current}/{total}{batch_info} |{bar}| {percent:.1f}%{time_info}")
            sys.stdout.flush()

        session_start = time.time()
        translated_this_session = 0
        
        # Only count progress for keys that exist in the CURRENT file
        def get_current_progress_count():
            return sum(1 for k in current_map if k in existing_map)

        show_progress(get_current_progress_count(), total_all, 0, 0,0,len(batches_to_process))

        batch_current = 0;
        for batch in batches_to_process:
            batch_current += 1
            # Use block-based translation for llama, regular batch for others
            if use_llama and not copy_only:
                results = translate_by_blocks(batch, api_lang, copy_only=copy_only)
            else:
                results = translate_batch(batch, api_lang, copy_only=copy_only)
            if results and len(results) == len(batch):
                # 1. Update results map
                for idx, res in enumerate(results):
                    _, key, _ = batch[idx]
                    existing_map[key] = res
                
                translated_this_session += len(batch)
                
                # 2. Save progress to file
                save_current_progress(output_path, original_lines, existing_map)
                
                # 3. Time calculation
                elapsed = time.time() - session_start
                lines_per_sec = translated_this_session / elapsed if elapsed > 0 else 0
                remaining = total_new - translated_this_session
                eta = remaining / lines_per_sec if lines_per_sec > 0 else 0
                
                show_progress(get_current_progress_count(), total_all, elapsed, eta, batch_current,len(batches_to_process))
            else:
                batch_end_time = time.strftime("%H:%M:%S")
                print(f"\n[!] [{batch_end_time}] API error on batch {batch_current}. Skipping or retrying...")
                continue

            # Log completion time
            batch_end_time = time.strftime("%H:%M:%S")
            elapsed_batch = time.time() - session_start
            sys.stdout.write(f" [{batch_end_time}] Completed batch {batch_current} ({len(batch)} items) | Total: {translated_this_session}/{total_new}")

        # Combined results line
        sys.stdout.write("\n")
        sys.stdout.flush()

    if not any_lang_updated:
        print("--- No updates required. ---")

    # Sync Last file at the end (ONLY if original changed)
    if changed_keys and os.path.exists(input_file):
        last_dir = os.path.dirname(last_file)
        if last_dir and not os.path.exists(last_dir):
            os.makedirs(last_dir)
        shutil.copy2(input_file, last_file)
        # Simplified sync message to include folder name
        rel_last = os.path.relpath(last_file, SCRIPT_DIR)
        print(f"Sync: {os.path.basename(input_file)} -> {rel_last}")


def process_file():
    parser = argparse.ArgumentParser(description='SC2 GameStrings Translator with Change Detection')
    parser.add_argument('langs', nargs='*', help='Target languages (e.g., ruRU koKR frFR)')
    parser.add_argument('--langs', dest='langs_flag', help='Comma-separated list of target languages (e.g., ruRU,koKR)')
    parser.add_argument('--input', '-i', help='Input GameStrings.txt path')
    parser.add_argument('--last', '-l', help='Previous GameStrings.txt for comparison')
    parser.add_argument('--output', '-o', help='Output pattern (use {lang} or {locale})')
    parser.add_argument('--copy-only', action='store_true', help='Skip translation, just copy strings to target files')
    parser.add_argument('--mod', '-m', help='Path to SC2Mod folder for full synchronization')
    parser.add_argument('--eta', action='store_true', help='Show estimated time to completion (ETA) in progress bar')
    parser.add_argument('--list', action='store_true', help='List all supported SC2 locales and exit')
    parser.add_argument('--translator', '-t', help='Force use a specific translator (libre, google, papago, llama)')
    parser.add_argument('--force', action='store_true', help='Force translation of all strings, ignoring last file')
    # Store args globally or ensure local show_progress can access it
    global args
    
    args = parser.parse_args()

    if args.list:
        print("Supported SC2 Locales:")
        for loc in sorted(SC2_LOCALES.keys()):
            print(f"  - {loc} ({SC2_LOCALES[loc]})")
        return

    # Input language validation
    raw_langs = list(args.langs)
    if args.langs_flag:
        raw_langs.extend(args.langs_flag.replace(',', ' ').split())
    
    if not raw_langs:
        raw_langs = DEFAULT_LANGS
    target_langs = []
    
    for l in raw_langs:
        if l in SC2_LOCALES:
            target_langs.append(l)
        else:
            # Try to find match if short code was entered
            matched = [sc2 for sc2, api in SC2_LOCALES.items() if api == l]
            if matched:
                target_langs.append(matched[0])
            else:
                print(f"[!] Error: Code '{l}' is not a valid SC2 locale.")
                print(f"Supported locales: {', '.join(SC2_LOCALES.keys())}")
                return

    if args.mod:
        mod_path = args.mod
        if not os.path.exists(mod_path):
            print(f"Error: Mod path not found: {mod_path}")
            return
        
        # Path to source English data
        en_path = os.path.join(mod_path, "enUS.SC2Data", "LocalizedData")
        if not os.path.exists(en_path):
            print(f"Error: enUS.SC2Data/LocalizedData not found in {mod_path}")
            return

        # Determine location for 'Last' files
        mod_name = os.path.basename(os.path.normpath(mod_path))
        # Default is translate/last/mod_name/
        last_base_dir = args.last if args.last else os.path.join(SCRIPT_DIR, "last", mod_name)
        
        # 1. GameStrings.txt (Translation)
        gs_input = os.path.join(en_path, "GameStrings.txt")
        gs_last = os.path.join(last_base_dir, "GameStrings.txt") if os.path.isdir(last_base_dir) else last_base_dir
        # If it's a directory, we use GameStrings.txt inside it.
        # This handles the case where user might still pass a single file.
        if os.path.isdir(last_base_dir) or not os.path.isfile(last_base_dir):
             gs_last = os.path.join(last_base_dir, "GameStrings.txt")

        gs_output = os.path.join(mod_path, "{lang}.SC2Data", "LocalizedData", "GameStrings.txt")
        sync_file(gs_input, gs_last, gs_output, target_langs, copy_only=False)

        # 2. Other files (Copy-only)
        other_files = ["ObjectStrings.txt", "TriggerStrings.txt", "GameHotkeys.txt"]
        for f_name in other_files:
            f_input = os.path.join(en_path, f_name)
            if os.path.exists(f_input):
                f_last = os.path.join(last_base_dir, f_name)
                f_output = os.path.join(mod_path, "{lang}.SC2Data", "LocalizedData", f_name)
                sync_file(f_input, f_last, f_output, target_langs, copy_only=True)
    else:
        # Paths configuration for single file
        input_file = args.input if args.input else INPUT_FILE
        
        # Smarter default for last_file
        if args.last:
            if os.path.isdir(args.last):
                last_file = os.path.join(args.last, os.path.basename(input_file))
            else:
                last_file = args.last
        else:
            input_name = os.path.basename(input_file)
            name_only, ext = os.path.splitext(input_name)
            # Default to flat list next to input if no directory logic used
            last_file = os.path.join(os.path.dirname(input_file) or SCRIPT_DIR, f"{name_only}_Last{ext}")

        output_pattern = args.output if args.output else os.path.join(OUTPUT_DIR, "GameStrings_{lang}_Google.txt")
        
        sync_file(input_file, last_file, output_pattern, target_langs, copy_only=args.copy_only)


def save_current_progress(path, original_lines, translation_map):
    with open(path, "w", encoding=ENCODING) as f:
        for line in original_lines:
            stripped = line.strip('\ufeff\n\r')
            if "=" in stripped and not stripped.startswith("#"):
                parts = stripped.split("=", 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    if key in translation_map:
                        f.write(f"{key}={translation_map[key]}\n")
                    # If no translation exists, we skip it
                    # so it gets re-translated next time.
                else:
                    # Skip malformed lines
                    pass
            else:
                # Keep comments and empty lines
                f.write(line)
        f.flush()


# ======================
# ENTRY POINT
# ======================

if __name__ == "__main__":
    process_file()