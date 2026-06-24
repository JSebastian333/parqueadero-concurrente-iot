import socket
import json
import os
import threading
import datetime
import tkinter as tk
from tkinter import messagebox

# C
HOST         = '0.0.0.0'
PORT         = 65432
AFORO_MAXIMO = 40
ARCHIVO_DB   = "parqueadero.json"
TARIFA_MIN   = 50

# Colores
BG      = "#f0f2f8"
CARD    = "#ffffff"
ACCENT1 = "#1a237e"
ACCENT2 = "#283593"
ACCENT3 = "#3949ab"
ACCENT4 = "#5c6bc0"
LIGHT1  = "#e8eaf6"
LIGHT2  = "#c5cae9"
TEXT1   = "#1a237e"
TEXT2   = "#3949ab"
TEXTG   = "#78909c"
FREE_C  = "#00c853"
FREE_BG = "#e8f5e9"
OCC_C   = "#e53935"
OCC_BG  = "#ffebee"
NAV_BG  = "#1a237e"

#Sincronizar
lock_json         = threading.Lock()
evento_entrada    = threading.Event()
evento_salida     = threading.Event()
EMERGENCIA_ACTIVA = False
conexion_entrada  = None
respuesta_entrada = None
conexion_salida   = None
respuesta_salida  = None

# JSON
def inicializar_db():
    if not os.path.exists(ARCHIVO_DB):
        _crear_db(); return
    try:
        with open(ARCHIVO_DB, 'r', encoding='utf-8') as f:
            c = json.load(f)
        if "mapa_puestos" not in c or "vehiculos_actuales" not in c:
            _crear_db()
    except Exception:
        _crear_db()

def _crear_db():
    datos = {"puestos_ocupados": 0, "vehiculos_actuales": [],
             "mapa_puestos": {str(i): None for i in range(1, AFORO_MAXIMO + 1)}}
    with open(ARCHIVO_DB, 'w', encoding='utf-8') as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)

def leer_db():
    with open(ARCHIVO_DB, 'r', encoding='utf-8') as f:
        return json.load(f)

def guardar_db(db):
    with open(ARCHIVO_DB, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=4, ensure_ascii=False)

def procesar_ingreso():
    global conexion_entrada, respuesta_entrada
    if conexion_entrada is None:
        messagebox.showinfo("Sistema", "No hay vehículo esperando en el sensor de entrada.")
        return
    placa  = var_placa_in.get().strip().upper()
    puesto = var_puesto_in.get().strip()
    with lock_json:
        db = leer_db()
        if db["puestos_ocupados"] >= AFORO_MAXIMO:
            respuesta_entrada = {"estado": "denegado", "mensaje": "Parqueadero lleno"}
            agregar_log("DENEGADO — Aforo completo", "deny")
            evento_entrada.set(); return
        asignado = None
        if puesto:
            if puesto in db["mapa_puestos"]:
                if db["mapa_puestos"][puesto] is None:
                    asignado = puesto
                else:
                    messagebox.showerror("Error", f"El puesto {puesto} ya está ocupado."); return
            else:
                messagebox.showerror("Error", f"Puesto inválido (1–{AFORO_MAXIMO})."); return
        else:
            for i in range(1, AFORO_MAXIMO + 1):
                if db["mapa_puestos"][str(i)] is None:
                    asignado = str(i); break
        if not asignado:
            messagebox.showerror("Error", "Sin puestos libres."); return
        if not placa:
            placa = f"EAN-{100 + int(asignado)}"
        ahora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db["mapa_puestos"][asignado] = {"placa": placa, "hora_entrada": ahora}
        if placa not in db["vehiculos_actuales"]:
            db["vehiculos_actuales"].append(placa)
        db["puestos_ocupados"] = sum(1 for p in db["mapa_puestos"].values() if p)
        libres = AFORO_MAXIMO - db["puestos_ocupados"]
        respuesta_entrada = {"estado": "autorizado",
                             "mensaje": f"Puesto {asignado} asignado",
                             "puestos_libres": libres}
        guardar_db(db)
    agregar_log(f"INGRESO — {placa} → P{asignado} · Libres: {libres}", "in")
    var_placa_in.set(""); var_puesto_in.set("")
    _reset_panel_entrada()
    actualizar_ui()
    evento_entrada.set()

