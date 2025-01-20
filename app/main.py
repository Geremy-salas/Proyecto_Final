import logging
import os

from flask import Flask, render_template, request, send_file
import google.cloud.logging
from google.cloud import firestore
from google.cloud import storage
from google.cloud import vision
from google.cloud import vision_v1p3beta1 as vision
from google.cloud import texttospeech

# Configuración de logging
client = google.cloud.logging.Client()
client.get_default_handler()
client.setup_logging()

app = Flask(__name__)
vision_client = vision.ImageAnnotatorClient()
text_to_speech_client = texttospeech.TextToSpeechClient()

@app.route('/')
def root():
    return render_template('home.html')

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    successful_upload = False
    objects_detected = []
    extracted_text = ""
    phishing_result = "No evaluado"
    web_entities = []
    audio_file = None

    if request.method == 'POST':
        uploaded_file = request.files.get('picture')
        if uploaded_file:
            try:
                # Subir imagen al bucket de Google Cloud Storage
                gcs = storage.Client()
                bucket = gcs.get_bucket(os.environ.get('BUCKET', 'my-bmd-bucket1'))
                blob = bucket.blob(uploaded_file.filename)
                blob.upload_from_string(
                    uploaded_file.read(),
                    content_type=uploaded_file.content_type
                )
                logging.info(f"Imagen subida a {blob.public_url}")

                # Descargar la imagen al servidor temporalmente
                local_path = f"/tmp/{uploaded_file.filename}"
                with open(local_path, "wb") as image_file:
                    image_file.write(blob.download_as_bytes())

                # Procesar la imagen
                objects_detected = localize_objects(local_path)
                extracted_text = extract_text(blob.public_url)
                phishing_result = detect_phishing(extracted_text)
                web_entities = detect_web_uri(blob.public_url)
                audio_file = convert_text_to_audio(extracted_text)
                successful_upload = True

            except Exception as e:
                logging.error(f"Error en la carga o análisis de la imagen: {e}")

    return render_template(
        'upload_photo.html',
        successful_upload=successful_upload,
        objects_detected=objects_detected,
        extracted_text=extracted_text,
        phishing_result=phishing_result,
        web_entities=web_entities,
        audio_file=audio_file
    )


class Exception:
    pass


class TypeError:
    pass


@app.route('/search')
def search():
    query = request.args.get('q')
    results = []

    if query:
        db = firestore.Client()
        doc = db.collection(u'tags').document(query.lower()).get().to_dict()

        try:
            for url in doc['photo_urls']:
                results.append(url)
        except TypeError as e:
            pass

    return render_template('search.html', query=query, results=results)

@app.route('/verify', methods=['POST', 'GET'])
def verify():
    legitimacy_result = None
    web_results = []
    if request.method == 'POST':
        uploaded_file = request.files.get('picture')
        if uploaded_file:
            # Búsqueda inversa y análisis de legitimidad
            search_results = perform_reverse_search(uploaded_file)
            legitimacy_result = analyze_legitimacy(search_results)
            web_results = search_results.get("links", [])

    return render_template(
        'verify.html',
        legitimacy_result=legitimacy_result,
        web_results=web_results,
    )

@app.errorhandler(500)
def server_error(e):
    logging.exception('An error occurred during a request.')
    return render_template('error.html'), 500

# Funciones auxiliares
def detect_objects(image_uri):
    """Detecta objetos en la imagen utilizando Google Vision."""
    try:
        image = vision.Image(source=vision.ImageSource(image_uri=image_uri))
        objects = vision_client.object_localization(image=image).localized_object_annotations
        return [obj.name for obj in objects]
    except Exception as e:
        logging.error(f"Error al detectar objetos: {e}")
        return []

def extract_text(image_uri):
    """Extrae texto de la imagen."""
    try:
        image = vision.Image(source=vision.ImageSource(image_uri=image_uri))
        response = vision_client.text_detection(image=image)
        texts = response.text_annotations
        return texts[0].description if texts else ""
    except Exception as e:
        logging.error(f"Error al extraer texto: {e}")
        return ""

def detect_phishing(extracted_text):
    """Determina si el texto podría ser phishing."""
    phishing_keywords = ["password", "login", "verification", "bank", "account", "urgent",
                         "verify", "security", "credentials", "update", "email", "restricted",
                         "access", "locked", "transaction", "alert", "secure", "details",
                         "confirm", "attention", "urgent action", "immediate response",
                         "personal information", "billing", "expire", "unlock",
                         "verify now", "confidential", "safe", "click", "link", "free",
                         "promotion", "limited offer", "identity"]
    for word in phishing_keywords:
        if word.lower() in extracted_text.lower():
            return "Posible phishing detectado"
    return "No es phishing"

def convert_text_to_audio(text):
    """Convierte el texto extraído a un archivo de audio utilizando Google Text-to-Speech."""
    if text.strip():
        # Configuración para la conversión a voz
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="es-ES",  # Puedes cambiar el idioma si es necesario
            ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        # Solicitar la conversión a voz
        response = text_to_speech_client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )

        # Guardar el archivo de audio
        audio_path = "/tmp/extracted_text_audio.mp3"
        with open(audio_path, "wb") as out:
            out.write(response.audio_content)

        return audio_path
    return None

@app.route('/download_audio')
def download_audio():
    """Ruta para descargar el archivo de audio generado."""
    audio_file = "/tmp/extracted_text_audio.mp3"
    if os.path.exists(audio_file):
        return send_file(audio_file, as_attachment=True)
    return "Archivo de audio no encontrado."

def detect_web_uri(uri):
    """Detecta entidades web y páginas relacionadas con la imagen."""
    try:
        image = vision.Image(source=vision.ImageSource(image_uri=uri))
        response = vision_client.web_detection(image=image)
        web_entities = [entity.description for entity in response.web_detection.web_entities]
        return web_entities
    except Exception as e:
        logging.error(f"Error al detectar entidades web: {e}")
        return []

def perform_reverse_search(uploaded_file):
    """Realiza una búsqueda inversa de la imagen y devuelve resultados."""
    try:
        content = uploaded_file.read()
        image = vision.Image(content=content)
        response = vision_client.web_detection(image=image)
        links = [
            img.url for img in response.web_detection.full_matching_images
        ]
        return {"links": links}
    except Exception as e:
        logging.error(f"Error en la búsqueda inversa: {e}")
        return {"links": []}

def analyze_legitimacy(search_results):
    """Analiza los resultados de la búsqueda inversa y determina legitimidad."""
    trusted_domains = ["example.com", "trustedwebsite.org"]
    links = search_results.get("links", [])
    for link in links:
        for domain in trusted_domains:
            if domain in link:
                return "Legítimo"
    return "Sospechoso"


def len(objects):
    pass


def print(param):
    pass


def open(path, param):
    pass


def localize_objects(image_path):
    """Localiza objetos en una imagen desde un archivo local."""
    try:
        client = vision.ImageAnnotatorClient()
        with open(image_path, "rb") as image_file:
            content = image_file.read()
        image = vision.Image(content=content)
        objects = client.object_localization(image=image).localized_object_annotations

        detected_objects = []
        for obj in objects:
            detected_objects.append({
                "name": obj.name,
                "confidence": obj.score,
                "vertices": [{"x": v.x, "y": v.y} for v in obj.bounding_poly.normalized_vertices]
            })

        return detected_objects
    except Exception as e:
        logging.error(f"Error al localizar objetos: {e}")
        return []


def int(param):
    pass



if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
