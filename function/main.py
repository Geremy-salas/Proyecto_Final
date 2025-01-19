import os
import logging

from google.cloud import firestore
from google.cloud import vision
import requests
from bs4 import BeautifulSoup


def photo_analysis_service(event, context):
    bucket = os.environ.get('BUCKET', 'my-bmd-bucket')
    file_name = event['name']

    # Analizar objetos y texto
    objects = _analyze_photo(bucket, file_name)
    text = _extract_text(bucket, file_name)

    # Verificar legitimidad mediante búsqueda inversa
    legitimacy, web_results = _verify_legitimacy(bucket, file_name)

    # Almacenar resultados en Firestore
    _store_results(bucket, file_name, objects, text, legitimacy, web_results)


def _analyze_photo(bucket, file_name):
    client = vision.ImageAnnotatorClient()
    image = vision.Image(source=vision.ImageSource(image_uri=f'gs://{bucket}/{file_name}'))
    objects = client.object_localization(image=image).localized_object_annotations
    return [obj.name for obj in objects]


def _extract_text(bucket, file_name):
    client = vision.ImageAnnotatorClient()
    image = vision.Image(source=vision.ImageSource(image_uri=f'gs://{bucket}/{file_name}'))
    response = client.text_detection(image=image)
    texts = response.text_annotations
    return texts[0].description if texts else ""


def _verify_legitimacy(bucket, file_name):
    """
    Realiza una verificación de legitimidad mediante búsqueda inversa.
    """
    file_path = f'https://storage.googleapis.com/{bucket}/{file_name}'
    search_results = _perform_reverse_search(file_path)
    legitimacy = _analyze_legitimacy(search_results)
    web_results = search_results.get("links", [])
    return legitimacy, web_results


def _perform_reverse_search(image_url):
    """
    Realiza una búsqueda inversa de la imagen utilizando un servicio web.
    """
    search_endpoint = "https://www.google.com/searchbyimage/upload"
    files = {"encoded_image": ("image.jpg", requests.get(image_url).content)}
    try:
        response = requests.post(search_endpoint, files=files, allow_redirects=False)
        if response.status_code == 302:
            results_url = response.headers.get("Location")
            return _scrape_search_results(results_url)
    except Exception as e:
        logging.error(f"Error en la búsqueda inversa: {e}")
    return {"links": []}


def _scrape_search_results(results_url):
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


def _analyze_legitimacy(search_results):
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


def _store_results(bucket, file_name, objects, text, legitimacy, web_results):
    db = firestore.Client()

    # Almacenar objetos detectados
    for obj in objects:
        db.collection(u'tags').document(obj.lower()).set(
            {u'photo_urls': firestore.ArrayUnion(
                [f'https://storage.googleapis.com/{bucket}/{file_name}']
            )
            },
            merge=True
        )

    # Almacenar texto extraído
    if text:
        db.collection(u'texts').document(file_name).set({"content": text})

    # Almacenar resultados de legitimidad
    db.collection(u'legitimacy').document(file_name).set({
        "legitimacy": legitimacy,
        "web_results": web_results
    })
