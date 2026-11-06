"""realms-trimmer: recorta mundos de Minecraft para que Realms los acepte.

Quita los chunks que ningún jugador ha visitado (por ejemplo, los que genera
Chunky por adelantado) y deja un margen alrededor de las zonas visitadas.
Nunca modifica el mundo original: siempre trabaja sobre una copia.

Uso:
    Doble clic en el archivo           -> abre una ventana para elegir las carpetas.
    python realms_trimmer.py ENTRADA [SALIDA] [--margen 3] [--nombre NOMBRE]
    python realms_trimmer.py ENTRADA --analizar
"""
import argparse
import gzip
import os
import shutil
import struct
import sys
import zlib

SECTOR = 4096
APP_TITLE = '✂️ Realms Trimmer'
INHABITED_TAG = b'\x04\x00\x0dInhabitedTime'


# --------------------------------------------------------------------------
# Lectura y escritura de archivos de región (.mca)
# --------------------------------------------------------------------------

def read_region(path):
    """Devuelve {indice: (payload, timestamp)} con los chunks del archivo."""
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
    raise ValueError(f'compresión no soportada: {comp}')


def inhabited_ticks(payload):
    """Ticks que los jugadores han pasado en el chunk. None si no se puede leer."""
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
# Localizar dimensiones (formato nuevo "dimensions/" y formato clásico)
# --------------------------------------------------------------------------

def find_dimensions(world):
    """Devuelve {nombre: carpeta} de cada dimensión que tenga carpeta region."""
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
# Análisis
# --------------------------------------------------------------------------

def scan_dimension(dim_dir, tick=None):
    """Devuelve (todos_los_chunks, chunks_visitados, chunks_ilegibles)."""
    all_chunks, visited, unreadable = set(), set(), 0
    region_dir = os.path.join(dim_dir, 'region')
    for fn in mca_files(region_dir):
        if tick:
            tick()
        rx, rz = region_coords(fn)
        for i, (payload, _) in read_region(os.path.join(region_dir, fn)).items():
            c = chunk_coords(rx, rz, i)
            all_chunks.add(c)
            t = inhabited_ticks(payload)
            if t is None:
                unreadable += 1
                visited.add(c)  # ante la duda, se conserva
            elif t > 0:
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
    """Reparte una barra 0..1 entre pasos; llama a callback(fracción)."""

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
    log(f'{"Dimensión":<28}{"Total":>10}{"Visitados":>11}{"Se quedan":>11}')
    for name, (_, all_chunks, visited, keep, unreadable) in result.items():
        log(f'{name:<28}{len(all_chunks):>10}{len(visited):>11}{len(keep):>11}')
        if unreadable:
            log(f'  ({unreadable} chunks no se pudieron leer; se conservan)')
        total_all += len(all_chunks)
        total_keep += len(keep)
    log(f'{"TOTAL":<28}{total_all:>10}{"":>11}{total_keep:>11}')
    if total_all:
        log(f'Se conserva el {100 * total_keep / total_all:.0f}% de los chunks (margen = {margin}).')


# --------------------------------------------------------------------------
# Recorte
# --------------------------------------------------------------------------

def rename_level(level_dat, new_name):
    with open(level_dat, 'rb') as f:
        d = gzip.decompress(f.read())
    tag = b'\x08\x00\x09LevelName'
    i = d.find(tag)
    if i < 0:
        print('Aviso: no se encontró LevelName en level.dat; no se cambia el nombre.')
        return
    i += len(tag)
    n = int.from_bytes(d[i:i+2], 'big')
    new = new_name.encode('utf-8')
    d = d[:i] + len(new).to_bytes(2, 'big') + new + d[i+2+n:]
    with open(level_dat, 'wb') as f:
        f.write(gzip.compress(d))


