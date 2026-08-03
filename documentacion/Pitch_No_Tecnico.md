# Pitch No Técnico — Gestión de Citas Médicas Analyzer (HU-015)

**Versión para gente sin conocimientos de código (personal administrativo, negocio, pacientes, inversores).**

---

## 1. El problema de todos los días

Imaginá un centro de salud que recibe **miles de mensajes por día** de pacientes que quieren cambiar, cancelar o confirmar sus citas. Mensajes como este:

> *"Deseo solicitar la reprogramación de mi cita médica con el cardiólogo para la próxima semana en el horario de la mañana."*

Leer cada mensaje, entender **qué quiere el paciente** (¿reprogramar? ¿cancelar?), **con qué médico** (¿cardiólogo? ¿pediatra?) y **a qué horario** (¿mañana? ¿tarde?) lleva tiempo y personal. Y cuando son 15,000 mensajes diarios, ese trabajo se convierte en un cuello de botella: pacientes que esperan, errores humanos y personal ocupado en tareas repetitivas.

Este proyecto nace para resolver exactamente eso.

---

## 2. Qué hace el sistema

**"Gestión de Citas Médicas Analyzer"** es un sistema que lee esas solicitudes por nosotros. Toma el archivo de Excel donde el centro guarda todos los pedidos de los pacientes y, mensaje por mensaje, es capaz de entender:

- **Qué acción quiere el paciente** → reprogramar, cancelar o confirmar la cita.
- **Con qué especialidad** → cardiología, pediatría, dermatología, etc. (13 especialidades).
- **A qué horario prefiere** → mañana, tarde o noche.

El resultado es un archivo nuevo, ordenado y listo para usar: una fila por cada paciente, con su pedido ya "clasificado". Es como si un recepcionista leyera los 15,000 mensajes y dejara una planilla resumida, pero en segundos y sin equivocarse.

---

## 3. Cómo funciona, paso a paso (en palabras simples)

Pensemos en el sistema como un **equipo de recepcionistas automáticos** que trabajan en cadena:

**Paso 1 — Recibir las solicitudes.** El centro sube su archivo de Excel (o el sistema mira una carpeta entera donde se van dejando los archivos). No importa el formato exacto de las columnas: el sistema las reconoce por sí solo.

**Paso 2 — Ordenar por especialidad.** Los mensajes se separan en montones según el tipo de médico que mencionan: los que hablan del cardiólogo van en un montón, los del pediatra en otro. Así el trabajo se reparte en paralelo, como varios recepcionistas atendiendo cada uno su propio mostrador.

**Paso 3 — Agrupar mensajes parecidos.** Dentro de cada especialidad, el sistema junta los mensajes que se parecen mucho entre sí (por ejemplo, todos los que dicen "reprogramar en la mañana"). De cada grupo, se queda con **un solo mensaje de ejemplo** para analizarlo. Con 50,000 solicitudes, esto reduce todo a unos **60 grupos representativos**. Es el mismo truco de "no leas los 500 correos parecidos, leé uno y aplicá la respuesta a todos".

**Paso 4 — Entender el mensaje.** Sobre cada grupo representativo, el sistema extrae la información clave: la acción (reprogramar/cancelar/confirmar), la especialidad y el horario preferido. Y esa misma respuesta se aplica a todos los mensajes de ese grupo.

**Paso 5 — Medir los costos (la parte importante).** Cuando la opción está activada, el sistema traduce el mensaje de ejemplo al inglés **solo para comparar cuánto "cuesta leerlo"** en cada idioma. El resultado se guarda en un informe: cuántos tokens (unidades que la inteligencia artificial cobra) consume el español vs. el inglés.

**Paso 6 — Mostrar los resultados.** Todo se ve en una **página web** con gráficos, barras de progreso en vivo y un botón para descargar el Excel final con cada paciente ya clasificado.

---

## 4. El descubrimiento que ahorra dinero

Aquí está el corazón del proyecto, y se explica así:

Los sistemas de inteligencia artificial **cobran por la cantidad de texto que leen**. Ese texto se mide en unidades llamadas **tokens** (imaginalos como "pedacitos de palabras"). A más tokens, más caro.

Y ocurre algo curioso con el español médico: palabras largas y formales como **"reprogramación"** o **"cardiología"** se parten en muchos pedacitos cuando la máquina las lee. En inglés, esas mismas ideas ocupan menos pedacitos.

Este sistema **mide exactamente esa diferencia** y responde una pregunta de negocios concreta:

> **"¿Me conviene procesar los mensajes directamente en español, o traducirlos al inglés primero para gastar menos en inteligencia artificial?"**

Con el estimador de costos, en un clic podés ver el ahorro proyectado para el volumen real del centro. Por ejemplo, con **15,000 mensajes por día** y una tarifa de **$2.50 USD por cada millón de tokens**:

| Período | Costo en español | Costo en inglés | **Ahorro** |
|---|---|---|---|
| Por día | más alto | más bajo | una diferencia medible |
| Por mes (30 días) | — | — | se nota |
| Por año (365 días) | — | — | se nota mucho |

La respuesta a esa pregunta **no es la misma para todos**: depende del tipo de vocabulario que use cada centro. Este sistema entrega **datos reales, medidos con tus propios mensajes**, para decidir la estrategia con números en la mano y no a ciegas.

---

## 5. La pantalla (cómo se ve)

Quien use el sistema no necesita saber de código. La interfaz web incluye:

- **Dos modos de carga**: arrastrar un archivo Excel, o indicar una carpeta entera para procesar todos los archivos que contenga.
- **Una casilla "optimizar tokens"**: al activarla, el sistema hace la comparación de costos español vs. inglés. Es opcional.
- **Barra de progreso en vivo**: muestra por qué etapa va el proceso (leyendo archivo, agrupando mensajes, clasificando, terminado).
- **Tarjetas con las métricas clave**: tokens en español, tokens en inglés, costo estimado, ahorro y fragmentación.
- **Gráficos** (de torta y de barras) que resumen los resultados: qué acciones pidieron los pacientes, a qué horarios, por especialidad, y la comparación de costos entre idiomas.
- **Tabla de resultados** con el detalle de cada paciente.
- **Botón de exportar**: descarga el Excel final con una fila por mensaje, listo para entregar o importar a otro sistema.

---

## 6. Para qué sirve en la práctica

- **Ahorro de tiempo**: procesar 50,000 solicitudes en segundos, en lugar de días de trabajo manual.
- **Decisión de costos con datos**: saber con certeza si conviene (o no) pagar por traducción previa antes de enviar los mensajes a la inteligencia artificial.
- **Menos errores**: la clasificación es consistente y se puede auditar.
- **Orden y trazabilidad**: cada paciente tiene su fila con el pedido ya entendido, exportable a Excel.
- **Escalable**: funciona con un archivo chico o con una carpeta llena de archivos grandes.

---

## 7. En tres frases

1. Es un **"recepcionista automático"** que lee los mensajes de los pacientes y los deja clasificados (qué quiere, con qué médico, a qué horario) en un Excel.
2. Además **mide cuánto cuesta que la inteligencia artificial lea cada idioma**, y calcula el ahorro de traducir antes de procesar.
3. Todo se opera desde una **página web sencilla**, sin saber de código, y el resultado se exporta en un clic.
