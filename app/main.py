import logging
import os

from flask import Flask, render_template, request
import google.cloud.logging
from google.cloud import firestore
from google.cloud import storage
from google.cloud import vision
import requests
from bs4 import BeautifulSoup

client = google.cloud.logging.Client()
client.get_default_handler()
client.setup_logging()

app = Flask(__name__)

# Instancia de Vision para reutilizar
vision_client = vision.ImageAnnotatorClient()

@app.route('/')
def root():
    return render_template('home.html')


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    successful_upload = False
    objects_detected = []
    extracted_text = ""
    phishing_result = "No evaluado"

    if request.method == 'POST':
        uploaded_file = request.files.get('picture')

        if uploaded_file:
            gcs = storage.Client()
            bucket = gcs.get_bucket(os.environ.get('BUCKET', 'my-bmd-bucket'))
            blob = bucket.blob(uploaded_file.filename)

            # Subir la imagen al bucket
            blob.upload_from_string(
                uploaded_file.read(),
                content_type=uploaded_file.content_type
            )

            logging.info(blob.public_url)

            # Análisis de la imagen
            objects_detected = detect_objects(blob.public_url)
            extracted_text = extract_text(blob.public_url)
            phishing_result = detect_phishing(extracted_text)

            successful_upload = True

    return render_template(
        'upload_photo.html',
        successful_upload=successful_upload,
        objects_detected=objects_detected,
        extracted_text=extracted_text,
        phishing_result=phishing_result
    )


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
            # Realiza la búsqueda inversa con la imagen cargada
            search_results = perform_reverse_search(uploaded_file)
            legitimacy_result = analyze_legitimacy(search_results)
            web_results = search_results.get("links", [])

    return render_template(
        'verify.html',
        legitimacy_result=legitimacy_result,
        web_results=web_results,
    )


def detect_objects(image_uri):
    image = vision.Image(source=vision.ImageSource(image_uri=image_uri))
    objects = vision_client.object_localization(image=image).localized_object_annotations
    return [obj.name for obj in objects]


def extract_text(image_uri):
    image = vision.Image(source=vision.ImageSource(image_uri=image_uri))
    response = vision_client.text_detection(image=image)
    texts = response.text_annotations
    return texts[0].description if texts else ""


def detect_phishing(extracted_text):
    phishing_keywords = [
        "password", "login", "verification", "bank", "account", "urgent",
        "verify", "security", "credentials", "update", "email", "restricted",
        "access", "locked", "transaction", "alert", "secure", "details",
        "confirm", "attention", "urgent action", "immediate response",
        "personal information", "billing", "expire", "unlock",
        "verify now", "confidential", "safe", "click", "link", "free",
        "promotion", "limited offer", "identity"
    ]
    for word in phishing_keywords:
        if word.lower() in extracted_text.lower():
            return "Posible phishing detectado"
    return "No es phishing"


def perform_reverse_search(image):
    """
    Realiza una búsqueda inversa de la imagen utilizando un servicio web.
    """
    search_endpoint = "https://www.google.com/searchbyimage/upload"
    files = {"encoded_image": image, "image_content": ""}

    try:
        response = requests.post(search_endpoint, files=files, allow_redirects=False)
        if response.status_code == 302:
            results_url = response.headers.get("Location")
            return scrape_search_results(results_url)
    except Exception as e:
        logging.error(f"Error en la búsqueda inversa: {e}")
    return {"links": []}


class Exception:
    pass


def scrape_search_results(results_url):
    """
    Procesa la URL de resultados de búsqueda para extraer enlaces significativos.
    """
    try:
        response = requests.get(results_url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        links = [a['href'] for a in soup.find_all('a', href=True) if 'http' in a['href']]
        return {"links": links}
    except Exception as e:
        logging.error(f"Error al analizar los resultados de búsqueda: {e}")
        return {"links": []}


def any(param):
    pass


def analyze_legitimacy(search_results):
    """
    Determina si la imagen es legítima basándose en los resultados de búsqueda.
    """
    links = search_results.get("links", [])
    if not links:
        return "No se encontró suficiente información para determinar la legitimidad."

    phishing_keywords = ["fake", "scam", "phishing", "fraud", "malware"]
    for link in links:
        if any(keyword in link.lower() for keyword in phishing_keywords):
            return "La imagen podría no ser legítima (posible phishing)."
    return "La imagen parece legítima."


def int(param):
    pass


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
