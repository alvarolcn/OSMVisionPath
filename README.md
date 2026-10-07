# TERRA · Trazador de caminos PNOA

Prototipo local con OpenCV 5 y una interfaz web en español. Descarga una ortofoto WMS del PNOA, permite marcar puntos sobre un camino, calcula un recorrido asistido y lo dibuja progresivamente encima de la imagen. Exporta GeoJSON en longitud/latitud WGS84.

## Iniciar en Windows

Requiere Python 3.10 o superior e internet para descargar dependencias y consultar PNOA.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Abre http://127.0.0.1:5000. No es necesario activar el entorno ni instalar Node.

Si `/api/ortho` devuelve 502 con `WinError 10013`, el entorno donde se ejecuta Python está bloqueando la conexión al IGN. Detén el servidor y ejecuta el comando de inicio desde una terminal local con acceso a internet. Si lo inicia Codex, necesita acceso a red autorizado. El detalle del fallo aparece en la interfaz y en la consola del servidor.

1. Pulsa **Elegir área en OpenStreetMap**. Navega y haz clic para elegir el centro, o pulsa **Dibujar área** y arrastra desde una esquina. Se selecciona un cuadrado de 100–3000 m. **Usar esta área** rellena latitud, longitud y ancho; también puedes editarlos manualmente. Cancelar no cambia el área.
2. **Usar esta área** inicia automáticamente la descarga del IGN. Un loader cubre la foto hasta que se recibe, decodifica y dibuja la nueva ortofoto. También aparece durante la detección y se retira si hay un error. Para coordenadas editadas manualmente, pulsa **Cargar ortofoto**. La vista se abre ajustada para mostrar toda la imagen (100%); se mantiene la descarga de 4096×4096 para analizarla a resolución completa. Puedes ampliar hasta el 800%.
3. La **segmentación es el modo inicial**. Pulsa **Detectar área completa**. El modelo activo ya se puede usar: **Cargar otro modelo (opcional)** solo sirve para sustituirlo. No hace falta seleccionar archivo cada vez. La detección heurística sigue disponible en el selector.
4. Revisa los candidatos, descarta o corrige con puntos (máximo 20) y exporta el GeoJSON. **Mostrar zonas detectadas** superpone la máscara; la cobertura y probabilidad máxima ayudan a interpretar resultados vacíos.

El mapa usa Leaflet 1.9.4 servido localmente y las teselas estándar de OpenStreetMap, con atribución visible. Solo se solicitan las teselas de la vista abierta; no hay descarga masiva ni precarga de mapas. Requiere internet para el mapa base. Las coordenadas manuales siguen disponibles. OSM sirve para elegir el área; las imágenes analizadas proceden del PNOA y el modelo no consulta los caminos de OSM. La selección reproduce el cuadrado proyectado del WMS y su ancho aproximado en terreno en la latitud central.

## Cómo funciona y límites

### Nuevos modos de la GUI

- **Modelo de segmentación**: usa el ONNX activo del servidor. OpenCV DNN valida los modelos cargados con una inferencia antes de activarlos. Si existe el D-LinkNet34 convertido localmente y su informe de verificación, se carga al iniciar `python app.py` o en la primera consulta del modelo al arrancar desde Flask o un IDE. El archivo alternativo es opcional. No se descarga ningún modelo automáticamente.
- **Wololo · Inicio → Fin**: marca dos puntos sobre la ortofoto cargada y pulsa **Trazar con Wololo**. Reutiliza el modelo activo y analiza teselas nativas de 512×512 en un corredor alrededor de los marcadores. Busca una conexión global dentro del corredor mediante A*, favoreciendo píxeles con alta probabilidad de camino; no decide una rama definitiva al cambiar de tesela. Conserva en caché hasta 256 predicciones para reutilizarlas al corregir. No hace peticiones nuevas al PNOA: necesita que la imagen siga en memoria en el servidor.

