# Proyecto_Computacion

Se desarrolló un aplicativo web que utiliza la *API de Google Vision* para extraer texto de imágenes y detectar posibles intentos de falsificación o phishing. El proceso comienza cuando el usuario sube una imagen, que es almacenada en un bucket. A partir de esta imagen, se extrae todo el texto, y mediante una función específica, se analiza si contiene indicios de phishing. Además, el sistema genera palabras clave asociadas al contenido, proporcionando metadata útil para su análisis.

Adicionalmente, se integró la *API de Cloud Text-to-Speech* para convertir el texto extraído en audio, ampliando las funcionalidades del sistema y permitiendo ofrecer la información en diferentes formatos según los requerimientos.

El sistema también verifica la legitimidad de las imágenes y, si estas están disponibles en la web, genera un listado de URLs de las fuentes originales, ayudando a identificar su origen.

Gracias a las capacidades avanzadas de inteligencia artificial de la API de Google Vision, el proceso de extracción de texto es altamente preciso, minimizando errores. Por otro lado, la API Cloud Text-to-Speech transforma el texto en audio con gran naturalidad, optimizando la experiencia del usuario.