def trim(world, dest, margin, new_name, log=print, progress=None):
    log('Analizando chunks...')
    result = plan(world, margin, progress, 0.0, 0.45)
    print_plan(result, margin, log)

    log(f'\nCopiando mundo a: {dest}')
    shutil.copytree(world, dest, ignore=shutil.ignore_patterns('session.lock', 'realms-upload.log'))
    if progress:
        progress(0.6)

    log('Recortando regiones...')
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
        rename_level(level_dat, new_name)
        old = os.path.join(dest, 'level.dat_old')
        if os.path.isfile(old):
            os.remove(old)

    log(f'\nTamaño original: {folder_size_mb(world):,.1f} MB')
    log(f'Tamaño recortado: {folder_size_mb(dest):,.1f} MB')
    log(f'Listo. Sube a Realms el mundo "{new_name}" sin abrirlo antes en un jugador.')
    if progress:
        progress(1.0)


# --------------------------------------------------------------------------
# Validación común
# --------------------------------------------------------------------------

def validate(world, dest=None):
    """Devuelve un mensaje de error, o None si todo está bien."""
    if not world or not os.path.isfile(os.path.join(world, 'level.dat')):
        return f'"{world}" no parece un mundo de Minecraft (falta level.dat).'
    if not find_dimensions(world):
        return 'No se encontró ninguna carpeta "region" en el mundo.'
    if dest is not None:
        if not dest:
            return 'Elige una carpeta de salida.'
        if os.path.exists(dest):
            return f'Ya existe "{dest}". Bórrala o elige otra carpeta de salida.'
        w = os.path.normcase(os.path.abspath(world))
        d = os.path.normcase(os.path.abspath(dest))
        if d == w or d.startswith(w + os.sep):
            return 'La carpeta de salida no puede estar dentro del mundo original.'
    return None


def default_dest(world):
    return world.rstrip('\\/') + ' (Realms)'


# --------------------------------------------------------------------------
# Ventana (doble clic)
# --------------------------------------------------------------------------

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
ICON_ICO = os.path.join(ASSETS, 'icon.ico')
ICON_PNG = os.path.join(ASSETS, 'icon.png')