Wololo calcula la propuesta primero y avanza por tramos cortos. Los tramos con baja probabilidad o posibles bifurcaciones requieren revisión; también hace pausas periódicas para confirmar la dirección. La vista se amplía al 800% y muestra la propuesta pendiente en naranja discontinuo. **Confirmar dirección** acepta ese tramo; **Corregir dirección** permite pulsar un punto de paso y recalcular desde el último tramo aceptado hasta el destino. **Deshacer tramo** recupera el tramo anterior para revisarlo; **Finalizar aquí** termina en el último punto aceptado y descarta la propuesta pendiente. **Nuevo inicio y fin** conserva lo aceptado y prepara otro camino. La exportación incluye solo los tramos aceptados. Al completar el recorrido puedes simplificarlo y exportarlo como los demás trazados.

Wololo favorece el **centro estimado de la vía**: calcula la distancia a los bordes de la máscara segmentada y penaliza el recorrido cerca de ellos. Combina esa preferencia con las probabilidades del modelo, manteniendo transitables los tramos poco reconocidos para pedir revisión. No mide bordes físicos que el modelo no haya detectado. Los cruces, sombras o máscaras incompletas pueden desplazar el eje; tus marcadores mantienen su posición exacta aunque estén fuera del centro.

**Reducir nodos: tolerancia** permite elegir 0,25; 0,5; 1; 2 o 5 metros (0,5 m por defecto). Aplica Douglas–Peucker en metros de terreno antes de mostrar cada propuesta. Conserva los extremos de los tramos y todos los puntos de paso; el panel indica el número de nodos antes y después. La revisión de dudas sigue usando los píxeles originales, sin depender de la geometría simplificada. Las exportaciones contienen el trazado simplificado que aceptaste. Cambiar la tolerancia se aplica en la siguiente búsqueda o corrección; los tramos ya aceptados se pueden modificar con **Simplificar trazado**.

Las dudas son estimaciones heurísticas, no una certeza del modelo. Wololo no aprende nuevos pesos a partir de las correcciones. **Límite de búsqueda** viene predefinido en 2.300.000 píxeles por conexión y se puede modificar entre 10.000 y 3.000.000. Un valor mayor permite una búsqueda más amplia y consume más tiempo y memoria; este límite es del buscador A*, no un requisito del modelo ni un radio alrededor del marcador. Puedes colocar puntos en cualquier zona de la ortofoto, fuera del corredor anterior: la próxima búsqueda analiza las teselas correspondientes al nuevo recorrido. **Nuevo inicio y fin** activa directamente los marcadores (modo A). Si se alcanza el límite, el aviso propone aumentarlo o añadir puntos y reintentar, sin repetir el mensaje. El zoom de revisión amplía la misma imagen; el análisis conserva los píxeles originales. No se garantiza encontrar un camino cuando la segmentación falla.

Contrato del ONNX: entrada float32 RGB en rango [0,1], NCHW `1×3×512×512`; salida única `1×1×H×W` de probabilidades [0,1] con sigmoid incluida. Sin normalización por media/desviación adicional en la GUI. No admite directamente modelos multiclase, logits, entradas NHWC ni modelos de detección de cajas. Si tu modelo tiene otro contrato, necesitará un adaptador. Límite de archivo en GUI: 255 MB; límite de petición: 256 MB. Otros modelos cargados desde la GUI se conservan en memoria hasta reiniciar.

La segmentación procesa recortes de 512×512 con solapamiento de 256 píxeles y mezcla ponderada; una ortofoto de 4096×4096 requiere 225 inferencias. Conserva la resolución descargada, en lugar de reducir todo el área. Las imágenes menores se rellenan por reflexión y se recortan al tamaño original. La máscara resultante se convierte en ejes normalizados respecto a toda la ortofoto. El modo heurístico también analiza los píxeles descargados sin reducción. La detección tarda más que con imágenes de 1024×1024; el loader permanece visible durante ese trabajo.

Selecciona un candidato en la lista o haciendo clic sobre él (se resalta en naranja). Puedes descartarlo o pulsar **Corregir**: aparecen puntos que puedes arrastrar y recalcular con el algoritmo asistido por color. Al recalcular se reemplaza ese candidato; los demás se conservan. Para añadir otro recorrido, selecciona la herramienta de puntos sin un candidato seleccionado. El GeoJSON contiene los candidatos conservados y las correcciones aplicadas. Las correcciones quedan marcadas con su método real de extracción por color.

