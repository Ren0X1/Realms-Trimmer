"""Realms Trimmer: trims Minecraft worlds so Realms accepts the upload.

Removes the chunks no player has ever visited (for example the ones Chunky
pre-generates) and keeps a margin around the visited areas. The original
world is never modified: it always works on a copy.

Usage:
    Double-click the file                -> opens the window.
    python realms_trimmer.py INPUT [OUTPUT] [--margin 3] [--name NAME] [--lang en|es|ru|zh]
    python realms_trimmer.py INPUT --analyze
"""
import argparse
import gzip
import json
import os
import shutil
import struct
import sys
import zlib

SECTOR = 4096
APP_TITLE = 'Realms Trimmer'
INHABITED_TAG = b'\x04\x00\x0dInhabitedTime'


# --------------------------------------------------------------------------
# Languages
# --------------------------------------------------------------------------

LANGUAGES = {'en': 'English', 'es': 'Español', 'ru': 'Русский', 'zh': '中文'}
DEFAULT_LANG = 'en'

STRINGS = {
    'subtitle': {
        'en': 'Trim your world before uploading it to Realms',
        'es': 'Recorta tu mundo antes de subirlo a Realms',
        'ru': 'Обрежьте мир перед загрузкой в Realms',
        'zh': '上传到 Realms 之前先精简你的世界',
    },
    'world': {'en': 'World', 'es': 'Mundo', 'ru': 'Мир', 'zh': '世界'},
    'output': {'en': 'Output', 'es': 'Copia', 'ru': 'Копия', 'zh': '输出'},
    'margin': {'en': 'Margin', 'es': 'Margen', 'ru': 'Запас', 'zh': '边距'},
    'browse': {'en': 'Browse', 'es': 'Examinar', 'ru': 'Обзор', 'zh': '浏览'},
    'analyze': {'en': 'Analyze', 'es': 'Analizar', 'ru': 'Анализ', 'zh': '分析'},
    'trim': {'en': 'Trim', 'es': 'Recortar', 'ru': 'Обрезать', 'zh': '精简'},
    'ready': {'en': 'Ready', 'es': 'Listo', 'ru': 'Готово', 'zh': '就绪'},
    'status_analyzing': {'en': 'Analyzing...', 'es': 'Analizando...', 'ru': 'Анализ...', 'zh': '正在分析...'},
    'status_trimming': {'en': 'Trimming...', 'es': 'Recortando...', 'ru': 'Обрезка...', 'zh': '正在精简...'},
    'status_analyzed': {
        'en': '✅ Analysis done', 'es': '✅ Análisis terminado',
        'ru': '✅ Анализ завершён', 'zh': '✅ 分析完成',
    },
    'status_trimmed': {
        'en': '✅ Copy created', 'es': '✅ Copia creada',
        'ru': '✅ Копия создана', 'zh': '✅ 副本已创建',
    },
    'status_error': {'en': '❌ Error', 'es': '❌ Error', 'ru': '❌ Ошибка', 'zh': '❌ 错误'},
    'intro': {
        'en': '1. Close Minecraft.\n2. Pick your world.\n'
              '3. Click Analyze to see how much will be removed, or Trim to create the copy.',
        'es': '1. Cierra Minecraft.\n2. Elige tu mundo.\n'
              '3. Pulsa Analizar para ver cuánto se recorta, o Recortar para crear la copia.',
        'ru': '1. Закройте Minecraft.\n2. Выберите мир.\n'
              '3. Нажмите «Анализ», чтобы увидеть, сколько будет удалено, или «Обрезать», чтобы создать копию.',
        'zh': '1. 关闭 Minecraft。\n2. 选择你的世界。\n'
              '3. 点击“分析”查看会删除多少，或点击“精简”创建副本。',
    },
    'pick_world': {
        'en': 'Pick your world folder', 'es': 'Elige la carpeta de tu mundo',
        'ru': 'Выберите папку мира', 'zh': '选择你的世界文件夹',
    },
    'pick_output': {
        'en': 'Pick where to save the copy', 'es': 'Elige dónde guardar la copia',
        'ru': 'Выберите, куда сохранить копию', 'zh': '选择副本的保存位置',
    },
    'confirm': {
        'en': 'Make sure Minecraft is closed.\n\nA trimmed copy will be created in:\n{dest}\n\n'
              'The original world is not modified.',
        'es': 'Asegúrate de que Minecraft está cerrado.\n\nSe creará una copia recortada en:\n{dest}\n\n'
              'El mundo original no se modifica.',
        'ru': 'Убедитесь, что Minecraft закрыт.\n\nОбрезанная копия будет создана в:\n{dest}\n\n'
              'Исходный мир не изменяется.',
        'zh': '请确认 Minecraft 已关闭。\n\n将在以下位置创建精简副本：\n{dest}\n\n原世界不会被修改。',
    },
    'log_analyzing': {
        'en': 'Analyzing chunks...', 'es': 'Analizando chunks...',
        'ru': 'Анализ чанков...', 'zh': '正在分析区块...',
    },
    'log_copying': {
        'en': 'Copying world to: {dest}', 'es': 'Copiando mundo a: {dest}',
        'ru': 'Копирование мира в: {dest}', 'zh': '正在复制世界到：{dest}',
    },
    'log_trimming': {
        'en': 'Trimming regions...', 'es': 'Recortando regiones...',
        'ru': 'Обрезка регионов...', 'zh': '正在精简区域文件...',
    },
    'size_now': {
        'en': 'Current size: {mb} MB', 'es': 'Tamaño actual: {mb} MB',
        'ru': 'Текущий размер: {mb} МБ', 'zh': '当前大小：{mb} MB',
    },
    'size_original': {
        'en': 'Original size: {mb} MB', 'es': 'Tamaño original: {mb} MB',
        'ru': 'Исходный размер: {mb} МБ', 'zh': '原始大小：{mb} MB',
    },
    'size_trimmed': {
        'en': 'Trimmed size: {mb} MB', 'es': 'Tamaño recortado: {mb} MB',
        'ru': 'Размер после обрезки: {mb} МБ', 'zh': '精简后大小：{mb} MB',
    },
    'log_done': {
        'en': 'Done. Upload "{name}" to Realms without opening it in singleplayer first.',
        'es': 'Listo. Sube a Realms el mundo "{name}" sin abrirlo antes en un jugador.',
        'ru': 'Готово. Загрузите «{name}» в Realms, не открывая его перед этим в одиночной игре.',
        'zh': '完成。请将“{name}”上传到 Realms，上传前不要在单人游戏中打开它。',
    },
    'tbl_dimension': {'en': 'Dimension', 'es': 'Dimensión', 'ru': 'Измерение', 'zh': '维度'},
    'tbl_total': {'en': 'Total', 'es': 'Total', 'ru': 'Всего', 'zh': '总数'},
    'tbl_visited': {'en': 'Visited', 'es': 'Visitados', 'ru': 'Посещено', 'zh': '已访问'},
    'tbl_kept': {'en': 'Kept', 'es': 'Se quedan', 'ru': 'Останется', 'zh': '保留'},
    'tbl_sum': {'en': 'TOTAL', 'es': 'TOTAL', 'ru': 'ИТОГО', 'zh': '合计'},
    'unreadable': {
        'en': '  ({n} chunks could not be read; they are kept)',
        'es': '  ({n} chunks no se pudieron leer; se conservan)',
        'ru': '  ({n} чанков не удалось прочитать; они сохранены)',
        'zh': '  （{n} 个区块无法读取，已保留）',
    },
    'kept_pct': {
        'en': 'Keeping {pct}% of the chunks (margin = {m}).',
        'es': 'Se conserva el {pct}% de los chunks (margen = {m}).',
        'ru': 'Сохраняется {pct}% чанков (запас = {m}).',
        'zh': '保留 {pct}% 的区块（边距 = {m}）。',
    },
    'warn_levelname': {
        'en': 'Warning: LevelName not found in level.dat; the name is not changed.',
        'es': 'Aviso: no se encontró LevelName en level.dat; no se cambia el nombre.',
        'ru': 'Внимание: LevelName не найден в level.dat; имя не изменено.',
        'zh': '警告：level.dat 中没有找到 LevelName，名称未修改。',
    },
    'err_not_world': {
        'en': '"{path}" does not look like a Minecraft world (level.dat is missing).',
        'es': '"{path}" no parece un mundo de Minecraft (falta level.dat).',
        'ru': '«{path}» не похоже на мир Minecraft (нет level.dat).',
        'zh': '“{path}”不是 Minecraft 世界（缺少 level.dat）。',
    },
    'err_no_region': {
        'en': 'No "region" folder was found in the world.',
        'es': 'No se encontró ninguna carpeta "region" en el mundo.',
        'ru': 'В мире не найдена папка «region».',
        'zh': '世界中没有找到 “region” 文件夹。',
    },
    'err_no_output': {
        'en': 'Pick an output folder.', 'es': 'Elige una carpeta de salida.',
        'ru': 'Выберите папку для копии.', 'zh': '请选择输出文件夹。',
    },
    'err_exists': {
        'en': '"{path}" already exists. Delete it or pick another output folder.',
        'es': 'Ya existe "{path}". Bórrala o elige otra carpeta de salida.',
        'ru': '«{path}» уже существует. Удалите её или выберите другую папку.',
        'zh': '“{path}”已存在。请删除它或选择其他输出文件夹。',
    },
    'err_inside': {
        'en': 'The output folder cannot be inside the original world.',
        'es': 'La carpeta de salida no puede estar dentro del mundo original.',
        'ru': 'Папка для копии не может находиться внутри исходного мира.',
        'zh': '输出文件夹不能位于原世界内。',
    },
    'err_margin': {
        'en': 'The margin must be a number from 0 up.',
        'es': 'El margen tiene que ser un número de 0 en adelante.',
        'ru': 'Запас должен быть числом от 0 и больше.',
        'zh': '边距必须是 0 或更大的数字。',
    },
    'cli_desc': {
        'en': 'Creates a copy of a Minecraft world without the unvisited chunks, so it can be '
              'uploaded to Realms. With no arguments it opens the window.',
        'es': 'Crea una copia de un mundo de Minecraft sin los chunks no visitados, para subirla '
              'a Realms. Sin argumentos abre la ventana.',
        'ru': 'Создаёт копию мира Minecraft без непосещённых чанков, чтобы её можно было '
              'загрузить в Realms. Без аргументов открывает окно.',
        'zh': '创建一个不含未访问区块的 Minecraft 世界副本，以便上传到 Realms。不带参数时打开窗口。',
    },
    'cli_input': {
        'en': 'World folder.', 'es': 'Carpeta del mundo.',
        'ru': 'Папка мира.', 'zh': '世界文件夹。',
    },
    'cli_output': {
        'en': 'Folder where the copy is created (default "<input> (Realms)").',
        'es': 'Carpeta donde se crea la copia (por defecto "<entrada> (Realms)").',
        'ru': 'Папка, в которой создаётся копия (по умолчанию «<вход> (Realms)»).',
        'zh': '创建副本的文件夹（默认为“<输入> (Realms)”）。',
    },
    'cli_margin': {
        'en': 'Chunks of margin around visited areas (default 3).',
        'es': 'Chunks de margen alrededor de las zonas visitadas (por defecto 3).',
        'ru': 'Запас в чанках вокруг посещённых зон (по умолчанию 3).',
        'zh': '已访问区域周围保留的区块边距（默认 3）。',
    },
    'cli_name': {
        'en': 'World name shown in the game (default: output folder name).',
        'es': 'Nombre del mundo en el juego (por defecto el de la carpeta de salida).',
        'ru': 'Название мира в игре (по умолчанию имя папки копии).',
        'zh': '游戏中显示的世界名称（默认为输出文件夹名）。',
    },
    'cli_analyze': {
        'en': 'Only show how much would be trimmed, without creating anything.',
        'es': 'Solo muestra cuánto se recortaría, sin crear nada.',
        'ru': 'Только показать, сколько будет обрезано, ничего не создавая.',
        'zh': '只显示会精简多少，不创建任何内容。',
    },
    'cli_lang': {
        'en': 'Language: en, es, ru, zh.', 'es': 'Idioma: en, es, ru, zh.',
        'ru': 'Язык: en, es, ru, zh.', 'zh': '语言：en、es、ru、zh。',
    },
}