def apply_icon(root):
    """Pone el icono en la ventana y en la barra de tareas (si existe)."""
    if sys.platform == 'win32':
        try:  # que Windows agrupe la ventana con nuestro icono y no con el de Python
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
    # CustomTkinter vuelve a poner su icono al arrancar; lo reponemos después
    root.after(250, lambda: apply_icon(root))

    entrada = ctk.StringVar()
    salida = ctk.StringVar()
    margen = ctk.IntVar(value=3)
    msgs = queue.Queue()
    MONO = ('Consolas', 12) if sys.platform == 'win32' else ('Menlo', 12)

    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(3, weight=1)

    # ---- Cabecera -------------------------------------------------------
    header = ctk.CTkFrame(root, fg_color='transparent')
    header.grid(row=0, column=0, sticky='ew', padx=24, pady=(20, 8))
    logo = None
    try:
        from PIL import Image
        if os.path.isfile(ICON_PNG):
            logo = ctk.CTkImage(Image.open(ICON_PNG), size=(56, 56))
    except Exception:
        logo = None
    if logo:
        ctk.CTkLabel(header, image=logo, text='').pack(side='left', padx=(0, 14))
    titles = ctk.CTkFrame(header, fg_color='transparent')
    titles.pack(side='left')
    ctk.CTkLabel(titles, text='Realms Trimmer', font=ctk.CTkFont(size=26, weight='bold')).pack(anchor='w')
    ctk.CTkLabel(titles, text='Recorta tu mundo para subirlo a Realms sin "timed out"',
                 text_color=('gray35', 'gray65'), font=ctk.CTkFont(size=13)).pack(anchor='w')

    # ---- Formulario ------------------------------------------------------
    card = ctk.CTkFrame(root, corner_radius=14)
    card.grid(row=1, column=0, sticky='ew', padx=24, pady=8)
    card.grid_columnconfigure(1, weight=1)

    def pick_in():
        d = filedialog.askdirectory(title='Elige la carpeta de tu mundo')
        if d:
            entrada.set(os.path.normpath(d))
            salida.set(default_dest(os.path.normpath(d)))

    def pick_out():
        d = filedialog.askdirectory(title='Elige dónde guardar la copia')
        if d:
            name = os.path.basename(entrada.get()) + ' (Realms)' if entrada.get() else 'Mundo (Realms)'
            salida.set(os.path.join(os.path.normpath(d), name))

    label_font = ctk.CTkFont(size=13, weight='bold')
    rows = (('🌍  Mundo', entrada, pick_in, 'Carpeta del mundo en .minecraft/saves'),
            ('📁  Copia', salida, pick_out, 'Dónde se crea la copia recortada'))
    for r, (text, var, cmd, hint) in enumerate(rows):
        ctk.CTkLabel(card, text=text, font=label_font).grid(row=r, column=0, sticky='w', padx=(18, 10), pady=(16 if r == 0 else 8, 0))
        ctk.CTkEntry(card, textvariable=var, height=36, placeholder_text=hint).grid(
            row=r, column=1, sticky='ew', pady=(16 if r == 0 else 8, 0))
        ctk.CTkButton(card, text='Examinar', width=100, height=36, command=cmd,
                      fg_color=('gray75', 'gray30'), hover_color=('gray65', 'gray25'),
                      text_color=('gray10', 'gray95')).grid(
            row=r, column=2, padx=(10, 18), pady=(16 if r == 0 else 8, 0))

    ctk.CTkLabel(card, text='✂️  Margen', font=label_font).grid(row=2, column=0, sticky='w', padx=(18, 10), pady=(14, 16))
    margin_row = ctk.CTkFrame(card, fg_color='transparent')
    margin_row.grid(row=2, column=1, columnspan=2, sticky='ew', padx=(0, 18), pady=(14, 16))
    margin_row.grid_columnconfigure(0, weight=1)
    margin_value = ctk.CTkLabel(margin_row, text='3 chunks', width=80)

    def on_slide(v):
        margen.set(int(round(float(v))))
        margin_value.configure(text=f'{margen.get()} chunk' + ('' if margen.get() == 1 else 's'))

    slider = ctk.CTkSlider(margin_row, from_=0, to=8, number_of_steps=8, command=on_slide)
    slider.set(3)
    slider.grid(row=0, column=0, sticky='ew')
    margin_value.grid(row=0, column=1, padx=(10, 0))

    # ---- Acciones y progreso --------------------------------------------
    actions = ctk.CTkFrame(root, fg_color='transparent')
    actions.grid(row=2, column=0, sticky='ew', padx=24, pady=(8, 4))
    actions.grid_columnconfigure(2, weight=1)
    btn_analyze = ctk.CTkButton(actions, text='🔍  Analizar', width=140, height=40,
                                fg_color='transparent', border_width=2,
                                text_color=('gray10', 'gray95'),
                                font=ctk.CTkFont(size=14, weight='bold'))
    btn_trim = ctk.CTkButton(actions, text='✂️  Recortar', width=160, height=40,
                             font=ctk.CTkFont(size=14, weight='bold'))
    btn_analyze.grid(row=0, column=0)
    btn_trim.grid(row=0, column=1, padx=(10, 0))
    status = ctk.CTkLabel(actions, text='Listo', text_color=('gray35', 'gray65'), anchor='e')
    status.grid(row=0, column=2, sticky='e')
    bar = ctk.CTkProgressBar(actions, height=10)
    bar.set(0)
    bar.grid(row=1, column=0, columnspan=3, sticky='ew', pady=(12, 0))

    # ---- Registro --------------------------------------------------------
    log_box = ctk.CTkTextbox(root, font=MONO, corner_radius=12, wrap='none')
    log_box.grid(row=3, column=0, sticky='nsew', padx=24, pady=(8, 20))
    log_box.insert('end', '1. Cierra Minecraft.\n2. Elige tu mundo.\n3. Pulsa Analizar para ver cuánto se recorta, '
                          'o Recortar para crear la copia.\n')
    log_box.configure(state='disabled')

    # ---- Lógica ----------------------------------------------------------
    def log(text):
        msgs.put(('log', text))

    def progress(f):
        msgs.put(('progress', f))

    def set_busy(busy, text):
        state = 'disabled' if busy else 'normal'
        btn_analyze.configure(state=state)
        btn_trim.configure(state=state)
        slider.configure(state=state)
        status.configure(text=text)

    def pump():
        try:
            while True:
                kind, value = msgs.get_nowait()
                if kind == 'log':
                    log_box.configure(state='normal')
                    log_box.insert('end', value + '\n')
                    log_box.see('end')
                    log_box.configure(state='disabled')
                elif kind == 'progress':
                    bar.set(value)
                    status.configure(text=f'{value * 100:.0f}%')
                elif kind == 'done':
                    set_busy(False, value)
        except queue.Empty:
            pass
        root.after(80, pump)

    def run(job, busy_text, done_text):
        set_busy(True, busy_text)
        bar.set(0)
        log_box.configure(state='normal')
        log_box.delete('1.0', 'end')
        log_box.configure(state='disabled')

        def worker():
            result = done_text
            try:
                job()
            except Exception as e:  # mostrar cualquier fallo en la ventana
                log(f'ERROR: {e}')
                result = '❌ Error'
            msgs.put(('done', result))
        threading.Thread(target=worker, daemon=True).start()

    def do_analyze():
        w = entrada.get().strip()
        err = validate(w)
        if err:
            messagebox.showerror(APP_TITLE, err)
            return
        m = margen.get()

        def job():
            log('Analizando chunks...')
            print_plan(plan(w, m, progress), m, log)
            log(f'Tamaño actual: {folder_size_mb(w):,.1f} MB')
        run(job, 'Analizando...', '✅ Análisis terminado')

    def do_trim():
        w = entrada.get().strip()
        d = salida.get().strip()
        err = validate(w, d)
        if err:
            messagebox.showerror(APP_TITLE, err)
            return
        if not messagebox.askokcancel(APP_TITLE,
                                      'Asegúrate de que Minecraft está cerrado.\n\n'
                                      f'Se creará una copia recortada en:\n{d}\n\n'
                                      'El mundo original no se modifica.'):
            return
        m = margen.get()
        run(lambda: trim(w, d, m, os.path.basename(d), log, progress),
            'Recortando...', '✅ Copia creada')

    btn_analyze.configure(command=do_analyze)
    btn_trim.configure(command=do_trim)

    pump()
    root.mainloop()