def procesar_salida():
    global conexion_salida, respuesta_salida
    if conexion_salida is None:
        messagebox.showinfo("Sistema", "No hay vehículo esperando en el sensor de salida.")
        return
    placa = var_placa_out.get().strip().upper()
    if not placa:
        messagebox.showerror("Error", "Ingrese la placa del vehículo."); return
    with lock_json:
        db = leer_db()
        puesto_encontrado = None; datos_v = None
        for p, d in db["mapa_puestos"].items():
            if d and d["placa"] == placa:
                puesto_encontrado = p; datos_v = d; break
        if not puesto_encontrado:
            messagebox.showerror("Error", f"Placa {placa} no encontrada."); return
        entrada_dt = datetime.datetime.strptime(datos_v["hora_entrada"], "%Y-%m-%d %H:%M:%S")
        mins  = max(1, int((datetime.datetime.now() - entrada_dt).total_seconds() // 60))
        total = mins * TARIFA_MIN
        messagebox.showinfo("Factura",
            f"Placa:    {placa}\n"
            f"Puesto:   {puesto_encontrado}\n"
            f"Tiempo:   {mins} min\n"
            f"Tarifa:   ${TARIFA_MIN}/min\n"
            f"─────────────────────\n"
            f"TOTAL:    ${total:,} COP")
        db["mapa_puestos"][puesto_encontrado] = None
        if placa in db["vehiculos_actuales"]:
            db["vehiculos_actuales"].remove(placa)
        db["puestos_ocupados"] = sum(1 for p in db["mapa_puestos"].values() if p)
        libres = AFORO_MAXIMO - db["puestos_ocupados"]
        respuesta_salida = {"estado": "autorizado",
                            "mensaje": f"Salida ok. Recaudo: ${total}",
                            "puestos_libres": libres}
        guardar_db(db)
    agregar_log(f"SALIDA — {placa} liberó P{puesto_encontrado} · ${total:,} COP", "out")
    var_placa_out.set("")
    _reset_panel_salida()
    actualizar_ui()
    evento_salida.set()

# TCP
def servidor_tcp():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT)); srv.listen()
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=manejar_cliente, args=(conn,), daemon=True).start()

def manejar_cliente(conn):
    global conexion_entrada, respuesta_entrada, evento_entrada
    global conexion_salida, respuesta_salida, evento_salida, EMERGENCIA_ACTIVA
    try:
        raw = conn.recv(1024).decode('utf-8')
        if not raw: conn.close(); return
        req    = json.loads(raw)
        accion = req.get("accion")
        if accion == "chequear_estado":
            conn.sendall(json.dumps({"estado": "emergencia" if EMERGENCIA_ACTIVA else "normal"}).encode())
            conn.close(); return
        if EMERGENCIA_ACTIVA:
            conn.sendall(json.dumps({"estado": "emergencia", "mensaje": "APERTURA FORZADA"}).encode())
            conn.close(); return
        if accion == "solicitar_ingreso":
            conexion_entrada = conn
            evento_entrada.clear()
            root.after(0, _activar_panel_entrada)
            evento_entrada.wait()
            if conexion_entrada:
                conn.sendall(json.dumps(respuesta_entrada).encode())
            conexion_entrada = None
        elif accion == "solicitar_salida":
            conexion_salida = conn
            evento_salida.clear()
            root.after(0, _activar_panel_salida)
            evento_salida.wait()
            if conexion_salida:
                conn.sendall(json.dumps(respuesta_salida).encode())
            conexion_salida = None
    except Exception as e:
        print(f"TCP error: {e}")
    finally:
        try: conn.close()
        except: pass