**Simplificar trazado** usa Douglas–Peucker con tolerancia en metros de terreno en la latitud central del área: 0,25; 0,5; 1; 2; 5 o 10 m. Puedes aplicar el cambio al candidato seleccionado o a todos. Conserva los extremos, los vértices compartidos entre trazados y un mínimo válido para bucles cerrados. La lista muestra el número de vértices y el panel informa cuántos se han eliminado. Las coordenadas y longitudes del GeoJSON se actualizan con la geometría simplificada.

**Deshacer**, en Revisar y exportar, restaura simplificaciones, descartes, recálculos y cambios de puntos. Guarda hasta 40 estados durante la sesión. Una nueva imagen, una nueva detección, un cambio de modo o de modelo inician un historial nuevo. **Quitar último punto**, junto a los puntos de corrección, actúa únicamente sobre esos puntos.

**OSM para JOSM** descarga `caminos-pnoa.osm`, en XML OSM 0.6, con nodos WGS84 y vías de los trazados conservados. Las coordenadas coincidentes comparten nodos y se usan IDs negativos para elementos nuevos. Incluye `source=PNOA IGN` y un `fixme` de revisión; no asigna automáticamente una clase `highway` que el modelo no conoce. El archivo se genera para revisión local (`upload=false`). Ábrelo en JOSM mediante **Archivo → Abrir** y completa las conexiones, clasificación y atributos. El botón descarga el archivo, sin abrir aplicaciones externas ni enviar datos a OpenStreetMap.

Formato y apertura: https://wiki.openstreetmap.org/wiki/OSM_XML y https://josm.openstreetmap.de/wiki/Help/Action/Open

Zoom: rueda del ratón o +/−, entre 100% y 800%; **Ajustar** muestra la imagen completa y centrada. El visor ocupa todo el panel derecho y se adapta al tamaño de la ventana. **Llenar** amplía la imagen hasta cubrir el visor; los bordes que quedan fuera se pueden recorrer con la mano. La ortofoto mantiene sus proporciones y los marcadores conservan sus coordenadas al cambiar el tamaño de la ventana. La herramienta inicial es la **mano**: arrastra para mover la imagen. Pulsa **A** para activar los marcadores; aparece una previsualización del siguiente marcador bajo el cursor y un clic lo coloca. **S** o **Esc** vuelve a la mano. También puedes cambiar la herramienta desde el selector. Con marcadores activos, un clic en el fondo coloca un punto y arrastrar el fondo desplaza la vista temporalmente con la mano, sin crear un punto. Arrastrar un marcador permite moverlo; Shift + arrastrar siempre desplaza la vista.

Un clic sobre un marcador lo selecciona y resalta en naranja. **Suprimir** elimina el seleccionado sin renumerar los demás: si eliminas el 2, el 1 y el 3 conservan sus números. El siguiente marcador reutiliza el número libre más bajo. **Deshacer** restaura también la numeración y selección. En Wololo, el recorrido sigue el orden numérico: 1 → 2 → 3 termina en el 3, sin regresar al 2. Reutilizar un número vacante recupera su lugar en ese orden. El umbral y la detección del área completa se ocultan; Wololo utiliza un umbral interno de 0,5 para señalar dudas. Eliminar un marcador durante una revisión cancela la propuesta pendiente y conserva los tramos aceptados; vuelve a trazar con los marcadores restantes. Los atajos no actúan mientras escribes en campos, está abierto el selector de área o se procesa una petición.

El zoom amplía la imagen descargada, sin solicitar mayor resolución al WMS. Las coordenadas de selección y exportación permanecen referidas a la ortofoto original.

Documentación del motor ONNX: https://docs.opencv.org/5.0/main_modules/dnn.html

Para la corrección asistida con puntos, OpenCV reduce la imagen a 384 × 384, suaviza el ruido y convierte los colores a CIELAB. A partir de pequeñas muestras alrededor de tus puntos construye un coste por similitud de color. Dijkstra encuentra la ruta de menor coste entre cada par de puntos consecutivos y OpenCV simplifica la polilínea. La GUI anima el resultado **después** del cálculo; no representa progreso real del procesamiento. Este cálculo de corrección mantiene su límite de tamaño; la detección automática y la segmentación sí analizan la resolución completa descargada.