_lang = DEFAULT_LANG
SETTINGS_FILE = os.path.join(os.path.expanduser('~'), '.realms_trimmer.json')


def set_language(code):
    global _lang
    _lang = code if code in LANGUAGES else DEFAULT_LANG


def get_language():
    return _lang


def t(key, **kw):
    entry = STRINGS[key]
    text = entry.get(_lang) or entry[DEFAULT_LANG]
    return text.format(**kw) if kw else text


def chunks_label(n):
    if _lang == 'ru':
        if n % 10 == 1 and n % 100 != 11:
            word = 'чанк'
        elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            word = 'чанка'
        else:
            word = 'чанков'
        return f'{n} {word}'
    if _lang == 'zh':
        return f'{n} 个区块'
    return f'{n} chunk' + ('' if n == 1 else 's')


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(**values):
    data = load_settings()
    data.update(values)
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception:
        pass


# --------------------------------------------------------------------------
# Reading and writing region files (.mca)
# --------------------------------------------------------------------------

def read_region(path):
    """Returns {index: (payload, timestamp)} for the chunks in the file."""
    with open(path, 'rb') as f:
        data = f.read()
    chunks = {}
    if len(data) < 2 * SECTOR:
        return chunks
    for i in range(1024):
        off = int.from_bytes(data[i*4:i*4+3], 'big')
        if off == 0:
            continue
        p = off * SECTOR
        length = int.from_bytes(data[p:p+4], 'big')
        if length == 0 or p + 4 + length > len(data):
            continue
        ts = data[SECTOR + i*4:SECTOR + i*4 + 4]
        chunks[i] = (data[p:p+4+length], ts)
    return chunks


