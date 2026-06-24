Sistema IoT de Parqueadero Concurrente

Este es un proyecto distribuido de extremo a extremo desarrollado para la asignatura de **Arquitectura de Computadores**. Consiste en un sistema de gestión de parqueadero a escala (maqueta automatizada) que integra el control de hardware en tiempo real con una aplicación centralizada de escritorio utilizando una arquitectura Cliente-Servidor sobre una red WiFi local.

Tecnologías y Componentes
- **Hardware:** Raspberry Pi Pico 2W, Sensores Infrarrojos (IR), Servomotores SG90, Protoboard.
- **Software & Protocolos:** Python, MicroPython, Sockets TCP/IP, JSON, Multi-threading.


Arquitectura del Sistema
El proyecto implementa una arquitectura distribuida **Cliente-Servidor** comunicada de manera síncrona mediante **Sockets TCP/IP**:

El Cliente (Edge - Raspberry Pi Pico 2W)
Desarrollado en **MicroPython**. Se encarga del control físico directo de la maqueta utilizando conceptos de concurrencia:
- **Hilos (`_thread`):** Utiliza hilos de ejecución independientes en los núcleos de la Pico para monitorear en tiempo real y de forma síncrona los sensores infrarrojos de entrada y salida sin bloquear el flujo general del programa.
- **Control de Actuadores:** Modula señales PWM para abrir y cerrar de forma precisa las talanqueras físicas mediante servomotores SG90 tras recibir autorizaciones del servidor.
El Servidor (Central - PC GUI App)
Desarrollado en **Python** en el entorno VS Code. Actúa como el cerebro del sistema:
- **Interfaz Gráfica de Usuario (GUI):** Diseñada en **Tkinter**, despliega un mapa interactivo de 40 puestos en tiempo real (Verde = Libre, Rojo = Ocupado), un panel dinámico con animaciones de neón al detectar vehículos, logs de eventos detallados y un botón de apertura manual por emergencia.
- **Exclusión Mutua (`threading.Lock`):** Implementa mecanismos de sincronización avanzados para proteger la base de datos contra condiciones de carrera, permitiendo procesar ingresos y salidas concurrentes sin corromper el registro.
- **Persistencia de Datos:** Utiliza un archivo estructurado `parqueadero.json` para almacenar los autos actuales, puestos ocupados y marcas de tiempo, manteniendo los datos intactos incluso ante reinicios o apagados del servidor.

---

Conexión de Pines (Mapeo de Hardware)

| Componente | Pin GPIO | Función |
| :--- | :--- | :--- |
| **Servo Entrada (SG90)** | GPIO 15 | Control de barrera de entrada (PWM) |
| **Servo Salida (SG90)** | GPIO 16 | Control de barrera de salida (PWM) |
| **Sensor IR Entrada** | GPIO 14 | Detección de vehículo entrante (Pull-Up) |
| **Sensor IR Salida** | GPIO 17 | Detección de vehículo saliente (Pull-Up) |

---
Casos de Prueba Evaluados e Implementados
El sistema supera con éxito los criterios de estrés de la guía de laboratorio:
1. **Entrada Normal:** Detección IR -> Registro y validación de placa en la GUI -> Apertura y cierre temporalizado de la talanquera.
2. **Salida Normal:** Detección IR -> Cálculo automático del tiempo transcurrido y tarifa por minuto en COP -> Liberación automática del puesto en el JSON -> Apertura de talanquera.
3. **Concurrencia Pura:** Gestión simultánea de peticiones de entrada y salida mediante hilos concurrentes sin bloqueos ni pérdidas de datos.
4. **Aforo Lleno:** Bloqueo automático de ingreso y alerta visual cuando la capacidad máxima (40 puestos) es alcanzada.
5. **Apertura de Emergencia:** Control forzado desde la GUI que abre permanentemente ambas compuertas y notifica por socket a la Raspberry Pi.