# ── EMERGENCIA ─────────────────────────────────────────────────────────────────
def abrir_emergencia():
    global EMERGENCIA_ACTIVA, conexion_entrada, conexion_salida
    if not messagebox.askyesno("Emergencia",
        "¿Confirmar APERTURA DE EMERGENCIA?\n\nAmbas barreras se abrirán permanentemente."): return
    EMERGENCIA_ACTIVA = True
    agregar_log("EMERGENCIA ACTIVADA — Barreras abiertas", "deny")
    msg = json.dumps({"estado": "emergencia", "mensaje": "APERTURA FORZADA"}).encode()
    for c in [conexion_entrada, conexion_salida]:
        if c:
            try: c.sendall(msg); c.close()
            except: pass
    conexion_entrada = conexion_salida = None
    evento_entrada.set(); evento_salida.set()
    btn_emerg_open.config(state=tk.DISABLED, bg="#b71c1c", fg="#ff8a80")
    btn_emerg_close.config(state=tk.NORMAL, bg="#1b5e20", fg="#b9f6ca", activebackground="#2e7d32")

def cerrar_emergencia():
    global EMERGENCIA_ACTIVA
    if not messagebox.askyesno("Emergencia",
        "¿Confirmar CIERRE DE EMERGENCIA?\n\nLas barreras volverán al modo normal."): return
    EMERGENCIA_ACTIVA = False
    agregar_log("Emergencia desactivada — Sistema normal", "in")
    btn_emerg_open.config(state=tk.NORMAL, bg="#7f1d1d", fg="#fca5a5", activebackground="#991b1b")
    btn_emerg_close.config(state=tk.DISABLED, bg=LIGHT1, fg=TEXTG, activebackground=LIGHT1)

# Act UI
slot_frames = []