def write_region(path, chunks):
    header = bytearray(2 * SECTOR)
    body = bytearray()
    sector = 2
    for i in sorted(chunks):
        payload, ts = chunks[i]
        n = (len(payload) + SECTOR - 1) // SECTOR
        header[i*4:i*4+3] = sector.to_bytes(3, 'big')
        header[i*4+3] = min(n, 255)
        header[SECTOR + i*4:SECTOR + i*4 + 4] = ts
        body += payload + b'\x00' * (n * SECTOR - len(payload))
        sector += n
    with open(path, 'wb') as f:
        f.write(header + body)


def decompress(payload):
    comp = payload[4] & 0x7F
    raw = payload[5:]
    if comp == 2:
        return zlib.decompress(raw)
    if comp == 1:
        return gzip.decompress(raw)
    if comp == 3:
        return raw
    raise ValueError(f'unsupported compression: {comp}')


def inhabited_ticks(payload):
    """Ticks players have spent in the chunk. None if it can't be read."""
    try:
        d = decompress(payload)
    except Exception:
        return None
    k = d.find(INHABITED_TAG)
    if k < 0:
        return None
    start = k + len(INHABITED_TAG)
    return struct.unpack('>q', d[start:start+8])[0]


def region_coords(filename):
    _, x, z, _ = filename.split('.')
    return int(x), int(z)