La corrección con puntos usa extracción asistida por color. Puede cruzar campos, tejados o zonas con color parecido. Las sombras y la vegetación pueden interrumpir el trazado. Ningún modo garantiza el eje ni la anchura del camino. El modelo D-LinkNet está orientado a carreteras de imágenes satelitales; su precisión en senderos o pistas rurales del PNOA necesita validación frente a trazados reales y puede requerir ajuste con ejemplos locales.

### Convertir los pesos D-LinkNet34

El proyecto utiliza `models/model.onnx` y `models/best.th`. Los pesos y el ONNX están excluidos de Git; para trasladar la aplicación copia estos archivos y `models/model.verification.json` además del código. El informe registra el SHA-256 del origen y diferencias numéricas entre PyTorch y OpenCV.

Para reproducir la conversión a otro archivo:

```powershell
.\.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install onnx
.\.venv\Scripts\python.exe tools/convert_dlinknet.py models/best.th --output models/model-new.onnx
```

El conversor solo carga tensores (`weights_only=True`) y exige coincidencia estricta con la arquitectura D-LinkNet34. No descarga pesos ResNet ni ejecuta objetos Python del checkpoint. La normalización original `BGR / 255 × 3.2 − 1.6` está integrada en el ONNX: el archivo acepta directamente el RGB [0,1] enviado por la aplicación. Incluye sigmoid. El modelo recibe cada recorte a 512×512; no reproduce las ocho transformaciones de la inferencia original a 1024×1024. La comparación numérica prueba la conversión, no la precisión geográfica del modelo. Arquitectura y atribución: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

La imagen WMS se solicita en EPSG:3857, con orden X/Y, a **4096 × 4096**, el máximo por petición anunciado por GetCapabilities del IGN (comprobado el 5 de octubre de 2026). No se amplía artificialmente una imagen de 1024×1024. La GUI indica dimensiones y metros de terreno por píxel solicitados; un área de 750 m equivale aproximadamente a 0,183 m/px. El tamaño de área se corrige por latitud en su centro; la longitud exportada se estima con distancias geodésicas esféricas. El máximo de píxeles por petición no garantiza la máxima resolución nativa en cualquier extensión: las ortofotos tienen distintas resoluciones según el vuelo y un área grande pierde detalle por metro. Reduce el área para caminos estrechos. No se descarga ni se analiza todo el territorio. Las últimas dos imágenes se conservan en memoria durante la sesión del servidor.

Servidor limitado a localhost, sin publicación externa. Las fuentes de la GUI son opcionales y tienen alternativa local. La aplicación siempre muestra la versión real de OpenCV.

## Fuentes

- Servicio oficial: https://www.ign.es/wms-inspire/pnoa-ma (capa `OI.OrthoimageCoverage`).
- PNOA y servicios: https://pnoa.ign.es/pnoa-imagen/visualizadores-y-servicios-web
- OpenCV 5: https://docs.opencv.org/5.0/index.html
- Paquete fijado: `opencv-python-headless==5.0.0.93`.

Mantén la atribución © IGN · PNOA al compartir imágenes y revisa las condiciones del IGN para tu uso.

## Crear un modelo de segmentación para PNOA

El objetivo es ajustar un modelo preentrenado con ejemplos de caminos del PNOA, en lugar de entrenarlo desde cero.