def actualizar_ui():
    try:
        db = leer_db()
    except Exception:
        return
    ocupados = db["puestos_ocupados"]
    libres   = AFORO_MAXIMO - ocupados
    pct      = round(ocupados / AFORO_MAXIMO * 100)
    mapa     = db["mapa_puestos"]

    lbl_stat_occ.config(text=str(ocupados).zfill(2))
    lbl_stat_free.config(text=str(libres).zfill(2))
    lbl_stat_pct.config(text=f"{pct}%")

    ahora = datetime.datetime.now()
    for i, (card, lbl_num, lbl_placa, lbl_time) in enumerate(slot_frames):
        datos = mapa.get(str(i + 1))
        if datos:
            entrada_dt = datetime.datetime.strptime(datos["hora_entrada"], "%Y-%m-%d %H:%M:%S")
            mins = max(1, int((ahora - entrada_dt).total_seconds() // 60))
            placa_txt = datos["placa"][:7]
            card.config(bg=OCC_BG, highlightbackground=OCC_C)
            lbl_num.config(bg=OCC_BG, fg=OCC_C)
            lbl_placa.config(text=placa_txt, bg=OCC_BG, fg="#b71c1c")
            lbl_time.config(text=f"{mins}m", bg=OCC_BG, fg=TEXTG)
        else:
            card.config(bg=FREE_BG, highlightbackground=FREE_C)
            lbl_num.config(bg=FREE_BG, fg="#2e7d32")
            lbl_placa.config(text="LIBRE", bg=FREE_BG, fg=FREE_C)
            lbl_time.config(text="", bg=FREE_BG, fg=FREE_C)

def agregar_log(texto, tipo="in"):
    now    = datetime.datetime.now().strftime("%H:%M:%S")
    colors = {"in": "#1565c0", "out": "#b71c1c", "deny": "#e65100"}
    icons  = {"in": "→", "out": "←", "deny": "✕"}
    color  = colors.get(tipo, TEXT2)
    icon   = icons.get(tipo, "·")
    row = tk.Frame(frame_log_inner, bg=CARD)
    row.pack(fill=tk.X, pady=1)
    tk.Label(row, text=now, font=("Courier New", 11), fg=TEXTG,
             bg=CARD, width=8, anchor="w").pack(side=tk.LEFT)
    tk.Label(row, text=f"{icon} {texto}", font=("Segoe UI", 15),
             fg=color, bg=CARD, anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)
    tk.Frame(frame_log_inner, bg=LIGHT1, height=1).pack(fill=tk.X)


# Lujitos
TAIL_STEPS = 20          
SPEED_NEO  = 0.015       
FRAME_MS   = 30         

def _perim_pt(t, w, h):
    """t ∈ [0,1) → (x,y) en el perímetro, sentido horario."""
    perim = 2 * (w + h)
    d = (t % 1.0) * perim
    if d < w:       return d,     0
    d -= w
    if d < h:       return w,     d
    d -= h
    if d < w:       return w - d, h
    d -= w
    return 0, h - d

def _lerp_color(c1, c2, t):
    r1,g1,b1 = int(c1[1:3],16), int(c1[3:5],16), int(c1[5:7],16)
    r2,g2,b2 = int(c2[1:3],16), int(c2[3:5],16), int(c2[5:7],16)
    r = int(r1+(r2-r1)*t); g = int(g1+(g2-g1)*t); b = int(b1+(b2-b1)*t)
    return f"#{r:02x}{g:02x}{b:02x}"

class NeonBeam:
    """
    Gestiona UN rayo neón con cola sobre un canvas dado.
    Pre-crea los objetos canvas una sola vez; cada tick solo los mueve.
    """
    def __init__(self, cvs, color_bright, color_dim, offset=0.0):
        self.cvs    = cvs
        self.bright = color_bright
        self.dim    = color_dim
        self.pos    = offset
        self.segs   = []          
        self.tip    = None       
        self._build()

    def _build(self):
        cvs = self.cvs
       
        self.border = cvs.create_rectangle(3, 3, 10, 10,
                                            outline=self.dim, width=1, tags="neon")
      
        for _ in range(TAIL_STEPS):
            seg = cvs.create_line(0,0,1,1, fill=self.dim, width=1,
                                  capstyle="round", tags="neon")
            self.segs.append(seg)
        
        self.tip = cvs.create_oval(0,0,1,1, fill="white", outline="", tags="neon")

    def tick(self):
        self.pos = (self.pos + SPEED_NEO) % 1.0
        cvs = self.cvs
        w   = cvs.winfo_width()  - 1
        h   = cvs.winfo_height() - 1
        if w < 20 or h < 20:
            return
        M   = 4 
        bw  = w - 2*M
        bh  = h - 2*M

        
        cvs.coords(self.border, M, M, w-M, h-M)

        TAIL = 0.22   
        for i, seg_id in enumerate(self.segs):
            frac  = i / TAIL_STEPS
            t0    = (self.pos - TAIL * (1 - frac      )) % 1.0
            t1    = (self.pos - TAIL * (1 - (i+1)/TAIL_STEPS)) % 1.0
            x0,y0 = _perim_pt(t0, bw, bh)
            x1,y1 = _perim_pt(t1, bw, bh)
            x0+=M; y0+=M; x1+=M; y1+=M
            alpha = frac ** 0.6
            col   = _lerp_color(self.dim, self.bright, alpha)
            lw    = max(1, int(1 + 3*alpha))
            cvs.coords(seg_id, x0, y0, x1, y1)
            cvs.itemconfig(seg_id, fill=col, width=lw)

        # Punta
        xp,yp = _perim_pt(self.pos, bw, bh)
        xp+=M; yp+=M
        cvs.coords(self.tip, xp-5, yp-5, xp+5, yp+5)

    def hide(self):
        for seg in self.segs:
            cvs = self.cvs
            cvs.coords(seg, -10,-10,-9,-9)
        self.cvs.coords(self.tip, -10,-10,-9,-9)


class PanelNeon:
    """
    Administra el efecto neón de un panel completo:
    dos rayos NeonBeam a 180° de distancia.
    """
    def __init__(self, cvs, color_bright, color_dim):
        self.cvs   = cvs
        self.job   = None
        self.beam1 = NeonBeam(cvs, color_bright, color_dim, offset=0.0)
        self.beam2 = NeonBeam(cvs, color_bright, color_dim, offset=0.5)

    def start(self):
        if self.job:
            return          # ya corriendo
        self._tick()

    def _tick(self):
        self.beam1.tick()
        self.beam2.tick()
        self.job = self.cvs.after(FRAME_MS, self._tick)

    def stop(self):
        if self.job:
            self.cvs.after_cancel(self.job)
            self.job = None
        self.beam1.hide()
        self.beam2.hide()


#Resetear paneles
def _activar_panel_entrada():
    frame_panel_in.config(bg="#fff3f3")
    lbl_in_status.config(text="⚠  Vehículo en sensor — asigne placa y puesto",
                         fg="#e65100", bg="#fff3f3")
    entry_placa_in.focus_set()
    neon_in.start()

def _reset_panel_entrada():
    neon_in.stop()
    frame_panel_in.config(bg=CARD)
    lbl_in_status.config(text="Esperando vehículo...", fg=TEXTG, bg=CARD)

def _activar_panel_salida():
    frame_panel_out.config(bg="#f0fff4")
    lbl_out_status.config(text="⚠  Vehículo en sensor — ingrese la placa",
                          fg="#2e7d32", bg="#f0fff4")
    entry_placa_out.focus_set()
    neon_out.start()

def _reset_panel_salida():
    neon_out.stop()
    frame_panel_out.config(bg=CARD)
    lbl_out_status.config(text="Esperando vehículo...", fg=TEXTG, bg=CARD)

def refrescar():
    actualizar_ui()
    root.after(10000, refrescar)

#Pantalla completa
fullscreen_state = False

def toggle_fullscreen(event=None):
    global fullscreen_state
    fullscreen_state = not fullscreen_state
    root.attributes("-fullscreen", fullscreen_state)
    lbl_fs_hint.config(text="F11 salir pantalla completa" if fullscreen_state else "F11 pantalla completa")

def exit_fullscreen(event=None):
    global fullscreen_state
    fullscreen_state = False
    root.attributes("-fullscreen", False)
    lbl_fs_hint.config(text="F11 pantalla completa")

# Modo ventana
root = tk.Tk()
root.title("Sistema de Parqueadero")
root.geometry("1100x740")
root.minsize(900, 620)
root.config(bg=ACCENT2)
root.bind("<F11>",    toggle_fullscreen)
root.bind("<Escape>", exit_fullscreen)

outer = tk.Frame(root, bg=ACCENT1, padx=7, pady=7)
outer.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
mid   = tk.Frame(outer, bg=ACCENT3, padx=2, pady=2)
mid.pack(fill=tk.BOTH, expand=True)
shell = tk.Frame(mid, bg=BG)
shell.pack(fill=tk.BOTH, expand=True)

# Full
topbar = tk.Frame(shell, bg=CARD, height=48)
topbar.pack(fill=tk.X)
topbar.pack_propagate(False)

tk.Label(topbar, text="  Sistema de Parqueadero",
         font=("Segoe UI", 15, "bold"), fg=TEXT1, bg=CARD).pack(side=tk.LEFT, padx=10)

topbar_right = tk.Frame(topbar, bg=CARD)
topbar_right.pack(side=tk.RIGHT, padx=14)

lbl_fs_hint = tk.Label(topbar_right, text="F11 pantalla completa",
                        font=("Segoe UI", 12), fg=TEXTG, bg=CARD, cursor="hand2")
lbl_fs_hint.pack(side=tk.RIGHT, padx=12)
lbl_fs_hint.bind("<Button-1>", toggle_fullscreen)

for icon_txt in ["⚙", "🔔", "👤"]:
    tk.Label(topbar_right, text=icon_txt, font=("Segoe UI", 16),
             fg=ACCENT3, bg=CARD, cursor="hand2").pack(side=tk.RIGHT, padx=6)

tk.Frame(shell, bg=LIGHT2, height=1).pack(fill=tk.X)

#Main
main = tk.Frame(shell, bg=BG)
main.pack(fill=tk.BOTH, expand=True)
main.columnconfigure(0, weight=38)
main.columnconfigure(1, weight=62)
main.rowconfigure(0, weight=1)

left  = tk.Frame(main, bg=BG)
left.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=10)

tk.Frame(main, bg=LIGHT2, width=1).grid(row=0, column=0, sticky="nse")

right = tk.Frame(main, bg=BG)
right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=10)

