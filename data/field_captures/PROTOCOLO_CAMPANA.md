# Protocolo de Campaña de Campo

> Procedimiento para levantar un radio-mapa **real** del edificio y reportarlo por separado del
> sintético. Es la única forma de convertir las métricas actuales, que son de simulación, en
> mediciones empíricas.

Este documento no sustituye a la medición: describe cómo hacerla para que los datos sirvan.

> **Relación con `GUIA_MAPEO_Y_DESPLIEGUE.md`.** Esa guía cubre el procedimiento operativo paso a
> paso: desactivar el *throttling* de escaneo en Android, manejar la app en modo calibrador y
> desplegar el servidor con túnel. Este documento cubre lo complementario: los criterios que
> deciden si los datos resultantes valen para algo. Léelos juntos; la cuadrícula de puntos sale
> de un comando, no de ninguno de los dos:
>
> ```bash
> PYTHONPATH=. python calibration_tools/print_mapping_grid.py --floor 1
> ```

---

## 0. Por qué existe este protocolo

El primer intento de campaña produjo tres capturas inservibles (`RP_P3_HAll`, `RP_Escalera`,
`RP_P4_Meta`, conservadas en este directorio). Las tres se guardaron en la coordenada
**(10.0, 2.0)** porque el cliente Android tenía las coordenadas fijadas en el código y no las
pedía. Tres puntos físicamente distintos con la misma posición no sirven ni para el WKNN ni para
la validación cruzada.

Eso ya está corregido: el calibrador ahora exige X e Y y rechaza el envío si faltan. El resto de
este documento cubre los errores que el software **no** puede impedir.

---

## 1. Antes de salir

- [ ] **Fijar el origen de coordenadas y los ejes.** Elige una esquina del edificio como (0, 0) y
      deja por escrito hacia dónde crece X y hacia dónde Y. Todo el equipo debe usar el mismo
      criterio: media campaña medida con los ejes girados es media campaña perdida.
- [ ] **Dibujar el plano con las coordenadas objetivo** de cada punto de referencia antes de
      medir, no sobre la marcha. Numéralos con el convenio `RP_<aula o zona>_<detalle>`, por
      ejemplo `RP_S302_Center`, `RP_P3_Hall_C`.
- [ ] **Comprobar que el modelo del edificio coincide con la realidad.** El grafo actual
      (`create_default_school_graph`) sitúa las aulas en x = 2, 10 y 18 y la escalera en
      (10, 8), con los pisos separados 3.5 m. Si el edificio real no encaja, hay que ajustar el
      grafo **antes** de medir, o las coordenadas medidas no serán comparables con las rutas.
- [ ] **Anotar el modelo de teléfono.** Chipsets distintos reportan el RSSI con desplazamientos
      de varios dB para la misma señal. Si la campaña usa más de un dispositivo, hay que
      registrar cuál midió cada punto.
- [ ] **Cinta métrica o telémetro.** Estimar la posición "a ojo" introduce un error de 1–2 m que
      se suma directamente al error del sistema y lo hace parecer peor de lo que es.

## 2. Densidad y cobertura

- [ ] **Un punto cada 3–5 m** en zonas de tránsito. La validación actual usa 1 RP cada 3–8 m.
- [ ] **Como mínimo**: centro y puerta de cada aula que se quiera cubrir, tres puntos por pasillo
      y el descanso de cada escalera. Para las 12 aulas del modelo, eso son 40 puntos.
- [ ] **Cubrir los cuatro pisos.** Un piso sin puntos de referencia no puede clasificarse, y el
      clasificador jerárquico asignará sus lecturas al piso más parecido sin avisar.
- [ ] **Incluir las esquinas del aula**, no solo el centro. El criterio geométrico usa un radio de
      4 m desde el centro, y conviene comprobar con datos reales que cubre toda la superficie.

## 3. Durante la medición

- [ ] **15 muestras por punto** (el calibrador las cuenta). No reducirlas: la desviación estándar
      por BSSID se calcula con ellas y es lo que permite evaluar la ponderación probabilística.
- [ ] **Mantener el teléfono a la altura de uso real**, en la mano a la altura del pecho, no
      apoyado en el suelo ni en una mesa. El cuerpo atenúa y esa atenuación forma parte de la
      señal que verá el sistema en operación.
- [ ] **Girar sobre uno mismo** entre muestras, o medir en dos orientaciones. La antena del
      teléfono es direccional y una sola orientación sesga la huella.
- [ ] **Medir con el edificio en uso**, no un domingo. Un aula vacía y una ocupada difieren en
      3–6 dB, y el sistema operará con gente dentro.
- [ ] **Anotar la hora de cada punto.** La deriva temporal del RSSI es la principal causa de
      degradación en fingerprinting, y sin la hora no se puede estudiar.

## 4. Después

- [ ] **Descargar el radio-mapa** con `GET /api/v1/calibration/radio-map` y guardarlo en este
      directorio con un nombre que indique la fecha, por ejemplo `campo_2026_10_15.json`.
- [ ] **Seudonimizar los BSSID** antes de commitear. Las MAC de puntos de acceso son
      geolocalizables en bases públicas de *wardriving*. Usa el mismo esquema determinista que las
      capturas existentes, `ap_field_<primeros 8 hex de sha256(mac)>`, para que el mismo AP siga
      siendo comparable entre campañas.
- [ ] **Validar el dataset** antes de darlo por bueno:

      ```bash
      PYTHONPATH=. python calibration_tools/loocv_evaluator.py --map data/field_captures/campo_2026_10_15.json
      ```

- [ ] **Reportarlo por separado** del sintético en `calibration_tools/validation_report.md`. No
      mezclar ambos datasets en una sola tabla: la comparación entre "simulado" y "medido" es
      justamente el resultado interesante.

## 5. Qué esperar

La literatura sitúa el error típico de WKNN en despliegues reales en **3–5 m**
(Bahl & Padmanabhan 2000; Torres-Sospedra et al. 2014), frente a los 1.70 m de la simulación
actual. **Un resultado de 3–4 m en campo no es un fracaso: es el resultado esperado**, y
reportarlo honestamente vale más que un 1.70 m que solo se sostiene contra un modelo idealizado.

Lo que sí conviene comprobar en campo, porque el modelo lo favorece artificialmente:

| Métrica | En simulación | Qué revisar en campo |
| :--- | :---: | :--- |
| Aislamiento de piso | 100% | El modelo solo atenúa las losas; las paredes no atenúan nada. Es la cifra más optimista de todas. |
| Error medio 2D | 1.70 m | Sin multicamino ni cuerpos humanos. Espera 3–5 m. |
| k óptimo | 2 | Con ruido real, un k mayor podría resultar más robusto. Repetir el barrido. |
| FAR / FRR | 0% / 0% | Los umbrales (−70 dBm, 4 m) se derivaron del modelo de propagación, no de medidas. Re-sintonizar con `threshold_tuner.py`. |