def gui_classic():
    import queue
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext

    root = tk.Tk()
    root.title(APP_TITLE)
    root.minsize(640, 420)
    apply_icon(root)

    entrada = tk.StringVar()
    salida = tk.StringVar()
    margen = tk.IntVar(value=3)
    msgs = queue.Queue()

    def pick_in():
        d = filedialog.askdirectory(title='Elige la carpeta de tu mundo')
        if d:
            entrada.set(os.path.normpath(d))
            if not salida.get():
                salida.set(default_dest(os.path.normpath(d)))

    def pick_out():
        d = filedialog.askdirectory(title='Elige dónde guardar la copia')
        if d:
            name = os.path.basename(entrada.get()) + ' (Realms)' if entrada.get() else 'Mundo (Realms)'
            salida.set(os.path.join(os.path.normpath(d), name))

    frm = tk.Frame(root, padx=12, pady=12)
    frm.pack(fill='both', expand=True)
    frm.columnconfigure(1, weight=1)

    tk.Label(frm, text='Mundo (entrada):').grid(row=0, column=0, sticky='w')
    tk.Entry(frm, textvariable=entrada).grid(row=0, column=1, sticky='ew', padx=6)
    tk.Button(frm, text='Examinar…', command=pick_in).grid(row=0, column=2)

    tk.Label(frm, text='Copia (salida):').grid(row=1, column=0, sticky='w', pady=6)
    tk.Entry(frm, textvariable=salida).grid(row=1, column=1, sticky='ew', padx=6)
    tk.Button(frm, text='Examinar…', command=pick_out).grid(row=1, column=2)

    tk.Label(frm, text='Margen (chunks):').grid(row=2, column=0, sticky='w')
    tk.Spinbox(frm, from_=0, to=16, width=5, textvariable=margen).grid(row=2, column=1, sticky='w', padx=6)

    btns = tk.Frame(frm)
    btns.grid(row=3, column=0, columnspan=3, sticky='w', pady=8)
    log_box = scrolledtext.ScrolledText(frm, height=14, font=('Consolas', 9), state='disabled')
    log_box.grid(row=4, column=0, columnspan=3, sticky='nsew')
    frm.rowconfigure(4, weight=1)

    def log(text):
        msgs.put(text)

    def pump():
        while not msgs.empty():
            item = msgs.get()
            if item is None:
                for b in btns.winfo_children():
                    b.config(state='normal')
                continue
            log_box.config(state='normal')
            log_box.insert('end', item + '\n')
            log_box.see('end')
            log_box.config(state='disabled')
        root.after(100, pump)

    def run(job):
        for b in btns.winfo_children():
            b.config(state='disabled')
        log_box.config(state='normal')
        log_box.delete('1.0', 'end')
        log_box.config(state='disabled')

        def worker():
            try:
                job()
            except Exception as e:  # mostrar cualquier fallo en la ventana
                log(f'ERROR: {e}')
            finally:
                msgs.put(None)
        threading.Thread(target=worker, daemon=True).start()

    def get_margin():
        try:
            m = int(margen.get())
        except (tk.TclError, ValueError):
            m = -1
        if m < 0:
            messagebox.showerror(APP_TITLE, 'El margen tiene que ser un número de 0 en adelante.')
            return None
        return m

    def do_analyze():
        w = entrada.get().strip()
        err = validate(w)
        m = get_margin()
        if err:
            messagebox.showerror(APP_TITLE, err)
            return
        if m is None:
            return

        def job():
            log('Analizando chunks...')
            print_plan(plan(w, m), m, log)
            log(f'Tamaño actual: {folder_size_mb(w):,.1f} MB')
        run(job)

    def do_trim():
        w = entrada.get().strip()
        d = salida.get().strip()
        err = validate(w, d)
        m = get_margin()
        if err:
            messagebox.showerror(APP_TITLE, err)
            return
        if m is None:
            return
        if not messagebox.askokcancel(APP_TITLE,
                                      'Asegúrate de que Minecraft está cerrado.\n\n'
                                      f'Se creará una copia recortada en:\n{d}\n\n'
                                      'El mundo original no se modifica.'):
            return
        run(lambda: trim(w, d, m, os.path.basename(d), log))

    tk.Button(btns, text='Analizar', width=12, command=do_analyze).pack(side='left')
    tk.Button(btns, text='Recortar', width=12, command=do_trim).pack(side='left', padx=8)

    pump()
    root.mainloop()