def chunk_coords(rx, rz, i):
    return rx * 32 + (i % 32), rz * 32 + (i // 32)


# --------------------------------------------------------------------------
# Finding dimensions (new "dimensions/" layout and the classic one)
# --------------------------------------------------------------------------

def find_dimensions(world):
    """Returns {name: folder} for every dimension that has a region folder."""
    dims = {}
    new_root = os.path.join(world, 'dimensions')
    if os.path.isdir(new_root):
        for ns in sorted(os.listdir(new_root)):
            ns_dir = os.path.join(new_root, ns)
            if not os.path.isdir(ns_dir):
                continue
            for name in sorted(os.listdir(ns_dir)):
                d = os.path.join(ns_dir, name)
                if os.path.isdir(os.path.join(d, 'region')):
                    dims[f'{ns}:{name}'] = d
    for name, rel in (('overworld', ''), ('the_nether', 'DIM-1'), ('the_end', 'DIM1')):
        d = os.path.join(world, rel) if rel else world
        if os.path.isdir(os.path.join(d, 'region')):
            dims.setdefault(f'minecraft:{name}', d)
    return dims


def mca_files(folder):
    if not os.path.isdir(folder):
        return []
    return [f for f in os.listdir(folder) if f.startswith('r.') and f.endswith('.mca')]


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------

def scan_dimension(dim_dir, tick=None):
    """Returns (all_chunks, visited_chunks, unreadable_count)."""
    all_chunks, visited, unreadable = set(), set(), 0
    region_dir = os.path.join(dim_dir, 'region')
    for fn in mca_files(region_dir):
        if tick:
            tick()
        rx, rz = region_coords(fn)
        for i, (payload, _) in read_region(os.path.join(region_dir, fn)).items():
            c = chunk_coords(rx, rz, i)
            all_chunks.add(c)
            ticks = inhabited_ticks(payload)
            if ticks is None:
                unreadable += 1
                visited.add(c)  # when in doubt, keep it
            elif ticks > 0:
                visited.add(c)
    return all_chunks, visited, unreadable


def expand(chunks, margin):
    out = set()
    for cx, cz in chunks:
        for dx in range(-margin, margin + 1):
            for dz in range(-margin, margin + 1):
                out.add((cx + dx, cz + dz))
    return out


def folder_size_mb(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total / (1024 * 1024)


class Progress:
    """Spreads a 0..1 bar across steps and calls callback(fraction)."""

    def __init__(self, callback, total, start=0.0, end=1.0):
        self.callback, self.total, self.start, self.end = callback, max(total, 1), start, end
        self.done = 0

    def tick(self):
        self.done += 1
        if self.callback:
            self.callback(self.start + (self.end - self.start) * min(self.done / self.total, 1.0))


def count_region_files(world, subs=('region',)):
    return sum(len(mca_files(os.path.join(d, s)))
               for d in find_dimensions(world).values() for s in subs)


def plan(world, margin, progress=None, start=0.0, end=1.0):
    result = {}
    bar = Progress(progress, count_region_files(world), start, end)
    for name, d in find_dimensions(world).items():
        all_chunks, visited, unreadable = scan_dimension(d, bar.tick)
        keep = expand(visited, margin) & all_chunks
        result[name] = (d, all_chunks, visited, keep, unreadable)
    return result


def print_plan(result, margin, log=print):
    total_all = total_keep = 0
    log(f'{t("tbl_dimension"):<28}{t("tbl_total"):>10}{t("tbl_visited"):>11}{t("tbl_kept"):>11}')
    for name, (_, all_chunks, visited, keep, unreadable) in result.items():
        log(f'{name:<28}{len(all_chunks):>10}{len(visited):>11}{len(keep):>11}')
        if unreadable:
            log(t('unreadable', n=unreadable))
        total_all += len(all_chunks)
        total_keep += len(keep)
    log(f'{t("tbl_sum"):<28}{total_all:>10}{"":>11}{total_keep:>11}')
    if total_all:
        log(t('kept_pct', pct=f'{100 * total_keep / total_all:.0f}', m=margin))


# --------------------------------------------------------------------------
# Trimming
# --------------------------------------------------------------------------

def rename_level(level_dat, new_name, log=print):
    with open(level_dat, 'rb') as f:
        d = gzip.decompress(f.read())
    tag = b'\x08\x00\x09LevelName'
    i = d.find(tag)
    if i < 0:
        log(t('warn_levelname'))
        return
    i += len(tag)
    n = int.from_bytes(d[i:i+2], 'big')
    new = new_name.encode('utf-8')
    d = d[:i] + len(new).to_bytes(2, 'big') + new + d[i+2+n:]
    with open(level_dat, 'wb') as f:
        f.write(gzip.compress(d))


def trim(world, dest, margin, new_name, log=print, progress=None):
    log(t('log_analyzing'))
    result = plan(world, margin, progress, 0.0, 0.45)
    print_plan(result, margin, log)

    log('\n' + t('log_copying', dest=dest))
    shutil.copytree(world, dest, ignore=shutil.ignore_patterns('session.lock', 'realms-upload.log'))
    if progress:
        progress(0.6)

    log(t('log_trimming'))
    bar = Progress(progress, count_region_files(dest, ('region', 'entities', 'poi')), 0.6, 0.98)
    for name, (src_dim, _, _, keep, _) in result.items():
        dst_dim = os.path.join(dest, os.path.relpath(src_dim, world))
        for sub in ('region', 'entities', 'poi'):
            folder = os.path.join(dst_dim, sub)
            for fn in mca_files(folder):
                bar.tick()
                rx, rz = region_coords(fn)
                path = os.path.join(folder, fn)
                chunks = read_region(path)
                kept = {i: v for i, v in chunks.items() if chunk_coords(rx, rz, i) in keep}
                if kept:
                    if len(kept) != len(chunks):
                        write_region(path, kept)
                else:
                    os.remove(path)

    level_dat = os.path.join(dest, 'level.dat')
    if os.path.isfile(level_dat):
        rename_level(level_dat, new_name, log)
        old = os.path.join(dest, 'level.dat_old')
        if os.path.isfile(old):
            os.remove(old)

    log('\n' + t('size_original', mb=f'{folder_size_mb(world):,.1f}'))
    log(t('size_trimmed', mb=f'{folder_size_mb(dest):,.1f}'))
    log(t('log_done', name=new_name))
    if progress:
        progress(1.0)


# --------------------------------------------------------------------------
# Shared validation
# --------------------------------------------------------------------------

def validate(world, dest=None):
    """Returns an error message, or None if everything is fine."""
    if not world or not os.path.isfile(os.path.join(world, 'level.dat')):
        return t('err_not_world', path=world)
    if not find_dimensions(world):
        return t('err_no_region')
    if dest is not None:
        if not dest:
            return t('err_no_output')
        if os.path.exists(dest):
            return t('err_exists', path=dest)
        w = os.path.normcase(os.path.abspath(world))
        d = os.path.normcase(os.path.abspath(dest))
        if d == w or d.startswith(w + os.sep):
            return t('err_inside')
    return None


def default_dest(world):
    return world.rstrip('\\/') + ' (Realms)'


# --------------------------------------------------------------------------
# Window (double-click)
# --------------------------------------------------------------------------

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
ICON_ICO = os.path.join(ASSETS, 'icon.ico')
ICON_PNG = os.path.join(ASSETS, 'icon.png')


def apply_icon(root):
    """Sets the icon on the window and the taskbar (if the files exist)."""
    if sys.platform == 'win32':
        try:  # group the window under our icon instead of Python's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Ren0X1.RealmsTrimmer')
        except Exception:
            pass
        if os.path.isfile(ICON_ICO):
            try:
                root.iconbitmap(ICON_ICO)
            except Exception:
                pass
    if os.path.isfile(ICON_PNG):
        try:
            import tkinter as tk
            root._icon_img = tk.PhotoImage(file=ICON_PNG)
            root.iconphoto(True, root._icon_img)
        except Exception:
            pass


def gui():
    set_language(load_settings().get('lang', DEFAULT_LANG))
    try:
        import customtkinter  # noqa: F401
    except ImportError:
        return gui_classic()
    return gui_modern()


def gui_modern():
    import queue
    import threading
    from tkinter import filedialog, messagebox
    import customtkinter as ctk

    ctk.set_appearance_mode('dark')
    ctk.set_default_color_theme('green')

    root = ctk.CTk()
    root.title(APP_TITLE)
    root.geometry('760x620')
    root.minsize(640, 540)
    apply_icon(root)
    # CustomTkinter sets its own icon on startup; put ours back afterwards
    root.after(250, lambda: apply_icon(root))
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(0, weight=1)

    # State that survives a language change
    world_var = ctk.StringVar()
    output_var = ctk.StringVar()
    margin_var = ctk.IntVar(value=3)
    msgs = queue.Queue()
    state = {'busy': False}
    ui = {}
    MONO = ('Consolas', 12) if sys.platform == 'win32' else ('Menlo', 12)

    logo = None
    try:
        from PIL import Image
        if os.path.isfile(ICON_PNG):
            logo = ctk.CTkImage(Image.open(ICON_PNG), size=(56, 56))
    except Exception:
        logo = None

    def pick_in():
        d = filedialog.askdirectory(title=t('pick_world'))
        if d:
            world_var.set(os.path.normpath(d))
            output_var.set(default_dest(os.path.normpath(d)))

    def pick_out():
        d = filedialog.askdirectory(title=t('pick_output'))
        if d:
            base = os.path.basename(world_var.get()) if world_var.get() else t('world')
            output_var.set(os.path.join(os.path.normpath(d), base + ' (Realms)'))

    def on_language(name):
        code = next(c for c, n in LANGUAGES.items() if n == name)
        if code == get_language():
            return
        set_language(code)
        save_settings(lang=code)
        build()

    def build():
        """(Re)builds every widget in the current language."""
        if 'body' in ui:
            ui['body'].destroy()
        body = ctk.CTkFrame(root, fg_color='transparent')
        body.grid(row=0, column=0, sticky='nsew')
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(3, weight=1)
        ui['body'] = body

        # ---- Header ----------------------------------------------------
        header = ctk.CTkFrame(body, fg_color='transparent')
        header.grid(row=0, column=0, sticky='ew', padx=24, pady=(20, 8))
        header.grid_columnconfigure(1, weight=1)
        if logo:
            ctk.CTkLabel(header, image=logo, text='').grid(row=0, column=0, padx=(0, 14))
        titles = ctk.CTkFrame(header, fg_color='transparent')
        titles.grid(row=0, column=1, sticky='w')
        ctk.CTkLabel(titles, text=APP_TITLE, font=ctk.CTkFont(size=26, weight='bold')).pack(anchor='w')
        ctk.CTkLabel(titles, text=t('subtitle'), text_color=('gray35', 'gray65'),
                     font=ctk.CTkFont(size=13)).pack(anchor='w')
        lang_menu = ctk.CTkOptionMenu(header, values=list(LANGUAGES.values()), width=120,
                                      command=on_language,
                                      fg_color=('gray75', 'gray30'), button_color=('gray70', 'gray25'),
                                      button_hover_color=('gray65', 'gray20'),
                                      text_color=('gray10', 'gray95'))
        lang_menu.set(LANGUAGES[get_language()])
        lang_menu.grid(row=0, column=2, sticky='ne')
        ui['lang'] = lang_menu

        # ---- Form ------------------------------------------------------
        card = ctk.CTkFrame(body, corner_radius=14)
        card.grid(row=1, column=0, sticky='ew', padx=24, pady=8)
        card.grid_columnconfigure(1, weight=1)
        label_font = ctk.CTkFont(size=13, weight='bold')
        rows = (('🌍  ' + t('world'), world_var, pick_in),
                ('📁  ' + t('output'), output_var, pick_out))
        for r, (text, var, cmd) in enumerate(rows):
            top = 16 if r == 0 else 8
            ctk.CTkLabel(card, text=text, font=label_font).grid(row=r, column=0, sticky='w', padx=(18, 10), pady=(top, 0))
            ctk.CTkEntry(card, textvariable=var, height=36).grid(row=r, column=1, sticky='ew', pady=(top, 0))
            ctk.CTkButton(card, text=t('browse'), width=100, height=36, command=cmd,
                          fg_color=('gray75', 'gray30'), hover_color=('gray65', 'gray25'),
                          text_color=('gray10', 'gray95')).grid(row=r, column=2, padx=(10, 18), pady=(top, 0))

        ctk.CTkLabel(card, text='✂️  ' + t('margin'), font=label_font).grid(
            row=2, column=0, sticky='w', padx=(18, 10), pady=(14, 16))
        margin_row = ctk.CTkFrame(card, fg_color='transparent')
        margin_row.grid(row=2, column=1, columnspan=2, sticky='ew', padx=(0, 18), pady=(14, 16))
        margin_row.grid_columnconfigure(0, weight=1)
        margin_value = ctk.CTkLabel(margin_row, text=chunks_label(margin_var.get()), width=90)

        def on_slide(v):
            margin_var.set(int(round(float(v))))
            margin_value.configure(text=chunks_label(margin_var.get()))

        slider = ctk.CTkSlider(margin_row, from_=0, to=8, number_of_steps=8, command=on_slide)
        slider.set(margin_var.get())
        slider.grid(row=0, column=0, sticky='ew')
        margin_value.grid(row=0, column=1, padx=(10, 0))
        ui['slider'] = slider

        # ---- Actions and progress -------------------------------------
        actions = ctk.CTkFrame(body, fg_color='transparent')
        actions.grid(row=2, column=0, sticky='ew', padx=24, pady=(8, 4))
        actions.grid_columnconfigure(2, weight=1)
        bold = ctk.CTkFont(size=14, weight='bold')
        ui['analyze'] = ctk.CTkButton(actions, text='🔍  ' + t('analyze'), width=140, height=40,
                                      fg_color='transparent', border_width=2,
                                      text_color=('gray10', 'gray95'), font=bold, command=do_analyze)
        ui['trim'] = ctk.CTkButton(actions, text='✂️  ' + t('trim'), width=160, height=40,
                                   font=bold, command=do_trim)
        ui['analyze'].grid(row=0, column=0)
        ui['trim'].grid(row=0, column=1, padx=(10, 0))
        ui['status'] = ctk.CTkLabel(actions, text=t('ready'), text_color=('gray35', 'gray65'), anchor='e')
        ui['status'].grid(row=0, column=2, sticky='e')
        ui['bar'] = ctk.CTkProgressBar(actions, height=10)
        ui['bar'].set(0)
        ui['bar'].grid(row=1, column=0, columnspan=3, sticky='ew', pady=(12, 0))

        # ---- Log -------------------------------------------------------
        ui['log'] = ctk.CTkTextbox(body, font=MONO, corner_radius=12, wrap='none')
        ui['log'].grid(row=3, column=0, sticky='nsew', padx=24, pady=(8, 20))
        ui['log'].insert('end', t('intro') + '\n')
        ui['log'].configure(state='disabled')

    # ---- Logic ---------------------------------------------------------
    def log(text):
        msgs.put(('log', text))

    def progress(f):
        msgs.put(('progress', f))

    def set_busy(busy, text):
        state['busy'] = busy
        s = 'disabled' if busy else 'normal'
        for key in ('analyze', 'trim', 'slider', 'lang'):
            ui[key].configure(state=s)
        ui['status'].configure(text=text)

    def pump():
        try:
            while True:
                kind, value = msgs.get_nowait()
                if kind == 'log':
                    ui['log'].configure(state='normal')
                    ui['log'].insert('end', value + '\n')
                    ui['log'].see('end')
                    ui['log'].configure(state='disabled')
                elif kind == 'progress':
                    ui['bar'].set(value)
                    ui['status'].configure(text=f'{value * 100:.0f}%')
                elif kind == 'done':
                    set_busy(False, t(value))
        except queue.Empty:
            pass
        root.after(80, pump)

    def run(job, busy_key, done_key):
        set_busy(True, t(busy_key))
        ui['bar'].set(0)
        ui['log'].configure(state='normal')
        ui['log'].delete('1.0', 'end')
        ui['log'].configure(state='disabled')

        def worker():
            result = done_key
            try:
                job()
            except Exception as e:  # show any failure in the window
                log(f'ERROR: {e}')
                result = 'status_error'
            msgs.put(('done', result))
        threading.Thread(target=worker, daemon=True).start()

    def do_analyze():
        w = world_var.get().strip()
        err = validate(w)
        if err:
            messagebox.showerror(APP_TITLE, err)
            return
        m = margin_var.get()

        def job():
            log(t('log_analyzing'))
            print_plan(plan(w, m, progress), m, log)
            log(t('size_now', mb=f'{folder_size_mb(w):,.1f}'))
        run(job, 'status_analyzing', 'status_analyzed')

    def do_trim():
        w = world_var.get().strip()
        d = output_var.get().strip()
        err = validate(w, d)
        if err:
            messagebox.showerror(APP_TITLE, err)
            return
        if not messagebox.askokcancel(APP_TITLE, t('confirm', dest=d)):
            return
        m = margin_var.get()
        run(lambda: trim(w, d, m, os.path.basename(d), log, progress),
            'status_trimming', 'status_trimmed')

    build()
    pump()
    root.mainloop()


def gui_classic():
    """Plain Tkinter window, used when CustomTkinter is not installed."""
    import queue
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext

    root = tk.Tk()
    root.title(APP_TITLE)
    root.minsize(640, 420)
    apply_icon(root)

    world_var = tk.StringVar()
    output_var = tk.StringVar()
    margin_var = tk.IntVar(value=3)
    lang_var = tk.StringVar(value=LANGUAGES[get_language()])
    msgs = queue.Queue()

    def pick_in():
        d = filedialog.askdirectory(title=t('pick_world'))
        if d:
            world_var.set(os.path.normpath(d))
            output_var.set(default_dest(os.path.normpath(d)))

    def pick_out():
        d = filedialog.askdirectory(title=t('pick_output'))
        if d:
            base = os.path.basename(world_var.get()) if world_var.get() else t('world')
            output_var.set(os.path.join(os.path.normpath(d), base + ' (Realms)'))

    frm = tk.Frame(root, padx=12, pady=12)
    frm.pack(fill='both', expand=True)
    frm.columnconfigure(1, weight=1)
    frm.rowconfigure(4, weight=1)
    widgets = {}

    def build():
        for w in frm.winfo_children():
            w.destroy()
        tk.Label(frm, text=t('world') + ':').grid(row=0, column=0, sticky='w')
        tk.Entry(frm, textvariable=world_var).grid(row=0, column=1, sticky='ew', padx=6)
        tk.Button(frm, text=t('browse') + '…', command=pick_in).grid(row=0, column=2)
        tk.OptionMenu(frm, lang_var, *LANGUAGES.values(), command=on_language).grid(row=0, column=3, padx=(6, 0))

        tk.Label(frm, text=t('output') + ':').grid(row=1, column=0, sticky='w', pady=6)
        tk.Entry(frm, textvariable=output_var).grid(row=1, column=1, sticky='ew', padx=6)
        tk.Button(frm, text=t('browse') + '…', command=pick_out).grid(row=1, column=2)

        tk.Label(frm, text=t('margin') + ':').grid(row=2, column=0, sticky='w')
        tk.Spinbox(frm, from_=0, to=16, width=5, textvariable=margin_var).grid(row=2, column=1, sticky='w', padx=6)

        btns = tk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=4, sticky='w', pady=8)
        tk.Button(btns, text=t('analyze'), width=12, command=do_analyze).pack(side='left')
        tk.Button(btns, text=t('trim'), width=12, command=do_trim).pack(side='left', padx=8)
        widgets['btns'] = btns

        log_box = scrolledtext.ScrolledText(frm, height=14, font=('Consolas', 9))
        log_box.grid(row=4, column=0, columnspan=4, sticky='nsew')
        log_box.insert('end', t('intro') + '\n')
        log_box.config(state='disabled')
        widgets['log'] = log_box

    def on_language(name):
        code = next(c for c, n in LANGUAGES.items() if n == name)
        set_language(code)
        save_settings(lang=code)
        build()

    def log(text):
        msgs.put(text)

    def pump():
        while not msgs.empty():
            item = msgs.get()
            if item is None:
                for b in widgets['btns'].winfo_children():
                    b.config(state='normal')
                continue
            widgets['log'].config(state='normal')
            widgets['log'].insert('end', item + '\n')
            widgets['log'].see('end')
            widgets['log'].config(state='disabled')
        root.after(100, pump)

    def run(job):
        for b in widgets['btns'].winfo_children():
            b.config(state='disabled')
        widgets['log'].config(state='normal')
        widgets['log'].delete('1.0', 'end')
        widgets['log'].config(state='disabled')

        def worker():
            try:
                job()
            except Exception as e:  # show any failure in the window
                log(f'ERROR: {e}')
            finally:
                msgs.put(None)
        threading.Thread(target=worker, daemon=True).start()

    def get_margin():
        try:
            m = int(margin_var.get())
        except (tk.TclError, ValueError):
            m = -1
        if m < 0:
            messagebox.showerror(APP_TITLE, t('err_margin'))
            return None
        return m

    def do_analyze():
        w = world_var.get().strip()
        err = validate(w)
        if err:
            messagebox.showerror(APP_TITLE, err)
            return
        m = get_margin()
        if m is None:
            return

        def job():
            log(t('log_analyzing'))
            print_plan(plan(w, m), m, log)
            log(t('size_now', mb=f'{folder_size_mb(w):,.1f}'))
        run(job)

    def do_trim():
        w = world_var.get().strip()
        d = output_var.get().strip()
        err = validate(w, d)
        if err:
            messagebox.showerror(APP_TITLE, err)
            return
        m = get_margin()
        if m is None:
            return
        if not messagebox.askokcancel(APP_TITLE, t('confirm', dest=d)):
            return
        run(lambda: trim(w, d, m, os.path.basename(d), log))

    build()
    pump()
    root.mainloop()


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def cli(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    # Pick the language first so --help is shown in it
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument('--lang', choices=list(LANGUAGES))
    known, _ = pre.parse_known_args(argv)
    set_language(known.lang or load_settings().get('lang', DEFAULT_LANG))

    p = argparse.ArgumentParser(prog='realms-trimmer', description=t('cli_desc'))
    p.add_argument('input', help=t('cli_input'))
    p.add_argument('output', nargs='?', help=t('cli_output'))
    p.add_argument('--margin', '--margen', dest='margin', type=int, default=3, help=t('cli_margin'))
    p.add_argument('--name', '--nombre', dest='name', help=t('cli_name'))
    p.add_argument('--analyze', '--analizar', dest='analyze', action='store_true', help=t('cli_analyze'))
    p.add_argument('--lang', choices=list(LANGUAGES), help=t('cli_lang'))
    args = p.parse_args(argv)

    world = os.path.abspath(args.input)
    if args.margin < 0:
        sys.exit('Error: ' + t('err_margin'))

    if args.analyze:
        err = validate(world)
        if err:
            sys.exit('Error: ' + err)
        print_plan(plan(world, args.margin), args.margin)
        print(t('size_now', mb=f'{folder_size_mb(world):,.1f}'))
        return

    dest = os.path.abspath(args.output) if args.output else default_dest(world)
    err = validate(world, dest)
    if err:
        sys.exit('Error: ' + err)
    trim(world, dest, args.margin, args.name or os.path.basename(dest))


if __name__ == '__main__':
    if len(sys.argv) > 1:
        cli()
    else:
        gui()