banner = tk.Frame(left, bg=ACCENT1, padx=16, pady=12)
banner.pack(fill=tk.X, pady=(0, 10))
tk.Label(banner, text="Sistema de Parqueadero",
         font=("Segoe UI", 15, "bold"), fg="white", bg=ACCENT1).pack(anchor="w")
tk.Label(banner, text="Sistema activo — 40 puestos en línea",
         font=("Segoe UI", 15), fg="#9fa8da", bg=ACCENT1).pack(anchor="w", pady=(2, 0))


stats_row = tk.Frame(left, bg=BG)
stats_row.pack(fill=tk.X, pady=(0, 8))

def make_stat(parent, color, label, val):
    c = tk.Frame(parent, bg=CARD, padx=10, pady=8,
                 highlightbackground=LIGHT2, highlightthickness=1)
    c.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=3)
    v = tk.Label(c, text=val, font=("Segoe UI", 22, "bold"), fg=color, bg=CARD)
    v.pack()
    tk.Label(c, text=label, font=("Segoe UI", 15), fg=TEXTG, bg=CARD).pack()
    return v

lbl_stat_occ  = make_stat(stats_row, OCC_C,   "Ocupados",    "00")
lbl_stat_free = make_stat(stats_row, FREE_C,  "Disponibles", "40")
make_stat(stats_row, ACCENT3, "Capacidad", "40")
lbl_stat_pct  = make_stat(stats_row, ACCENT4, "Ocupación",   "0%")