# --------------------------------------------------------------------------
# Terminal
# --------------------------------------------------------------------------

def cli():
    p = argparse.ArgumentParser(
        prog='realms-trimmer',
        description='Crea una copia de un mundo de Minecraft sin los chunks no visitados, '
                    'para subirla a Realms. Sin argumentos abre la ventana.')
    p.add_argument('entrada', help='Carpeta del mundo.')
    p.add_argument('salida', nargs='?',
                   help='Carpeta donde se crea la copia (por defecto "<entrada> (Realms)").')
    p.add_argument('--margen', type=int, default=3,
                   help='Chunks de margen alrededor de las zonas visitadas (por defecto 3).')
    p.add_argument('--nombre', help='Nombre del mundo en el juego (por defecto el de la carpeta de salida).')
    p.add_argument('--analizar', action='store_true',
                   help='Solo muestra cuánto se recortaría, sin crear nada.')
    args = p.parse_args()

    world = os.path.abspath(args.entrada)
    if args.margen < 0:
        sys.exit('Error: el margen no puede ser negativo.')

    if args.analizar:
        err = validate(world)
        if err:
            sys.exit('Error: ' + err)
        print_plan(plan(world, args.margen), args.margen)
        print(f'Tamaño actual: {folder_size_mb(world):,.1f} MB')
        return

    dest = os.path.abspath(args.salida) if args.salida else default_dest(world)
    err = validate(world, dest)
    if err:
        sys.exit('Error: ' + err)
    trim(world, dest, args.margen, args.nombre or os.path.basename(dest))


if __name__ == '__main__':
    if len(sys.argv) > 1:
        cli()
    else:
        gui()