1. **Preparar imágenes.** Guardar ortofotos de distintas zonas y dividirlas en teselas de **512 × 512 píxeles**, como las que utiliza la aplicación. Mantener una resolución de terreno parecida a la prevista durante el uso.
2. **Dibujar máscaras correctas.** Cada tesela necesita una máscara del mismo tamaño: **0 = fondo** y **1 = superficie del camino o carretera**. Marcar toda la anchura de la vía, no solo el eje, para poder estimar su centro. Se pueden dibujar polígonos en CVAT y exportarlos como máscaras; comprobar que los valores exportados se convierten a las clases 0 y 1. [Documentación de máscaras de CVAT](https://docs.cvat.ai/docs/manual/advanced/annotation-with-polygons/creating-mask/).
3. **Separar entrenamiento y evaluación por zonas.** Reservar regiones completas para validación y evaluación final. Las teselas vecinas o solapadas de una misma ortofoto no deben repartirse entre esos conjuntos: producirían resultados demasiado optimistas.
4. **Entrenar con PyTorch.** Como primera prueba, ajustar el D-LinkNet34 existente con datos PNOA y medir su mejora. Después se puede comparar con SegFormer. [Ejemplo oficial de entrenamiento de SegFormer](https://github.com/huggingface/transformers/blob/main/examples/pytorch/semantic-segmentation/README.md).
5. **Evaluar y corregir los fallos.** Medir la coincidencia de las máscaras y revisar continuidad del camino, bifurcaciones y confusiones con campos o cauces. Usar los fallos observados en validación para decidir qué nuevos ejemplos etiquetar, manteniendo aparte el conjunto de evaluación final.
6. **Exportar a ONNX e integrar.** Adaptar la entrada y salida al contrato de la aplicación: RGB [0,1], NCHW `1×3×512×512` y una salida de probabilidades `1×1×H×W`. Incorporar al modelo exportado la normalización necesaria y sigmoid o la conversión apropiada de sus salidas. Comparar la inferencia original con el ONNX y verificar que OpenCV lo ejecuta antes de cargarlo desde la GUI. [Exportación oficial de PyTorch a ONNX](https://docs.pytorch.org/tutorials/beginner/onnx/export_simple_model_to_onnx_tutorial.html).

Como primera prueba, preparar **200–500 teselas revisadas**, con variedad de caminos, sombras, vegetación y ejemplos sin caminos. Es una propuesta de arranque, no una cantidad que garantice buenos resultados. Para entrenar cómodamente conviene una GPU; para etiquetar no hace falta.

Wololo puede generar borradores, pero **sus líneas exportadas no son máscaras de entrenamiento**: les falta la anchura real de la vía y una revisión humana. La sección **Dataset y entrenamiento** genera las máscaras directamente con el ONNX activo y permite revisarlas con un pincel o intercambiarlas con CVAT.

### Dataset y entrenamiento desde la GUI

El menú superior permite cambiar entre **Editor de caminos** y **Dataset y entrenamiento**, conservando la imagen y los trazados del editor. La selección de áreas del dataset utiliza el mismo mapa de OpenStreetMap, pero no modifica las coordenadas del editor ni dispara su descarga de ortofoto.

1. Pon nombre al lote y elige si la próxima zona pertenece a **Entrenamiento**, **Validación** o **Evaluación final**. **Elegir zona en OpenStreetMap** rellena el campo de bounding box; también puedes introducirlo como `oeste, sur, este, norte`, en longitud/latitud WGS84. Pulsa **Añadir bounding box** para incluir la zona en el lote.

En **Entrenar y usar**, el selector **Modelo de partida (.th)** usa por defecto `models/best.th`. Puedes continuar desde los pesos de un entrenamiento anterior, en `datasets/<dataset>/runs/<entrenamiento>/best.th`. También se listan los `.th` de la raíz y de `models/`; deben ser compatibles con D-LinkNet34. **Actualizar lista** detecta archivos nuevos. Se muestra la ruta del archivo seleccionado. Continuar desde sus pesos inicia un nuevo entrenamiento con un optimizador nuevo; combina ejemplos antiguos y nuevos y conserva zonas de validación separadas.
2. Añade otra zona geográficamente separada para validación. Se rechazan zonas de conjuntos distintos que se solapen o estén a menos de una tesela de distancia entre sus coberturas. Las zonas de evaluación final se conservan, pero no se utilizan durante el entrenamiento ni para elegir el mejor checkpoint.
3. Ajusta los metros por píxel solicitados (0,2 por defecto) y el umbral de las máscaras automáticas (0,5 por defecto). **Calcular teselas** estima el lote antes de descargarlo. Máximo 8 zonas y 256 teselas por dataset; para áreas grandes utiliza lotes menores o aumenta los metros por píxel.
4. Pulsa **Descargar y generar máscaras**. Se solicitan imágenes WMS de 512×512 a la resolución configurada, sin reducir una ortofoto completa a 512 píxeles. Cada tesela se segmenta con el ONNX activo del editor. Las teselas de borde pueden extenderse hasta completar una celda de 512 píxeles; su cobertura exacta se guarda en EPSG:3857. La resolución solicitada no garantiza que el vuelo PNOA tenga ese detalle nativo.
5. Selecciona un dataset y una tesela. El pincel **Pintar vía / Borrar vía** corrige la superficie de la carretera o camino sobre la imagen. Marca **He revisado esta máscara** y pulsa **Guardar máscara**. La máscara PNG guardada usa **0 = fondo y 255 = vía**; el entrenamiento la convierte a 0/1. Revisar una imagen sin caminos también es válido. Guarda antes de cambiar de tesela.
6. Opcionalmente, usa CVAT según el flujo descrito abajo. La GUI permite importar las máscaras corregidas y las marca como revisadas: importa únicamente un ZIP que hayas revisado.
7. Pulsa **Entrenar y exportar ONNX**. Elige épocas y CPU, CUDA o selección automática. Por defecto utiliza solo máscaras revisadas y exige ejemplos en entrenamiento y validación. **Incluir máscaras automáticas sin revisar** habilita entrenamiento experimental con pseudoetiquetas; sus métricas no representan precisión frente a etiquetas humanas.
8. El entrenamiento ajusta **D-LinkNet34** desde `models/best.th` por defecto (o el checkpoint seleccionado), con BCE + Dice, aumentos por rotaciones/reflejos y selección del mejor checkpoint según IoU de validación. Guarda pérdidas, IoU y Dice por época. Exporta el checkpoint a ONNX con el preprocesado integrado y compara sus salidas con PyTorch usando el conversor existente. No cambia el modelo del editor automáticamente.
9. Selecciona el entrenamiento completado y pulsa **Usar este modelo en el editor**. También funcionará en Wololo y en la detección de toda el área. La activación dura la sesión del servidor; el ONNX permanece en el dataset para cargarlo de nuevo si reinicias.

La descarga y el entrenamiento se ejecutan en segundo plano con progreso, registro y **Cancelar trabajo**. Solo se permite un trabajo de dataset/entrenamiento simultáneo. Cancelar conserva los archivos ya generados; una petición WMS o inferencia en curso puede tardar en terminar antes de cancelar. Reiniciar el servidor pierde el seguimiento de los trabajos, pero mantiene los datasets y modelos guardados.

Dependencias opcionales para entrenar (no hacen falta para descargar, revisar ni intercambiar máscaras):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-training.txt
```

Para GPU, el entorno necesita una instalación de PyTorch compatible con la tarjeta y CUDA. Con el entorno CPU actual también se puede entrenar, aunque tarda más. CVAT no necesita estar instalado en el servidor de esta aplicación ni requiere introducir credenciales aquí.

Los archivos se guardan en `datasets/<id>/`, excluido de Git:

```text
manifest.json                  # zonas, cobertura, resolución, conjuntos y revisión
images/<tesela>.png             # ortofoto 512×512
masks/<tesela>.png              # máscara binaria 0/255
runs/<run-id>/best.th           # mejores pesos PyTorch
runs/<run-id>/report.json       # métricas y procedencia de las etiquetas
runs/<run-id>/model.onnx        # modelo compatible con el editor
runs/<run-id>/model.verification.json
```

### Intercambio con CVAT

1. Descarga **Imágenes para CVAT** y crea una tarea con esas imágenes, conservando sus nombres y dimensiones. Crea la etiqueta **road**; `background` representa el fondo.
2. Descarga **Máscaras para CVAT** e impórtalas en esa tarea con formato **Segmentation Mask**. El ZIP contiene `labelmap.txt`, `ImageSets/Segmentation/default.txt` y máscaras RGB en `SegmentationClass/`. Usa RGB para declarar colores de clases; las máscaras locales de entrenamiento permanecen binarias 0/255.
3. Corrige las máscaras en CVAT y exporta con el mismo formato **Segmentation Mask**.
4. En la GUI selecciona ese ZIP y pulsa **Importar ZIP revisado**. Se comprueban nombres, dimensiones, clases y colores antes de guardar. Admite colores declarados en `labelmap.txt` y máscaras de índices 0/1. No cambia las ortofotos originales ni extrae rutas del ZIP al disco. Puedes importar solo un subconjunto de teselas revisadas.

Formato oficial: [Segmentation Mask de CVAT](https://docs.cvat.ai/docs/dataset_management/formats/format-smask/). La integración es mediante ZIP; no crea tareas ni sube imágenes automáticamente a una cuenta de CVAT. El ZIP **Dataset completo** incluye imágenes, máscaras locales, máscaras para CVAT y manifest, pero no los pesos del entrenamiento.

### Scripts Python para bounding boxes y entrenamiento

Edita [datasets.example.json](datasets.example.json) con tus zonas. Cada `bbox` usa `[oeste, sur, este, norte]` y cada `split` es `train`, `val` o `test`. Los directorios de salida deben ser nuevos: los scripts no sobrescriben datasets ni entrenamientos existentes.

```powershell
# Descargar teselas y generar borradores; crea images.zip y cvat.zip para CVAT:
.\.venv\Scripts\python.exe tools/prepare_dataset.py --config datasets.example.json --model models/model.onnx --output datasets/ejemplo

# Tras revisar las máscaras en la GUI o importar su ZIP de CVAT:
.\.venv\Scripts\python.exe tools/train_segmentation.py --dataset datasets/ejemplo --checkpoint models/best.th --output datasets/ejemplo/runs/manual-01 --epochs 10 --device auto

# Exportar y verificar el checkpoint elegido por validación:
.\.venv\Scripts\python.exe tools/convert_dlinknet.py datasets/ejemplo/runs/manual-01/best.th --output datasets/ejemplo/runs/manual-01/model.onnx
```

El script de entrenamiento también admite `--batch-size`, `--learning-rate` y `--allow-automatic`. La GUI utiliza lote de 1 y learning rate 0,0001. Entrenar a partir de máscaras generadas por el mismo modelo puede reforzar sus errores: la revisión humana y la evaluación en zonas distintas siguen siendo necesarias para comprobar mejoras reales.

## Verificación

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Las pruebas usan una ortofoto sintética para verificar una curva, validación de entradas, endpoints y conversión de coordenadas. El acceso real al WMS se verifica aparte y necesita internet.

Pruebas opcionales de integración ONNX y navegador (no son dependencias de la aplicación):

```powershell
.\.venv\Scripts\python.exe -m pip install onnx
npm install --prefix .qa --no-audit --no-fund --ignore-scripts playwright
.\.venv\Scripts\python.exe tests/check_onnx.py
.\.venv\Scripts\python.exe tests/gui_server.py
# En otra terminal, con Chrome instalado:
node tests/gui.cjs
node tests/gui_area.cjs
# Contra el servidor principal (puerto 5000):
node tests/gui_loader.cjs
node tests/test_geometry.cjs
node tests/gui_editing.cjs
node tests/gui_wololo.cjs
node tests/gui_shortcuts.cjs
node tests/gui_viewport.cjs
# Flujo de datasets en un servidor aislado con teselas y trabajos de prueba:
.\.venv\Scripts\python.exe tests/dataset_gui_server.py
# En otra terminal:
node tests/gui_datasets.cjs
# Prueba real de ajuste CPU, exportación y equivalencia con imágenes sintéticas:
.\.venv\Scripts\python.exe tests/check_dataset_training.py
```

El servidor de pruebas usa el puerto 5001 y una imagen sintética. El ONNX generado es exclusivamente una muestra de prueba de brillo, **no un modelo de caminos**. No se carga en el servidor principal. Los artefactos de prueba se guardan en `.qa/`, excluido de Git.

En el editor, **Modelo activo (ONNX)** permite seleccionar modelos de `models/`, de la raíz del proyecto y de `datasets/<dataset>/runs/<entrenamiento>/model.onnx` (exportados y verificados). Cambiarlo activa ese modelo para Segmentación, Wololo y la generación de borradores del dataset. El modelo de partida `.th` del entrenamiento sigue siendo independiente.

El editor y la preparación de datasets permiten elegir **PNOA IGN** (por defecto) o **ITACyL Castilla y León**, capa `Ortofoto_CyL` del [WMS oficial de ITACyL](https://www.itacyl.es/agro-y-geo-tecnologia/descarga-datos-geograficos/fotografia-aerea). ITACyL cubre Castilla y León y admite hasta 4000×4000 píxeles por solicitud, frente a los 4096×4096 del visor PNOA. Los datasets conservan la fuente en manifest.json y descargan teselas nativas de 512×512. Cambiar la fuente del editor requiere cargar otra vez la ortofoto; la fuente del lote es independiente. En el JSON de la herramienta CLI puede indicarse `"source": "itacyl"`.
El popup de OpenStreetMap recuerda la selección (centro y ancho), la posición del mapa y el zoom en `localStorage`, por separado para editor y datasets. Se mantienen al recargar o volver a abrir el navegador en la misma dirección local. **Pegar URL** permite localizar una zona; **Generar enlace** rellena el campo con una URL de OpenStreetMap del centro y zoom visibles, lista para copiar. El enlace de OpenStreetMap representa la vista, no el bounding box seleccionado.

En el editor, selecciona un trazado y usa **Eliminar**, **Dividir** (pulsa un punto interior) o **Unir (C)**. Para unir, pulsa C, elige el segundo trazado, añade puntos intermedios a la conexión naranja si hace falta y pulsa C para confirmar. Se conectan los extremos más próximos. **Esc** cancela; **Deshacer** o **Ctrl+Z** restaura cortes, eliminaciones y uniones. Durante una conexión pendiente, Ctrl+Z quita el último punto intermedio. Estas herramientas están disponibles cuando Wololo ha terminado o no hay revisión de tramos activa.

Modelos predeterminados: **models/model.onnx** para detección y borradores de máscaras; **models/best.th** para iniciar el entrenamiento. La precarga del ONNX requiere **models/model.verification.json**. Los selectores muestran los archivos presentes en el proyecto.

Las ortofotos del editor se descargan por teselas WMS de hasta **1024×1024**, con tres intentos y caché persistente en `cache/orthophotos/`. Puedes elegir entre 0,2 y 5 m/px; el valor predeterminado es 0,5. Se permite seleccionar hasta 30 km por lado, con un límite editable de megapíxeles en la GUI, calculado inicialmente a partir de la RAM disponible del servidor. El valor 0 permite pruebas sin límite. La resolución no se reduce automáticamente. El mosaico nativo se guarda como un array mapeado en disco y se reutiliza al detectar o usar Wololo; el visor recibe una vista previa de hasta 4096 px. La segmentación analiza bloques solapados sobre el mosaico y extrae los trazados de la máscara conjunta, evitando cortes en las fronteras de descarga. La caché conserva teselas parciales para reintentar y puede borrarse con el servidor detenido; no se elimina automáticamente. La detección completa de áreas grandes puede tardar y consume memoria adicional para probabilidades, máscaras y geometría.

En el selector del **editor**, **Dibujar polígono** permite marcar entre 3 y 128 vértices y finalizar con **Cerrar polígono**. Se descarga su bounding box por teselas, conservando contexto exterior para el modelo. La máscara y los trazados automáticos se recortan al polígono; Wololo limita su búsqueda al interior y evita atajos al simplificar polígonos cóncavos. El exterior aparece oscurecido y el contorno resaltado. La selección se conserva en localStorage; **Quitar polígono** vuelve a una selección rectangular. Los polígonos cruzados se rechazan. El selector de datasets conserva su selección rectangular.

El botón **Usar recomendado** consulta de nuevo la RAM del servidor. El presupuesto orientativo es el 50 % de la RAM disponible menos 512 MiB de reserva, con una estimación de 96 bytes por píxel para las estructuras de análisis. La GUI muestra píxeles y RAM estimada del bounding box completo (también al seleccionar polígonos), y conserva el límite manual en localStorage. Es una estimación, no una garantía: los trazados y las operaciones temporales pueden aumentar el consumo. El servidor comprueba el límite recibido antes de descargar o reservar el mosaico.