ops_row = tk.Frame(left, bg=BG)
ops_row.pack(fill=tk.X, pady=(0, 8))

var_placa_in  = tk.StringVar()
var_puesto_in = tk.StringVar()
var_placa_out = tk.StringVar()

NEON_PAD = 6
P = NEON_PAD

cvs_in  = tk.Canvas(ops_row, bg=BG, highlightthickness=0)
cvs_in.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))

cvs_out = tk.Canvas(ops_row, bg=BG, highlightthickness=0)
cvs_out.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0))

frame_panel_in  = tk.Frame(cvs_in,  bg=CARD, padx=10, pady=10)
frame_panel_out = tk.Frame(cvs_out, bg=CARD, padx=10, pady=10)

cvs_in_win  = cvs_in.create_window( P, P, anchor="nw", window=frame_panel_in)
cvs_out_win = cvs_out.create_window(P, P, anchor="nw", window=frame_panel_out)

def _resize_cvs(cvs, win):
    w = cvs.winfo_width(); h = cvs.winfo_height()
    cvs.itemconfig(win, width=w - 2*P, height=h - 2*P)

cvs_in.bind( "<Configure>", lambda e: _resize_cvs(cvs_in,  cvs_in_win))
cvs_out.bind("<Configure>", lambda e: _resize_cvs(cvs_out, cvs_out_win))

tk.Frame(frame_panel_in, bg=ACCENT1, height=3).pack(fill=tk.X, pady=(0, 8))
tk.Label(frame_panel_in, text="● Registro ingreso",
         font=("Segoe UI", 12, "bold"), fg=TEXT2, bg=CARD).pack(anchor="w", pady=(0, 4))
lbl_in_status = tk.Label(frame_panel_in, text="Esperando vehículo...",
                          font=("Segoe UI", 12), fg=TEXTG, bg=CARD)
lbl_in_status.pack(anchor="w", pady=(0, 6))

entry_placa_in = tk.Entry(frame_panel_in, textvariable=var_placa_in,
                           font=("Segoe UI", 12), fg=TEXT1, bg=LIGHT1,
                           relief=tk.FLAT, bd=0, insertbackground=TEXT1,
                           highlightbackground=LIGHT2, highlightthickness=1)
entry_placa_in.pack(fill=tk.X, pady=(0, 5), ipady=5)
entry_placa_in.insert(0, "Placa del vehículo")
entry_placa_in.bind("<FocusIn>", lambda e: entry_placa_in.delete(0, tk.END)
                    if entry_placa_in.get() == "Placa del vehículo" else None)

entry_puesto_in = tk.Entry(frame_panel_in, textvariable=var_puesto_in,
                            font=("Segoe UI", 12), fg=TEXT1, bg=LIGHT1,
                            relief=tk.FLAT, bd=0, insertbackground=TEXT1,
                            highlightbackground=LIGHT2, highlightthickness=1)
