# Capturas de Campo (Evidencia, NO dataset de calibración)

Este directorio conserva las huellas Wi-Fi **reales** tomadas con el cliente Android
(`CalibratorManager`) durante las pruebas en el edificio. Se extrajeron de
`data/radio_map.json`, donde estaban mezcladas con los 40 puntos de referencia sintéticos y
degradaban la auditoría LOOCV (la precisión de aislamiento de piso caía de 100% a 88.6–93.2%,
por debajo del objetivo de diseño de ≥95%).

## Contenido

`field_captures.json` — 3 capturas, 44 puntos de acceso distintos:

| ID | Piso declarado | APs detectados |
| :--- | :---: | :---: |
| `RP_P3_HAll` | 3 | 32 |
| `RP_Escalera` | 3 | 29 |
| `RP_P4_Meta` | 4 | 23 |

## Por qué NO son puntos de referencia utilizables

Las tres capturas tienen la coordenada **(10.0, 2.0)**, que es el valor por defecto del
formulario del calibrador: durante la toma no se fijaron `x` e `y`. Tres puntos físicamente
distintos (un pasillo del piso 3, una escalera y un punto del piso 4) comparten posición, así
que no pueden alimentar ni el WKNN ni el LOOCV.

**Para reutilizarlas hay que volver a medir la posición real de cada punto** y solo entonces
reincorporarlas a un dataset de calibración.

## Seudonimización de BSSID

Los BSSID originales eran direcciones MAC reales de los puntos de acceso del edificio, que son
geolocalizables en bases de datos públicas de *wardriving* (WiGLE y similares). Se sustituyeron
por un seudónimo determinista:

```
ap_field_<primeros 8 hex de sha256(mac_en_minúsculas)>
```

Es determinista, de modo que el mismo AP recibe el mismo identificador en capturas futuras y
las huellas siguen siendo comparables entre sí.

> **Advertencia:** esto es seudonimización, no anonimización fuerte. El espacio de direcciones
> MAC es pequeño (2^48, y el prefijo OUI del fabricante es público), así que un atacante con
> recursos podría invertir el hash por fuerza bruta. Sirve para no publicar las MAC en claro,
> no como garantía criptográfica.
>
> **Las MAC originales siguen en el historial de Git** (commit `89937a6`). Eliminarlas de ahí
> requiere reescribir el historial con `git filter-repo` y forzar el push, lo que invalida
> cualquier clon existente. Es una decisión que hay que tomar conscientemente.
