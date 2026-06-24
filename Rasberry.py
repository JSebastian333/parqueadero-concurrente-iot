import time
import network
import socket
import json
import _thread
from machine import Pin, PWM

# Red wifi
WIFI_SSID = "HONOR"
WIFI_PASS = "123456789"

# Servidor
SERVER_IP = "10.190.171.68"
SERVER_PORT = 65432

# Hardware
servo_entrada = PWM(Pin(15))
servo_salida = PWM(Pin(16))
servo_entrada.freq(50)
servo_salida.freq(50)

ir_entrada = Pin(14, Pin.IN, Pin.PULL_UP)
ir_salida = Pin(17, Pin.IN, Pin.PULL_UP)

# Abrir puertas
emergencia_activa = False


def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print(f"Conectando a la red {WIFI_SSID}...")
        wlan.connect(WIFI_SSID, WIFI_PASS)
        while not wlan.isconnected():
            time.sleep(1)
    print("¡Conexión WiFi establecida!")
    print("IP de la Pico:", wlan.ifconfig()[0])

def calcular_duty(angulo):
    min_duty = 1638
    max_duty = 8192
    return int(min_duty + (angulo / 180.0) * (max_duty - min_duty))

def controlar_entrada(abrir):
    if abrir:
        servo_entrada.duty_u16(calcular_duty(90))
    else:
        servo_entrada.duty_u16(calcular_duty(0))

def controlar_salida(abrir):
    if abrir:
        servo_salida.duty_u16(calcular_duty(90))
    else:
        servo_salida.duty_u16(calcular_duty(180))

def enviar_peticion_socket(diccionario_datos):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((SERVER_IP, SERVER_PORT))
        s.sendall(json.dumps(diccionario_datos).encode('utf-8'))
        respuesta_raw = s.recv(1024).decode('utf-8')
        s.close()
        return json.loads(respuesta_raw)
    except Exception as e:
        print(f"Error de socket: {e}")
        return {"estado": "error", "mensaje": "No se pudo conectar al servidor"}

#Inicio
controlar_entrada(abrir=False)
controlar_salida(abrir=False)


def hilo_entrada_y_emergencia():
    global emergencia_activa
    print("Core1: Hilo de ENTRADA + MONITOR DE EMERGENCIA activo...")

    contador_emergencia = 0  # Consulta al servidor cada 2 s

    while True:
        # Consulta emergencia
        contador_emergencia += 1
        if contador_emergencia >= 20:
            contador_emergencia = 0
            try:
                respuesta = enviar_peticion_socket({"accion": "chequear_estado"})
                estado = respuesta.get("estado")

                if estado == "emergencia" and not emergencia_activa:
                    emergencia_activa = True
                    print("EMERGENCIA: Abriendo barreras.")
                    controlar_entrada(abrir=True)
                    controlar_salida(abrir=True)

                elif estado == "normal" and emergencia_activa:
                    emergencia_activa = False
                    print("Emergencia desactivada. Cerrando barreras.")
                    controlar_entrada(abrir=False)
                    controlar_salida(abrir=False)
            except Exception as e:
                print(f"Monitor emergencia: {e}")

        #Sensor de entrada
        if not emergencia_activa and ir_entrada.value() == 0:
            print("\nVehículo detectado en la entrada. Validando aforo...")
            respuesta = enviar_peticion_socket({"accion": "solicitar_ingreso"})

            if respuesta.get("estado") == "emergencia":
                emergencia_activa = True
                controlar_entrada(abrir=True)
                controlar_salida(abrir=True)
                print("Emergencia recibida en respuesta de ingreso.")

            elif respuesta.get("estado") == "autorizado":
                print(f"{respuesta['mensaje']}. Puestos libres: {respuesta['puestos_libres']}")
                controlar_entrada(abrir=True)
                while ir_entrada.value() == 0:
                    time.sleep(0.1)
                time.sleep(2)
                controlar_entrada(abrir=False)
                print("Barrera de entrada cerrada.")
            else:
                print(f"Ingreso denegado: {respuesta.get('mensaje')}")
                time.sleep(2)

        time.sleep(0.1)


#Solo salida
def hilo_salida_principal():
    global emergencia_activa
    print("Core0: Hilo de SALIDA activo...")

    while True:
        if not emergencia_activa and ir_salida.value() == 0:
            print("Vehículo detectado en la salida. Procesando...")
            respuesta = enviar_peticion_socket({"accion": "solicitar_salida"})

            if respuesta.get("estado") == "emergencia":
                emergencia_activa = True
                controlar_entrada(abrir=True)
                controlar_salida(abrir=True)
                print("Emergencia recibida en respuesta de salida.")

            elif respuesta.get("estado") == "autorizado":
                print(f"{respuesta['mensaje']}. Puestos libres: {respuesta['puestos_libres']}")
                controlar_salida(abrir=True)
                while ir_salida.value() == 0:
                    time.sleep(0.1)
                time.sleep(2)
                controlar_salida(abrir=False)
                print("Barrera de salida cerrada.")
            else:
                print(f"Error al procesar salida: {respuesta.get('mensaje')}")
                time.sleep(2)

        time.sleep(0.1)


# Principal
conectar_wifi()

_thread.start_new_thread(hilo_entrada_y_emergencia, ())
hilo_salida_principal()