entry_puesto_in.pack(fill=tk.X, pady=(0, 5), ipady=5)
entry_puesto_in.insert(0, "N° puesto (opcional)")
entry_puesto_in.bind("<FocusIn>", lambda e: entry_puesto_in.delete(0, tk.END)
                     if entry_puesto_in.get() == "N° puesto (opcional)" else None)

btn_in = tk.Button(frame_panel_in, text="→  Autorizar ingreso",
                   font=("Segoe UI", 15, "bold"), bg=ACCENT1, fg="white",
                   relief=tk.FLAT, bd=0, activebackground=ACCENT2, activeforeground="white",
                   cursor="hand2", pady=7, command=procesar_ingreso)
btn_in.pack(fill=tk.X, pady=(4, 0))


tk.Frame(frame_panel_out, bg=FREE_C, height=3).pack(fill=tk.X, pady=(0, 8))
tk.Label(frame_panel_out, text="● Registro salida",
         font=("Segoe UI", 12, "bold"), fg="#00796b", bg=CARD).pack(anchor="w", pady=(0, 4))
lbl_out_status = tk.Label(frame_panel_out, text="Esperando vehículo...",
                           font=("Segoe UI", 12), fg=TEXTG, bg=CARD)
lbl_out_status.pack(anchor="w", pady=(0, 6))

entry_placa_out = tk.Entry(frame_panel_out, textvariable=var_placa_out,
                            font=("Segoe UI", 12), fg=TEXT1, bg=LIGHT1,
                            relief=tk.FLAT, bd=0, insertbackground=TEXT1,
                            highlightbackground="#a5d6a7", highlightthickness=1)
entry_placa_out.pack(fill=tk.X, pady=(0, 5), ipady=5)
entry_placa_out.insert(0, "Placa del vehículo")
entry_placa_out.bind("<FocusIn>", lambda e: entry_placa_out.delete(0, tk.END)
                     if entry_placa_out.get() == "Placa del vehículo" else None)

btn_out = tk.Button(frame_panel_out, text="←  Autorizar salida",
                    font=("Segoe UI", 15, "bold"), bg="#00796b", fg="white",
                    relief=tk.FLAT, bd=0, activebackground="#00695c", activeforeground="white",
                    cursor="hand2", pady=7, command=procesar_salida)
btn_out.pack(fill=tk.X, pady=(34, 0))


neon_in  = PanelNeon(cvs_in,  "#ff1744", "#7f0000")
neon_out = PanelNeon(cvs_out, "#00e676", "#004d26")


emerg_row = tk.Frame(left, bg=BG)
emerg_row.pack(fill=tk.X)

btn_emerg_open = tk.Button(emerg_row, text="⚠  Apertura de emergencia",
                            font=("Segoe UI", 15, "bold"),
                            bg="#7f1d1d", fg="#fca5a5", relief=tk.FLAT, bd=0,
                            activebackground="#991b1b", activeforeground="#fca5a5",
                            cursor="hand2", pady=9, command=abrir_emergencia)
btn_emerg_open.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))

btn_emerg_close = tk.Button(emerg_row, text="🔒  Cerrar emergencia",
                             font=("Segoe UI", 15, "bold"),
                             bg=LIGHT1, fg=TEXTG, relief=tk.FLAT, bd=0,
                             activebackground=LIGHT1, cursor="hand2",
                             pady=9, state=tk.DISABLED, command=cerrar_emergencia)
btn_emerg_close.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0))


log_card = tk.Frame(left, bg=CARD, highlightbackground=LIGHT2, highlightthickness=1)
log_card.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

tk.Label(log_card, text="  Historial de movimientos",
         font=("Segoe UI", 15, "bold"), fg=TEXT1, bg=CARD).pack(anchor="w", pady=(8, 4))

log_canvas = tk.Canvas(log_card, bg=CARD, highlightthickness=0)
log_scroll  = tk.Scrollbar(log_card, orient=tk.VERTICAL, command=log_canvas.yview)
log_canvas.configure(yscrollcommand=log_scroll.set)
log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
log_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

frame_log_inner = tk.Frame(log_canvas, bg=CARD)
log_canvas.create_window((0, 0), window=frame_log_inner, anchor="nw")

def on_log_configure(e):
    log_canvas.configure(scrollregion=log_canvas.bbox("all"))
    log_canvas.yview_moveto(1.0)
frame_log_inner.bind("<Configure>", on_log_configure)


slots_card = tk.Frame(right, bg=CARD, padx=12, pady=10,
                      highlightbackground=LIGHT2, highlightthickness=1)
slots_card.pack(fill=tk.BOTH, expand=True)

slots_header = tk.Frame(slots_card, bg=CARD)
slots_header.pack(fill=tk.X, pady=(0, 8))
tk.Label(slots_header, text="Mapa de puestos",
         font=("Segoe UI", 15, "bold"), fg=TEXT1, bg=CARD).pack(side=tk.LEFT)

legend_frame = tk.Frame(slots_header, bg=CARD)
legend_frame.pack(side=tk.RIGHT)
for color, lbl_txt in [(FREE_C, "Libre"), (OCC_C, "Ocupado")]:
    tk.Frame(legend_frame, bg=color, width=10, height=10).pack(side=tk.LEFT, padx=(6, 2))
    tk.Label(legend_frame, text=lbl_txt, font=("Segoe UI", 12),
             fg=TEXTG, bg=CARD).pack(side=tk.LEFT)

grid_frame = tk.Frame(slots_card, bg=CARD)
grid_frame.pack(fill=tk.BOTH, expand=True)

for col in range(8):
    grid_frame.columnconfigure(col, weight=1)

for i in range(40):
    row_i = i // 8
    col_i = i % 8
    card = tk.Frame(grid_frame, bg=FREE_BG, padx=4, pady=6,
                    highlightbackground=FREE_C, highlightthickness=1)
    card.grid(row=row_i, column=col_i, padx=3, pady=3, sticky="nsew")
    grid_frame.rowconfigure(row_i, weight=1)
    lbl_num   = tk.Label(card, text=f"P{i+1}", font=("Segoe UI", 13, "bold"),
                          fg="#2e7d32", bg=FREE_BG)
    lbl_num.pack()
    lbl_placa = tk.Label(card, text="LIBRE", font=("Segoe UI", 11, "bold"),
                          fg=FREE_C, bg=FREE_BG)
    lbl_placa.pack()
    lbl_time  = tk.Label(card, text="", font=("Segoe UI", 10),
                          fg=TEXTG, bg=FREE_BG)
    lbl_time.pack()
    slot_frames.append((card, lbl_num, lbl_placa, lbl_time))


tk.Frame(shell, bg=LIGHT2, height=1).pack(fill=tk.X)
nav_bar = tk.Frame(shell, bg=NAV_BG, height=52)
nav_bar.pack(fill=tk.X)
nav_bar.pack_propagate(False)

nav_items = [("⌂","Inicio",True),("⏚","Cámaras",False),("☰","Reportes",False),
             ("⊞","Monitor",False),("☻","Usuarios",False),("⏏","Salir",False)]
for icon, label, active in nav_items:
    bg_i = "#283593" if active else NAV_BG
    fg_i = "#ffffff"  if active else "#7986cb"
    item = tk.Frame(nav_bar, bg=bg_i, padx=12, pady=4, cursor="hand2")
    item.pack(side=tk.LEFT, padx=2, pady=6)
    tk.Label(item, text=icon,  font=("Segoe UI", 16), fg=fg_i, bg=bg_i).pack()
    tk.Label(item, text=label, font=("Segoe UI", 15), fg=fg_i, bg=bg_i).pack()


root.bind('<Return>', lambda e: procesar_ingreso())
root.bind('<space>',  lambda e: procesar_salida())

inicializar_db()
agregar_log("Sistema iniciado — 40 puestos disponibles", "in")
agregar_log("Servidor TCP escuchando en puerto 65432", "in")
actualizar_ui()
refrescar()
threading.Thread(target=servidor_tcp, daemon=True).start()
root.mainloop()